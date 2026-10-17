import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/platform/engine.g.dart';
import 'v020_session_integration_test.dart'
    show RecordingHintHost, ReplayController;

class LifetimeHost extends RecordingHintHost {
  @override
  Future<void> start(int epoch) async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late RecordingHintHost host;
  late ReplayController c;
  setUp(() async {
    host = LifetimeHost();
    c = ReplayController(host);
    c.corpus = await CorpusIndex.load(rootBundle);
    c.corpusProfile = CorpusProfile.cs2;
    c.phase = SessionPhase.listening;
  });
  tearDown(() => c.dispose());
  void emit(int window, String text, {int? start, int? end}) => c.bilingual(
    BilingualEvent(
      epoch: c.epoch,
      window: window,
      startMs: start ?? (window - 1) * 5000,
      endMs: end ?? window * 5000,
      english: text,
      chinese: '他们继续比赛。',
      appliedHints: 'CS2 broadcast.',
    ),
  );
  void eco() {
    emit(1, 'They have an eco round');
    emit(2, 'Another eco round follows');
    expect(host.hints.last, contains('eco='));
  }

  test(
    'generic recent hints expire on audio activity without new recognition',
    () {
      eco();
      expect(c.scene.map, isNull);
      c.activity(c.epoch, 0, false, 70001);
      expect(host.hints.last, isNot(contains('eco=')));
      final calls = host.hints.length;
      c.activity(c.epoch, 0, false, 71000);
      expect(host.hints.length, calls);
    },
  );

  test('audio expiry lets identical text become fresh independently again', () {
    eco();
    c.activity(c.epoch, 0, false, 70001);
    emit(3, 'They have an eco round', start: 70001, end: 75000);
    expect(host.hints.last, isNot(contains('eco=')));
    emit(4, 'Another eco round follows', start: 75000, end: 80000);
    expect(host.hints.last, contains('eco='));
  });

  test('confirmed map changes remove generic memory of old scene', () {
    eco();
    emit(3, 'They cross lobby');
    emit(4, 'He drops into vent');
    expect(c.scene.map, 'Nuke');
    expect(host.hints.last, contains('eco='));
    emit(5, 'We are now playing on Mirage');
    expect(c.scene.map, isNull);
    expect(host.hints.last, isNot(contains('eco=')));
    emit(6, 'He enters palace');
    expect(c.scene.map, 'Mirage');
    expect(host.hints.last, contains('Map: Mirage'));
  });

  test(
    'map expiry clears memory before late old captions but keeps display',
    () {
      eco();
      emit(3, 'They cross lobby');
      emit(4, 'He drops into vent');
      c.activity(c.epoch, 0, false, 66000);
      expect(c.scene.map, isNull);
      emit(8, 'They have an eco round', start: 25000, end: 30000);
      emit(9, 'Another eco round follows', start: 30000, end: 35000);
      expect(host.hints.last, isNot(contains('eco=')));
      expect(
        c.ledger.items
            .where((i) => i.english == 'They have an eco round')
            .length,
        2,
      );
      expect(c.ledger.items.last.status, CaptionStatus.ready);
    },
  );

  test('backward activity cannot rewind speech and recent clocks', () {
    c.activity(c.epoch, .4, true, 100000);
    c.activity(c.epoch, 0, false, 1000);
    expect(c.level, .4);
    expect(c.phase, SessionPhase.listening);
  });
  test(
    'NoSpeech completion also expires hints without an activity callback',
    () {
      eco();
      c.recognition(
        RecognitionEvent(
          epoch: c.epoch,
          window: 99,
          revision: 1,
          startMs: 70000,
          endMs: 75000,
          text: '',
          finalResult: true,
        ),
      );
      expect(host.hints.last, isNot(contains('eco=')));
    },
  );

  test('resume resets the audio high water mark for its new epoch', () async {
    c.activity(c.epoch, .4, true, 100000);
    c.phase = SessionPhase.paused;
    final oldEpoch = c.epoch;
    await c.resume();
    expect(c.epoch, oldEpoch + 1);
    c.activity(c.epoch, .6, true, 1000);
    expect(c.level, .6);
    expect(c.phase, SessionPhase.listening);
  });

  test(
    'reselecting library rejects late old-scope hint evidence and accepts fresh speech',
    () {
      c.activity(c.epoch, 0, false, 100000);
      c.corpusProfile = CorpusProfile.none;
      c.corpusProfile = CorpusProfile.cs2;
      emit(1, 'They have an eco round', start: 5000, end: 10000);
      emit(2, 'Another eco round follows', start: 10000, end: 15000);
      expect(host.hints.last, isNot(contains('eco=')));
      emit(3, 'They have an eco round', start: 100000, end: 105000);
      emit(4, 'Another eco round follows', start: 105000, end: 110000);
      expect(host.hints.last, contains('eco='));
    },
  );
}

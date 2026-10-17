import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/session_controller.dart';
import 'package:opencaption/platform/engine.g.dart';

class RecordingHintHost extends EngineHost {
  final hints = <String>[];
  @override
  Future<void> updateHints(String value, bool automaticAssist) async {
    hints.add(value);
  }
}

class ReplayController extends SessionController {
  ReplayController(EngineHost host) : super(host: host);
  @override
  String get backendFlavor => 'gemmaE2E';
  @override
  Future<void> savePreferences() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late RecordingHintHost host;
  late ReplayController c;
  setUp(() async {
    host = RecordingHintHost();
    c = ReplayController(host);
    c.corpus = await CorpusIndex.load(rootBundle);
    c.corpusProfile = CorpusProfile.cs2;
    c.phase = SessionPhase.listening;
  });
  tearDown(() => c.dispose());

  void emit(
    int window,
    String english,
    String chinese, {
    int? start,
    int? end,
    String hints = 'CS2 broadcast.',
  }) {
    c.bilingual(
      BilingualEvent(
        epoch: c.epoch,
        window: window,
        startMs: start ?? (window - 1) * 5000,
        endMs: end ?? window * 5000,
        english: english,
        chinese: chinese,
        appliedHints: hints,
      ),
    );
  }

  test(
    'actual corpus source -> scene -> bounded hints survives a gap and cut to another map',
    () {
      emit(1, 'They cross lobby', '他们穿过大厅。');
      emit(2, 'Broky drops into vent', 'broky 落入管道。');
      expect(c.scene.map, 'Nuke');
      expect(host.hints.last, contains('Map: Nuke'));
      expect(
        CorpusIndex.estimateHintTokens(host.hints.last),
        lessThanOrEqualTo(96),
      );
      emit(2, 'They enter palace', '他们进入宫殿。'); // duplicate window
      expect(
        c.ledger.items.where((x) => x.status != CaptionStatus.gap),
        hasLength(2),
      );
      c.gap(c.epoch, 12000, 15000);
      emit(3, 'They cross lobby and vent', '迟到的旧字幕。', start: 10000, end: 12000);
      expect(c.scene.map, isNull);
      expect(c.ledger.items[2].english, 'They cross lobby and vent');
      expect(c.ledger.items[3].status, CaptionStatus.gap);
      emit(4, 'He enters palace', '他进入宫殿。', start: 15000, end: 20000);
      emit(5, 'They hold connector', '他们守住拱门。', start: 20000, end: 25000);
      // Palace and Connector both exist on Anubis in the real library.
      // Preserve that ambiguity until a third, distinguishing cue arrives.
      expect(c.scene.map, isNull);
      emit(6, 'He crosses underpass', '他穿过下水道。', start: 25000, end: 30000);
      expect(c.scene.map, 'Mirage');
      expect(host.hints.last, contains('Map: Mirage'));
      expect(host.hints.last, isNot(contains('Map: Nuke')));
    },
  );

  test(
    'actual bundled team aliases learn affiliations and fresh bare IDs renew teams',
    () {
      emit(1, 'rain plays for FaZe', 'rain 为 FaZe 效力。');
      emit(2, 'broky from FaZe attacks', 'broky 发起进攻。');
      emit(3, 'Aleksib of NAVI calls the play', 'Aleksib 指挥战术。');
      emit(4, 'b1t plays for NAVI', 'b1t 为 NAVI 效力。');
      final expected = [
        c.corpus.canonicalTeam('FaZe')!,
        c.corpus.canonicalTeam('NAVI')!,
      ]..sort();
      expect(c.scene.teams, expected);
      c.activity(c.epoch, .02, false, 120000);
      expect(c.scene.teams, isEmpty);
      for (final row in ['rain', 'broky', 'Aleksib', 'b1t'].indexed) {
        emit(
          5 + row.$1,
          row.$2,
          row.$2,
          start: 120000 + row.$1 * 5000,
          end: 125000 + row.$1 * 5000,
        );
      }
      expect(c.scene.teams, expected);
      expect(host.hints.last, contains('Teams:'));
      expect(c.ledger.items.last.status, CaptionStatus.ready);
      expect(c.ledger.items.last.chinese, 'b1t');
    },
  );

  test(
    'numeric and registered-ID captions reach display while copied text and mismatched names do not',
    () {
      emit(1, '12', '12');
      expect(c.ledger.items.last.chinese, '12');
      emit(2, 'donk', 'donk');
      expect(c.ledger.items.last.chinese, 'donk');
      emit(3, 'donk', 'NiKo');
      expect(c.ledger.items.last.chinese, isNot('NiKo'));
      emit(4, 'hello', 'hello');
      expect(c.ledger.items.last.chinese, isNot('hello'));
      c.corpusProfile = CorpusProfile.none;
      emit(5, 'donk', 'donk', hints: '');
      expect(c.ledger.items.last.chinese, isNot('donk'));
      expect(host.hints.last, isEmpty);
    },
  );
}

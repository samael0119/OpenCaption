import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:flutter/services.dart';
import 'package:opencaption/local_preview.dart';
import 'package:opencaption/core/session_controller.dart';
import 'package:opencaption/platform/engine.g.dart';

class PendingHost extends EngineHost {
  final started = Completer<void>();
  int starts = 0;
  @override
  Future<void> start(int epoch) {
    starts++;
    return started.future;
  }

  @override
  Future<void> cancel() async {}
  @override
  Future<void> release() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('ending during resume ignores late native start completion', () async {
    final host = PendingHost();
    final controller = SessionController(host: host)
      ..phase = SessionPhase.paused;
    final resuming = controller.resume();
    expect(controller.phase, SessionPhase.preparing);
    await controller.end();
    host.started.complete();
    await resuming;
    expect(controller.phase, SessionPhase.ended);
    controller.dispose();
  });

  test('repeated resume cannot start two recordings', () async {
    final host = PendingHost();
    final controller = SessionController(host: host)
      ..phase = SessionPhase.paused;
    final first = controller.resume();
    await controller.resume();
    expect(host.starts, 1);
    host.started.complete();
    await first;
    expect(controller.phase, SessionPhase.listening);
    controller.dispose();
  });

  test(
    'library selection enables assistance and reselecting clears opt-out',
    () {
      final controller = SessionController(host: PendingHost());
      expect(controller.autoTermHints, isFalse);
      controller.corpusProfile = CorpusProfile.cs2;
      expect(controller.autoTermHints, isTrue);
      controller.autoTermHints = false;
      expect(controller.autoTermHints, isFalse);
      controller.corpusProfile = CorpusProfile.cs2;
      expect(controller.autoTermHints, isTrue);
      controller.corpusProfile = CorpusProfile.none;
      expect(controller.autoTermHints, isFalse);
      expect(controller.scene.map, isNull);
      controller.dispose();
    },
  );

  test(
    'capture gap forgets scene evidence but keeps in-flight hint provenance',
    () async {
      final controller = PreviewController();
      controller.corpus = await CorpusIndex.load(rootBundle);
      controller.corpusProfile = CorpusProfile.cs2;
      controller.phase = SessionPhase.listening;
      void emit(int window, String english) => controller.bilingual(
        BilingualEvent(
          epoch: 0,
          window: window,
          startMs: (window - 1) * 5000,
          endMs: window * 5000,
          english: english,
          chinese: '他们从大厅推进。',
        ),
      );
      emit(1, 'They cross lobby');
      emit(2, 'A player crosses lobby again'); // Lobby now enters the prompt.
      controller.gap(0, 10000, 12000);
      emit(
        3,
        'They cross lobby again now',
      ); // Could still originate in old hints.
      emit(4, 'He drops into vent');
      expect(controller.scene.map, isNull);
      expect(controller.metrics['hint_token_estimate'], lessThanOrEqualTo(96));
      controller.dispose();
    },
  );

  test(
    'exact applied-hint metadata allows fresh unhinted scene verification after expiry',
    () async {
      final c = PreviewController();
      c.corpus = await CorpusIndex.load(rootBundle);
      c.corpusProfile = CorpusProfile.cs2;
      c.phase = SessionPhase.listening;
      void emit(int window, int begin, int end, String text, String hints) =>
          c.bilingual(
            BilingualEvent(
              epoch: 0,
              window: window,
              startMs: begin,
              endMs: end,
              english: text,
              chinese: '他们继续推进。',
              appliedHints: hints,
            ),
          );
      emit(1, 0, 5000, 'They cross lobby', 'CS2 broadcast.');
      emit(2, 5000, 10000, 'They hold lobby again', 'CS2 broadcast.');
      emit(3, 10000, 15000, 'He drops vent', 'CS2 broadcast.; Lobby=大厅');
      expect(c.scene.map, 'Nuke');
      c.activity(0, .1, true, 61000);
      expect(c.scene.map, isNull);
      emit(10, 61000, 63000, 'A player moves through lobby', 'CS2 broadcast.');
      emit(
        11,
        63000,
        65000,
        'Another player drops into vent',
        'CS2 broadcast.',
      );
      expect(c.scene.map, 'Nuke');
      c.dispose();
    },
  );

  test(
    'future gap precedes late response arrival but not its audio order or scene evidence',
    () async {
      final c = PreviewController();
      c.corpus = await CorpusIndex.load(rootBundle);
      c.corpusProfile = CorpusProfile.cs2;
      c.phase = SessionPhase.listening;
      c.gap(0, 5000, 10000);
      c.bilingual(
        BilingualEvent(
          epoch: 0,
          window: 1,
          startMs: 0,
          endMs: 5000,
          english: 'They cross lobby',
          chinese: '他们穿过大厅。',
          appliedHints: 'CS2 broadcast.',
        ),
      );
      expect(c.ledger.items.first.english, 'They cross lobby');
      expect(c.ledger.items.last.status, CaptionStatus.gap);
      expect(c.ledger.latestSequence, 1);
      c.bilingual(
        BilingualEvent(
          epoch: 0,
          window: 3,
          startMs: 10000,
          endMs: 15000,
          english: 'He drops into vent',
          chinese: '他跳进管道。',
          appliedHints: 'CS2 broadcast.',
        ),
      );
      expect(c.scene.map, isNull);
      c.dispose();
    },
  );

  test('diagnostics retain live values and aggregate latency', () {
    final controller = SessionController(host: PendingHost());
    controller.diagnostic(controller.epoch, 'asr_ms', 120);
    controller.diagnostic(controller.epoch, 'asr_ms', 80);
    controller.diagnostic(controller.epoch, 'asr_rtf_milli', 400);
    controller.diagnostic(controller.epoch, 'translation_ms', 30);

    expect(controller.metrics['asr_ms'], 80);
    expect(controller.metrics['asr_count'], 2);
    expect(controller.metrics['asr_total_ms'], 200);
    expect(controller.metrics['asr_max_ms'], 120);
    expect(controller.metrics['asr_rtf_milli'], 400);
    expect(controller.metrics['translation_count'], 1);
    expect(controller.metrics['translation_total_ms'], 30);
    controller.dispose();
  });
}

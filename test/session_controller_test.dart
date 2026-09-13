import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
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

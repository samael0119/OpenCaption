// Explicit real-clock local integration; excluded from default unit tests.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/main.dart';
import 'package:opencaption/models/model_store.dart';
import 'package:opencaption/platform/engine.g.dart';
import '../test/v020_session_integration_test.dart' show ReplayController;

class LiveHintHost extends EngineHost {
  Process? process;
  @override
  Future<void> updateHints(String hints, bool automaticAssist) async {
    process?.stdin.writeln(
      jsonEncode({
        'type': 'hints',
        'hints': hints,
        'automatic': automaticAssist,
      }),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final run = Platform.environment['OPENCAPTION_JOINT_RUN']!;
  testWidgets('real capture queue model controller widget $run', (
    tester,
  ) async {
    final out =
        'evaluation/results/v020-independent/joint_live_${run}_ui.jsonl';
    expect(
      File(out).existsSync(),
      false,
      reason: 'Never implicitly replay a run',
    );
    final host = LiveHintHost();
    final c = ReplayController(host);
    await tester.runAsync(() async {
      c.corpus = await CorpusIndex.load(rootBundle);
      c.models.catalog =
          (jsonDecode(await rootBundle.loadString('assets/models.json'))
                  as List)
              .map((x) => ModelSpec(Map<String, dynamic>.from(x as Map)))
              .toList();
    });
    c.corpusProfile = CorpusProfile.cs2;
    c.asrId = 'gemma-4-e2b-litert';
    c.initialized = true;
    c.phase = SessionPhase.listening;
    tester.view.physicalSize = const Size(390, 780);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(OpenCaptionApp(controller: c));
    final process = (await tester.runAsync(
      () => Process.start('/home/hyh/Tools/litert/litert-venv/bin/python', [
        'evaluation/v020_joint_live_bridge.py',
      ]),
    ))!;
    host.process = process;
    // Construct external streams in the real async zone. Creating a file sink
    // in FakeAsync and awaiting its close in runAsync can stall test cleanup.
    final transport = (await tester.runAsync(() async {
      final errorsFile = File(
        'evaluation/results/v020-independent/joint_live_${run}_stderr.log',
      );
      final done = Completer<void>();
      final subscription = process.stderr.listen(
        (bytes) => errorsFile.writeAsBytesSync(bytes, mode: FileMode.append),
        onDone: done.complete,
        onError: done.completeError,
      );
      final replies = StreamIterator<Map<String, dynamic>>(
        process.stdout
            .transform(utf8.decoder)
            .transform(const LineSplitter())
            .where((x) => x.startsWith('OPENCAPTION_JSON '))
            .map((x) => jsonDecode(x.substring(17)) as Map<String, dynamic>),
      );
      return (subscription: subscription, done: done.future, replies: replies);
    }))!;
    final replies = transport.replies;
    final clock = Stopwatch();
    final windows = <int>{};
    var complete = false, capEnd = false, results = 0;
    var actions = <dynamic>[];
    void record(Map<String, Object?> row) {
      File(
        out,
      ).writeAsStringSync('${jsonEncode(row)}\n', mode: FileMode.append);
    }

    try {
      while ((await tester.runAsync(
        () => replies.moveNext().timeout(const Duration(seconds: 150)),
      ))!) {
        final row = replies.current;
        if (row['type'] == 'ready') {
          actions = List<dynamic>.from(row['actions'] as List);
          clock.start();
          process.stdin.writeln(jsonEncode({'type': 'begin'}));
          await host.updateHints(
            c.corpus.e2eHints('', profile: CorpusProfile.cs2),
            true,
          );
          record({
            'type': 'metadata',
            'run': run,
            'scope':
                'Real-clock local core/widget adapter; not screen or Android timing',
          });
        } else if (row['type'] == 'capture_event') {
          final f = row['fields'] as List;
          if (row['event'] == 'ACT') {
            final audioMs = int.parse(f[0] as String);
            c.activity(c.epoch, 0, false, audioMs);
            while (actions.isNotEmpty &&
                audioMs >= (actions.first['at_ms'] as int)) {
              final action = actions.removeAt(0) as Map;
              switch (action['action']) {
                case 'map':
                  c.correctScene(map: 'Nuke');
                  expect(c.manualMap, 'Nuke');
                case 'teams':
                  c.correctScene(
                    map: 'Nuke',
                    team1: c.corpus.canonicalTeam('FaZe'),
                    team2: c.corpus.canonicalTeam('NAVI'),
                  );
                  expect(c.hasManualTeams, true);
                case 'automatic':
                  c.restoreAutomaticScene();
                  expect(c.hasSceneCorrection, false);
                case 'no_corpus':
                  c.corpusProfile = CorpusProfile.none;
                  expect(c.autoTermHints, false);
                case 'cs2':
                  c.corpusProfile = CorpusProfile.cs2;
                  expect(c.autoTermHints, true);
                default:
                  throw StateError('Unknown frozen action');
              }
              record({
                'type': 'action',
                ...Map<String, dynamic>.from(action),
                'audio_ms': audioMs,
                'dart_elapsed_ms': clock.elapsedMilliseconds,
              });
            }
          } else if (row['event'] == 'GAP') {
            c.gap(
              c.epoch,
              int.parse(f[1] as String),
              int.parse(f[2] as String),
            );
          } else if (row['event'] == 'CAPEND') {
            capEnd = true;
          }
          record({...row, 'dart_elapsed_ms': clock.elapsedMilliseconds});
        } else if (row['type'] == 'result') {
          final window = row['window'] as int;
          expect(windows.add(window), true, reason: 'Duplicate result');
          expect(row['hints'].length, lessThanOrEqualTo(240));
          expect(
            CorpusIndex.estimateHintTokens(row['hints'] as String),
            lessThanOrEqualTo(96),
          );
          if (row['status'] == 'subtitle') {
            c.bilingual(
              BilingualEvent(
                epoch: c.epoch,
                window: window,
                startMs: row['start_ms'] as int,
                endMs: row['end_ms'] as int,
                english: row['english'] as String,
                chinese: row['chinese'] as String,
                appliedHints: row['hints'] as String,
              ),
            );
          } else if (row['status'] == 'invalid') {
            c.gap(c.epoch, row['start_ms'] as int, row['end_ms'] as int);
          }
          // NoSpeech produces no subtitle in the product; activity drives TTL.
          await tester.pump(const Duration(milliseconds: 16));
          await tester.pump(const Duration(milliseconds: 300));
          await tester.pumpAndSettle(
            const Duration(milliseconds: 100),
            EnginePhase.sendSemanticsUpdate,
            const Duration(seconds: 5),
          );
          expect(tester.takeException(), isNull);
          expect(find.text('暂停'), findsOneWidget);
          String? displayedEnglish, displayedChinese;
          if (row['status'] == 'subtitle') {
            final caption = c.ledger.items.lastWhere(
              (x) =>
                  x.status != CaptionStatus.gap &&
                  x.startMs == row['start_ms'] &&
                  x.endMs == row['end_ms'],
            );
            displayedEnglish = caption.english;
            displayedChinese = caption.chinese;
            expect(find.text(displayedEnglish), findsWidgets);
            if (displayedChinese.isNotEmpty) {
              expect(find.text(displayedChinese), findsWidgets);
            }
          }
          results++;
          record({
            ...row,
            'type': 'widget_result',
            'dart_elapsed_ms': clock.elapsedMilliseconds,
            'frame_after_audio_end_proxy_ms':
                clock.elapsedMilliseconds - (row['end_ms'] as int),
            'ledger_count': c.ledger.items.length,
            'map': c.scene.map,
            'teams': c.scene.teams,
            'widget_exception': false,
            'displayed_english': displayedEnglish,
            'displayed_chinese': displayedChinese,
          });
          process.stdin.writeln(jsonEncode({'type': 'ack', 'window': window}));
        } else if (row['type'] == 'complete') {
          host.process = null;
          expect(capEnd, true);
          expect(row['requests'], results);
          expect(actions, isEmpty);
          complete = true;
          record({...row, 'dart_elapsed_ms': clock.elapsedMilliseconds});
          break;
        }
        await tester.pump();
      }
      expect(complete, true);
      await tester.runAsync(() => process.stdin.close());
      expect(
        await tester.runAsync(
          () => process.exitCode.timeout(const Duration(seconds: 30)),
        ),
        0,
      );
      await tester.runAsync(
        () => transport.done.timeout(const Duration(seconds: 10)),
      );
    } catch (error, stack) {
      record({
        'type': 'harness_failure',
        'error': error.toString(),
        'stack': stack.toString(),
      });
      rethrow;
    } finally {
      host.process = null;
      process.kill();
      await tester.runAsync(() async {
        await process.exitCode.timeout(const Duration(seconds: 10));
        await replies.cancel().timeout(const Duration(seconds: 10));
        await transport.subscription.cancel().timeout(
          const Duration(seconds: 10),
        );
      });
      await tester.pumpWidget(const SizedBox());
      c.dispose();
    }
  }, timeout: const Timeout(Duration(minutes: 75)));
}

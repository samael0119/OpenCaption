// Explicit local integration probe, outside the default unit-test directory.
// Run only under the documented model lock/cgroup/timeout.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/platform/engine.g.dart';
import '../test/v020_session_integration_test.dart'
    show RecordingHintHost, ReplayController;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('current model replies causally update real controller hints', () async {
    final manifest =
        jsonDecode(
              File(
                'evaluation/results/v020-independent/controller_closed_loop_manifest.json',
              ).readAsStringSync(),
            )
            as Map<String, dynamic>;
    final process = await Process.start(
      '/home/hyh/Tools/litert/litert-venv/bin/python',
      ['evaluation/v020_controller_model_bridge.py'],
    );
    final errorFile = File(
      'evaluation/results/v020-independent/controller_closed_loop_model_stderr.log',
    ).openWrite();
    final errorsDone = process.stderr.listen(errorFile.add).asFuture<void>();
    final replies = StreamIterator<Map<String, dynamic>>(
      process.stdout
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .where((line) => line.startsWith('OPENCAPTION_JSON '))
          .map(
            (line) => jsonDecode(line.substring(17)) as Map<String, dynamic>,
          ),
    );
    Future<Map<String, dynamic>> next() async {
      expect(
        await replies.moveNext().timeout(const Duration(seconds: 120)),
        true,
      );
      return replies.current;
    }

    final records = <Map<String, Object?>>[];
    try {
      expect((await next())['type'], 'ready');
      for (final mode in manifest['modes'] as List) {
        final host = RecordingHintHost();
        final c = ReplayController(host);
        c.corpus = await CorpusIndex.load(rootBundle);
        c.corpusProfile = mode == 'no_hint'
            ? CorpusProfile.none
            : CorpusProfile.cs2;
        c.phase = SessionPhase.listening;
        var clock = 0;
        try {
          for (final caseRow in manifest['cases'] as List) {
            // The next request is fixed before its own output exists.
            final hints = mode == 'no_hint'
                ? ''
                : (host.hints.isEmpty
                      ? c.corpus.e2eHints('', profile: CorpusProfile.cs2)
                      : host.hints.last);
            expect(
              CorpusIndex.estimateHintTokens(hints),
              lessThanOrEqualTo(96),
            );
            process.stdin.writeln(
              jsonEncode({
                'mode': mode,
                'window': caseRow['window'],
                'hints': hints,
              }),
            );
            await process.stdin.flush();
            final row = await next();
            expect(row['type'], 'request');
            expect(row['window'], caseRow['window']);
            expect(row['requested_hints'], hints);
            clock =
                max(clock, row['end_ms'] as int) +
                (row['inference_ms'] as num).round();
            c.activity(c.epoch, 0, false, clock);
            if (row['status'] == 'subtitle') {
              c.bilingual(
                BilingualEvent(
                  epoch: c.epoch,
                  window: row['window'] as int,
                  startMs: row['start_ms'] as int,
                  endMs: row['end_ms'] as int,
                  english: row['english'] as String,
                  chinese: row['chinese'] as String,
                  appliedHints: row['hints'] as String,
                ),
              );
            } else {
              c.recognition(
                RecognitionEvent(
                  epoch: c.epoch,
                  window: row['window'] as int,
                  revision: 1,
                  startMs: row['start_ms'] as int,
                  endMs: row['end_ms'] as int,
                  text: '',
                  finalResult: true,
                ),
              );
            }
            records.add({
              ...row,
              'virtual_delivery_ms': clock,
              'map': c.scene.map,
              'teams': List<String>.from(c.scene.teams),
              'candidates': List<String>.from(c.scene.teamCandidates),
              'next_hints': host.hints.isEmpty ? '' : host.hints.last,
              'display_items': c.ledger.items.length,
            });
          }
        } finally {
          c.dispose();
        }
      }
      final complete = await next();
      expect(complete['requests'], 20);
      await process.stdin.close();
      expect(await process.exitCode.timeout(const Duration(seconds: 30)), 0);
      await errorsDone;
      File(
        'evaluation/results/v020-independent/controller_closed_loop_result.json',
      ).writeAsStringSync(
        const JsonEncoder.withIndent('  ').convert({
          'scope': manifest['scope'],
          'requests': records,
          'complete': true,
          'independent_quality_acceptance': false,
        }),
      );
    } finally {
      process.kill();
      await replies.cancel();
      await errorFile.close();
    }
  }, timeout: const Timeout(Duration(minutes: 8)));
}

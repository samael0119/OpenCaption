import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/platform/engine.g.dart';
import 'v020_session_integration_test.dart'
    show RecordingHintHost, ReplayController;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'cached actual model texts traverse controller with original hint provenance',
    () async {
      final fixture =
          jsonDecode(
                File(
                  'test/fixtures/v020_actual_context_replay.json',
                ).readAsStringSync(),
              )
              as Map<String, dynamic>;
      final reports = <Map<String, Object?>>[];
      for (final session in fixture['sessions'] as List) {
        final host = RecordingHintHost();
        final c = ReplayController(host);
        c.corpus = await CorpusIndex.load(rootBundle);
        c.corpusProfile = CorpusProfile.cs2;
        c.phase = SessionPhase.listening;
        var virtualClock = 0;
        var valid = 0;
        var previousEnd = 0;
        final rows = <Map<String, Object?>>[];
        try {
          for (final (index, row) in (session['windows'] as List).indexed) {
            final start = row['start_ms'] as int;
            final end = row['end_ms'] as int;
            expect(start, previousEnd);
            previousEnd = end;
            virtualClock =
                max(virtualClock, end) + (row['inference_ms'] as num).round();
            // Virtual sample clock, not fresh capture or measured UI timing.
            c.activity(c.epoch, 0, false, virtualClock);
            if (row['status'] == 'subtitle') {
              valid++;
              final event = BilingualEvent(
                epoch: c.epoch,
                window: index + 1,
                startMs: start,
                endMs: end,
                english: row['english'] as String,
                chinese: row['chinese'] as String,
                appliedHints: row['applied_hints'] as String,
              );
              c.bilingual(event);
              final count = c.ledger.items.length;
              c.bilingual(event);
              expect(
                c.ledger.items.length,
                count,
              ); // real output cannot double vote
            } else {
              c.recognition(
                RecognitionEvent(
                  epoch: c.epoch,
                  window: index + 1,
                  revision: 1,
                  startMs: start,
                  endMs: end,
                  text: '',
                  finalResult: true,
                ),
              );
            }
            final proposed = host.hints.isEmpty ? '' : host.hints.last;
            expect(
              CorpusIndex.estimateHintTokens(proposed),
              lessThanOrEqualTo(96),
            );
            if (c.scene.map != null) {
              expect(c.scene.map, fixture['reference_map']);
            }
            rows.add({
              'window': index + 1,
              'start_ms': start,
              'end_ms': end,
              'virtual_delivery_ms': virtualClock,
              'source_status': row['status'],
              'actual_applied_hints': row['applied_hints'],
              'proposed_next_hints': proposed,
              'map': c.scene.map,
              'teams': List<String>.from(c.scene.teams),
              'candidates': List<String>.from(c.scene.teamCandidates),
              'display_items': c.ledger.items.length,
            });
          }
          expect(c.ledger.items.length, valid);
          final first = rows.where((r) => r['map'] != null).firstOrNull;
          reports.add({
            'id': session['id'],
            'windows': rows,
            'subtitle_windows': valid,
            'total_windows': rows.length,
            'confirmed_map_windows': rows.where((r) => r['map'] != null).length,
            'confirmed_team_windows': rows
                .where((r) => (r['teams'] as List).length == 2)
                .length,
            'first_map_audio_end_ms': first?['end_ms'],
            'first_map_virtual_delivery_ms': first?['virtual_delivery_ms'],
          });
        } finally {
          c.dispose();
        }
      }
      // Ordinary regression runs are read-only and do not require ignored logs.
      // The bounded evidence run explicitly opts into a report artifact.
      final reportPath = Platform.environment['OPENCAPTION_REPLAY_REPORT'];
      if (reportPath != null) {
        File(reportPath).writeAsStringSync(
          const JsonEncoder.withIndent('  ').convert({
            'scope': fixture['scope'],
            'sources': fixture['sources'],
            'sessions': reports,
            'regenerated_closed_loop': false,
            'independent_quality_acceptance': false,
          }),
        );
      }
    },
  );
}

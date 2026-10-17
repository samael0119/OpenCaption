// Bounded cached-output shadow probe. No model, capture, network or phone.
import 'dart:collection';
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
  test(
    'past actual texts produce shadow candidates without changing actual controller hints',
    () async {
      final fixture =
          jsonDecode(
                File(
                  'test/fixtures/v020_actual_context_replay.json',
                ).readAsStringSync(),
              )
              as Map;
      final reports = <Map<String, Object?>>[];
      for (final session in fixture['sessions'] as List) {
        final host = RecordingHintHost();
        final c = ReplayController(host);
        c.corpus = await CorpusIndex.load(rootBundle);
        c.corpusProfile = CorpusProfile.cs2;
        c.phase = SessionPhase.listening;
        final recent = Queue<String>();
        final injected = <String>{};
        final rows = <Map<String, Object?>>[];
        var virtualClock = 0;
        try {
          for (final (i, row) in (session['windows'] as List).indexed) {
            final start = row['start_ms'] as int, end = row['end_ms'] as int;
            // Retrieval occurs before target completion; target text is not read
            // by the candidate generator, and its output never reaches the host.
            c.activity(c.epoch, 0, false, start);
            final hostCount = host.hints.length;
            final candidates = c.corpus.relatedCandidates(
              recent,
              map: c.scene.map,
              teams: c.scene.teams,
              injectedConcepts: injected,
            );
            final shadow = c.corpus.e2eHints(
              '',
              includeRecent: true,
              recentEnglish: recent,
              map: c.scene.map,
              teams: c.scene.teams,
              related: candidates,
            );
            expect(host.hints.length, hostCount);
            expect(shadow.length, lessThanOrEqualTo(240));
            expect(
              CorpusIndex.estimateHintTokens(shadow),
              lessThanOrEqualTo(96),
            );
            expect(candidates.length, lessThanOrEqualTo(2));
            if (c.scene.map == null) expect(candidates, isEmpty);
            final previousMap = c.scene.map;
            final sourceHints = row['applied_hints'] as String;
            injected.addAll(
              c.corpus
                  .match(sourceHints, limit: c.corpus.termCount)
                  .map(c.corpus.sceneConceptFor),
            );
            virtualClock =
                max(virtualClock, end) + (row['inference_ms'] as num).round();
            c.activity(c.epoch, 0, false, virtualClock);
            if (row['status'] == 'subtitle') {
              c.bilingual(
                BilingualEvent(
                  epoch: c.epoch,
                  window: i + 1,
                  startMs: start,
                  endMs: end,
                  english: row['english'] as String,
                  chinese: row['chinese'] as String,
                  appliedHints: sourceHints,
                ),
              );
              if (previousMap != c.scene.map) recent.clear();
              recent.add(row['english'] as String);
              if (recent.length > 6) recent.removeFirst();
            } else {
              c.recognition(
                RecognitionEvent(
                  epoch: c.epoch,
                  window: i + 1,
                  revision: 1,
                  startMs: start,
                  endMs: end,
                  text: '',
                  finalResult: true,
                ),
              );
            }
            rows.add({
              'target_window': i + 1,
              'source_start_ms': start,
              'target_end_ms': end,
              'retained_source_count_after_target': recent.length,
              'scene_at_retrieval': previousMap,
              'actual_applied_hints': sourceHints,
              'actual_proposed_next_hints': host.hints.isEmpty
                  ? ''
                  : host.hints.last,
              'shadow_hints_before_target': shadow,
              'related_candidates': candidates
                  .map(
                    (r) => {
                      'english': r.term['english'],
                      'chinese': r.term['chinese'],
                      'anchor': r.anchor,
                      'reason': r.reason,
                      'source_refs': r.sourceRefs,
                    },
                  )
                  .toList(),
              'shadow_submitted_to_model': false,
            });
          }
          reports.add({
            'id': session['id'],
            'windows': rows,
            'candidate_windows': rows
                .where((r) => (r['related_candidates'] as List).isNotEmpty)
                .length,
            'shadow_changed_hint_windows': rows
                .where(
                  (r) => (r['shadow_hints_before_target'] as String).contains(
                    'Candidate vocabulary',
                  ),
                )
                .length,
          });
        } finally {
          c.dispose();
        }
      }
      File(
        'evaluation/results/v020-independent/related_shadow.json',
      ).writeAsStringSync(
        const JsonEncoder.withIndent('  ').convert({
          'scope': fixture['scope'],
          'sessions': reports,
          'regenerated_inference': false,
          'independent_quality_acceptance': false,
          'roster_date_unknown': true,
          'candidate_source': 'explicit sourced one-hop map routes',
          'input_fixture': 'test/fixtures/v020_actual_context_replay.json',
        }),
      );
    },
  );
}

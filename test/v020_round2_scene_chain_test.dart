import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/session_controller.dart';
import 'package:opencaption/platform/engine.g.dart';

class _HintHost extends EngineHost {
  final hints = <String>[];
  @override
  Future<void> updateHints(String value, bool automaticAssist) async {
    hints.add(value);
  }
}

class _Controller extends SessionController {
  _Controller(EngineHost host) : super(host: host);
  @override
  String get backendFlavor => 'gemmaE2E';
  @override
  Future<void> savePreferences() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('bounded source -> current scene -> next prompt diagnostic', () async {
    final output = Platform.environment['OPENCAPTION_SCENE_CHAIN_REPORT'];
    if (output == null || File(output).existsSync()) {
      throw StateError('Explicit new report path required; never overwrite');
    }
    final plan = jsonDecode(
      File('evaluation/results/v020-round2/scene-chain/fixture.json')
          .readAsStringSync(),
    ) as Map<String, dynamic>;
    final reports = <Map<String, Object?>>[];
    final errors = <String>[];
    var events = 0;
    for (final session in plan['sessions'] as List) {
      final host = _HintHost();
      final c = _Controller(host);
      c.corpus = await CorpusIndex.load(rootBundle);
      c.corpusProfile = CorpusProfile.cs2;
      c.phase = SessionPhase.listening;
      final expectedTeams = (session['target_teams'] as List)
          .map((t) => c.corpus.canonicalTeam(t as String)!)
          .toList()..sort();
      final traces = <Map<String, Object?>>[];
      int? firstMap, firstTeams;
      var mapConfirmations = 0, wrongMap = 0;
      var teamConfirmations = 0, wrongTeams = 0;
      var virtualClock = 0;
      try {
        for (final row in session['windows'] as List) {
          events++;
          if (events > 120) throw StateError('Observation limit');
          final end = row['end_ms'] as int;
          virtualClock = max(virtualClock, end) +
              (row['inference_ms'] as num).round();
          c.activity(c.epoch, 0, false, virtualClock);
          if (row['status'] == 'subtitle') {
            c.bilingual(BilingualEvent(
              epoch: c.epoch,
              window: row['window'] as int,
              startMs: row['start_ms'] as int,
              endMs: end,
              english: row['english'] as String,
              chinese: row['chinese'] as String,
              appliedHints: row['applied_hints'] as String,
            ));
          } else {
            c.recognition(RecognitionEvent(
              epoch: c.epoch,
              window: row['window'] as int,
              revision: 1,
              startMs: row['start_ms'] as int,
              endMs: end,
              text: '',
              finalResult: true,
            ));
          }
          final teams = List<String>.from(c.scene.teams)..sort();
          final map = c.scene.map;
          final proposed = host.hints.isEmpty ? '' : host.hints.last;
          final tokens = CorpusIndex.estimateHintTokens(proposed);
          if (tokens > 96) errors.add('${session['id']}: budget >96');
          if (map != null) {
            mapConfirmations++;
            if (map != session['target_map']) {
              // Before a declared map cut, the original Nuke is correct.
              final cut = session['id'] == 'explicit_cut_and_denial' && end < 15000;
              if (!cut) wrongMap++;
            } else {
              firstMap ??= end;
            }
          }
          if (teams.isNotEmpty) {
            teamConfirmations++;
            if (jsonEncode(teams) != jsonEncode(expectedTeams)) {
              wrongTeams++;
            } else {
              firstTeams ??= end;
            }
          }
          if (row['must_release_map'] != null && map == row['must_release_map']) {
            errors.add('${session['id']}: current denial did not release');
          }
          traces.add({
            'window': row['window'], 'audio_end_ms': end,
            'source_english': row['english'], 'source_status': row['status'],
            'applied_hints': row['applied_hints'], 'proposed_hints': proposed,
            'hint_token_proxy': tokens, 'map': map, 'teams': teams,
            'candidates': List<String>.from(c.scene.teamCandidates),
            'virtual_delivery_ms': virtualClock,
          });
        }
        if (wrongMap != 0 || wrongTeams != 0) {
          errors.add('${session['id']}: wrong confirmed scene');
        }
        if (session['map_eligible'] == true && firstMap == null) {
          errors.add('${session['id']}: eligible map never confirmed');
        }
        if (session['team_eligible'] == true && firstTeams == null) {
          errors.add('${session['id']}: eligible teams never confirmed');
        }
        reports.add({
          'id': session['id'], 'kind': session['kind'], 'events': traces.length,
          'expected_map': session['target_map'], 'expected_teams': expectedTeams,
          'map_eligible': session['map_eligible'], 'team_eligible': session['team_eligible'],
          'first_correct_map_audio_end_ms': firstMap,
          'first_correct_teams_audio_end_ms': firstTeams,
          'map_sufficient_ms': session['map_sufficient_ms'],
          'teams_sufficient_ms': session['teams_sufficient_ms'],
          'map_confirmed_windows': mapConfirmations, 'map_wrong_windows': wrongMap,
          'team_confirmed_windows': teamConfirmations, 'team_wrong_windows': wrongTeams,
          'map_end': c.scene.map, 'teams_end': List<String>.from(c.scene.teams),
          'traces': traces,
        });
      } finally {
        c.dispose();
      }
    }
    File(output).writeAsStringSync(const JsonEncoder.withIndent('  ').convert({
      'complete': true, 'sessions': reports, 'event_count': events,
      'new_model_requests': 0, 'contract_errors': errors,
      'source': 'Frozen12-session diagnostic;10 synthetic +2 observed cached variants',
      'independent_quality_acceptance': false,
      'timing': 'Audio/virtual clocks only; no new ASR or physical paint measurement',
    }));
    expect(events, lessThanOrEqualTo(120));
    expect(reports, hasLength(12));
    expect(errors, isEmpty);
  });
}

// Opt-in local audio development evaluator. Ordinary test runs are read-only.
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/platform/engine.g.dart';
import 'v020_session_integration_test.dart'
    show RecordingHintHost, ReplayController;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final directory = Platform.environment['OPENCAPTION_CS_EVAL'];
  test(
    'actual CS corpus and controller drive fresh audio requests',
    () async {
      final out = Directory(directory!);
      final manifest =
          jsonDecode(File('${out.path}/manifest.json').readAsStringSync())
              as Map;
      final corpus = await CorpusIndex.load(rootBundle);
      File(
        '${out.path}/names.txt',
      ).writeAsStringSync(corpus.preservedIdentifiers().join('\n'));
      final report = File('${out.path}/display.jsonl');
      if (report.existsSync()) {
        throw StateError('Existing evidence; no implicit retry');
      }
      var sequence = 0;
      for (final arm in manifest['arms'] as List) {
        for (final source in manifest['sources'] as List) {
          final hosts = <String, RecordingHintHost>{};
          final controllers = <String, ReplayController>{};
          try {
            for (final style in ['standard', 'natural', 'community']) {
              final host = RecordingHintHost();
              final controller = ReplayController(host);
              controller.corpus = corpus;
              controller.corpusProfile = arm == 'cs2_auto'
                  ? CorpusProfile.cs2
                  : CorpusProfile.none;
              controller.initialized = true;
              controller.phase = SessionPhase.listening;
              controller.autoTermHints = arm == 'cs2_auto';
              hosts[style] = host;
              controllers[style] = controller;
            }
            for (final window in source['windows'] as List) {
              final proposed = hosts['standard']!.hints.last;
              final request = <String, dynamic>{
                'sequence': sequence,
                'arm': arm,
                'source_id': source['source_id'],
                ...Map<String, dynamic>.from(window as Map),
                'proposed_hints': proposed,
                'automatic': arm == 'cs2_auto',
              };
              final tag = sequence.toString().padLeft(4, '0');
              final command = File('${out.path}/commands/$tag.json');
              final temporary = File('${command.path}.tmp');
              temporary.writeAsStringSync(jsonEncode(request));
              temporary.renameSync(command.path);
              final responseFile = File('${out.path}/responses/$tag.json');
              final deadline = DateTime.now().add(const Duration(seconds: 120));
              while (!responseFile.existsSync()) {
                if (DateTime.now().isAfter(deadline)) {
                  throw StateError('Model response deadline $sequence');
                }
                await Future<void>.delayed(const Duration(milliseconds: 100));
              }
              final response =
                  jsonDecode(responseFile.readAsStringSync()) as Map;
              expect(response['sequence'], sequence);
              final displays = <String, Object?>{};
              for (final style in controllers.keys) {
                final c = controllers[style]!;
                final before = c.ledger.items.length;
                if (response['status'] == 'subtitle') {
                  final rendered = response['styles'][style] as Map;
                  c.bilingual(
                    BilingualEvent(
                      epoch: c.epoch,
                      window: window['window'] as int,
                      startMs: window['start_ms'] as int,
                      endMs: window['end_ms'] as int,
                      english: response['english'] as String,
                      chinese: rendered['chinese'] as String,
                      appliedHints: response['applied_hints'] as String,
                    ),
                  );
                } else if (response['status'] == 'invalid') {
                  c.gap(
                    c.epoch,
                    window['start_ms'] as int,
                    window['end_ms'] as int,
                  );
                }
                displays[style] = {
                  'items_added': c.ledger.items.length - before,
                  'chinese': c.ledger.items.length > before
                      ? c.ledger.items.last.chinese
                      : '',
                  'status': c.ledger.items.length > before
                      ? c.ledger.items.last.status.name
                      : 'no_speech',
                };
                expect(hosts[style]!.hints.last, hosts['standard']!.hints.last);
                expect(
                  CorpusIndex.estimateHintTokens(hosts[style]!.hints.last),
                  lessThanOrEqualTo(96),
                );
              }
              report.writeAsStringSync(
                '${jsonEncode({...request, ...Map<String, dynamic>.from(response), 'display': displays, 'next_hints': hosts['standard']!.hints.last, 'inferred_map': controllers['standard']!.scene.map, 'inferred_teams': controllers['standard']!.scene.teams})}\n',
                mode: FileMode.append,
              );
              sequence++;
            }
          } finally {
            for (final c in controllers.values) {
              c.dispose();
            }
          }
        }
      }
      expect(sequence, manifest['request_budget']);
      File(
        '${out.path}/controller_complete.json',
      ).writeAsStringSync(jsonEncode({'requests': sequence}));
    },
    skip: directory == null,
    timeout: const Timeout(Duration(minutes: 25)),
  );
}

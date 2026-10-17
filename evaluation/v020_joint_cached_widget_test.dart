// Replay only already generated smoke events; never load/invoke a model.
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
import '../test/v020_session_integration_test.dart'
    show RecordingHintHost, ReplayController;

void main() {
  testWidgets('cached real pressure events diagnose chronological visibility', (
    tester,
  ) async {
    final c = ReplayController(RecordingHintHost());
    await tester.runAsync(() async {
      c.corpus = await CorpusIndex.load(rootBundle);
      c.models.catalog =
          (jsonDecode(await rootBundle.loadString('assets/models.json'))
                  as List)
              .map((x) => ModelSpec(Map<String, dynamic>.from(x as Map)))
              .toList();
    });
    c.asrId = 'gemma-4-e2b-litert';
    c.initialized = true;
    c.corpusProfile = CorpusProfile.cs2;
    c.phase = SessionPhase.listening;
    tester.view.physicalSize = const Size(390, 780);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(c.dispose);
    await tester.pumpWidget(OpenCaptionApp(controller: c));
    final rows = File(
      'evaluation/results/v020-independent/joint_live_smoke_fixed_model.jsonl',
    ).readAsLinesSync().map((x) => jsonDecode(x) as Map).toList();
    var audio = 0;
    final records = <Map>[];
    for (final row in rows) {
      if (row['type'] == 'capture_event') {
        final f = row['fields'] as List;
        if (row['event'] == 'ACT') {
          audio = int.parse(f[0] as String);
          c.activity(c.epoch, 0, false, audio);
          if (audio == 10000) {
            c.correctScene(map: 'Nuke');
          }
          if (audio == 20000) {
            c.correctScene(
              map: 'Nuke',
              team1: c.corpus.canonicalTeam('FaZe'),
              team2: c.corpus.canonicalTeam('NAVI'),
            );
          }
          if (audio == 30000) {
            c.restoreAutomaticScene();
          }
        } else if (row['event'] == 'GAP') {
          c.gap(c.epoch, int.parse(f[1] as String), int.parse(f[2] as String));
        }
      } else if (row['type'] == 'result' && row['status'] == 'subtitle') {
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
        await tester.pump(const Duration(milliseconds: 16));
        await tester.pump(const Duration(milliseconds: 300));
        await tester.pumpAndSettle(
          const Duration(milliseconds: 100),
          EnginePhase.sendSemanticsUpdate,
          const Duration(seconds: 5),
        );
        expect(tester.takeException(), isNull);
        final caption = c.ledger.items.lastWhere(
          (x) => x.status != CaptionStatus.gap && x.startMs == row['start_ms'],
        );
        final visible = find.text(caption.english).evaluate().isNotEmpty;
        records.add({
          'window': row['window'],
          'audio_now': audio,
          'source_end': row['end_ms'],
          'visible_at_arrival': visible,
          'scroll_offset': tester
              .widget<ListView>(find.byType(ListView))
              .controller!
              .offset,
          'scroll_max': tester
              .widget<ListView>(find.byType(ListView))
              .controller!
              .position
              .maxScrollExtent,
          'ledger': c.ledger.items
              .map(
                (x) => {
                  'start': x.startMs,
                  'end': x.endMs,
                  'status': x.status.name,
                  'english': x.english,
                },
              )
              .toList(),
        });
        File(
          'evaluation/results/v020-independent/joint_live_cached_visibility.json',
        ).writeAsStringSync(
          const JsonEncoder.withIndent('  ').convert(records),
        );
        if (!visible) {
          await tester.scrollUntilVisible(
            find.text(caption.english),
            100,
            scrollable: find
                .descendant(
                  of: find.byType(ListView),
                  matching: find.byType(Scrollable),
                )
                .first,
            maxScrolls: 40,
          );
          await tester.pumpAndSettle();
          expect(find.text(caption.english), findsWidgets);
          expect(find.text(caption.chinese), findsWidgets);
        }
      }
      await tester.pump();
    }
    File(
      'evaluation/results/v020-independent/joint_live_cached_visibility.json',
    ).writeAsStringSync(const JsonEncoder.withIndent('  ').convert(records));
    expect(records, hasLength(4));
    await tester.pumpWidget(const SizedBox());
  });
}

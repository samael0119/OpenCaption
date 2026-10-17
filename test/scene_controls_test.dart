import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/local_preview.dart';
import 'package:opencaption/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  Future<PreviewController> controller(String theme) async {
    final c = PreviewController();
    c.corpus = await CorpusIndex.load(rootBundle);
    c.corpusProfile = CorpusProfile.cs2;
    c.initialized = true;
    c.phase = SessionPhase.listening;
    c.theme = theme;
    return c;
  }

  for (final theme in ['dark', 'light']) {
    testWidgets(
      '$theme optional correction is reachable at 320px with large text',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        tester.platformDispatcher.textScaleFactorTestValue = 1.5;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final c = (await tester.runAsync(() => controller(theme)))!;
        addTearDown(c.dispose);
        await tester.pumpWidget(OpenCaptionApp(controller: c));
        await tester.tap(find.byType(ExpansionTile));
        await tester.pumpAndSettle(
          const Duration(milliseconds: 100),
          EnginePhase.sendSemanticsUpdate,
          const Duration(seconds: 5),
        );
        expect(find.text('场景纠正'), findsOneWidget);
        final field = find.byWidgetPredicate(
          (w) =>
              w is DropdownButtonFormField<String> &&
              w.key.toString().contains('scene-map'),
        );
        expect(MediaQuery.textScalerOf(tester.element(field)).scale(16), 24);
        await tester.tap(field);
        await tester.pumpAndSettle(
          const Duration(milliseconds: 100),
          EnginePhase.sendSemanticsUpdate,
          const Duration(seconds: 5),
        );
        await tester.scrollUntilVisible(
          find.text('Nuke'),
          80,
          scrollable: find.byType(Scrollable).last,
          maxScrolls: 20,
        );
        await tester.pumpAndSettle(
          const Duration(milliseconds: 100),
          EnginePhase.sendSemanticsUpdate,
          const Duration(seconds: 5),
        );
        await tester.tap(find.text('Nuke').last);
        await tester.pumpAndSettle(
          const Duration(milliseconds: 100),
          EnginePhase.sendSemanticsUpdate,
          const Duration(seconds: 5),
        );
        expect(c.manualMap, 'Nuke');
        expect(find.textContaining('Nuke（已纠正）'), findsOneWidget);
        await tester.tap(find.text('恢复自动'));
        await tester.pumpAndSettle(
          const Duration(milliseconds: 100),
          EnginePhase.sendSemanticsUpdate,
          const Duration(seconds: 5),
        );
        expect(c.manualMap, isNull);
        expect(tester.takeException(), isNull);
        expect(find.text('暂停'), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      },
    );
  }
}

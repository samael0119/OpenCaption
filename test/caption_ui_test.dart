import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/appearance.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/local_preview.dart';
import 'package:opencaption/main.dart';
import 'package:opencaption/models/model_store.dart';
import 'package:opencaption/widgets/caption_transcript.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  Future<PreviewController> controller(String theme) async {
    final c = PreviewController();
    c.corpus = await CorpusIndex.load(rootBundle);
    c.models.catalog =
        (jsonDecode(await rootBundle.loadString('assets/models.json')) as List)
            .map((json) => ModelSpec(Map<String, dynamic>.from(json as Map)))
            .toList();
    c.asrId = 'gemma-4-e2b-litert';
    c.initialized = true;
    c.fontSize = 36;
    c.theme = theme;
    c.phase = SessionPhase.listening;
    for (var i = 0; i < 12; i++) {
      append(c, i);
    }
    return c;
  }

  test('chosen subtitle colors remain readable on both Material surfaces', () {
    for (final surface in [const Color(0xfff4faf8), const Color(0xff0e1512)]) {
      for (final preferred in SubtitleColor.values) {
        final result = captionTextColor(Color(preferred.argb), surface);
        final a = result.computeLuminance(), b = surface.computeLuminance();
        expect(
          (math.max(a, b) + .05) / (math.min(a, b) + .05),
          greaterThanOrEqualTo(4.5),
        );
      }
    }
  });

  for (final theme in ['dark', 'light']) {
    testWidgets(
      '$theme large type and four speech tasks wrap without overflow',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final c = (await tester.runAsync(() => controller(theme)))!;
        for (final task in ['bilingual', 'english', 'chinese', 'auto_zh']) {
          c.captionTask = task;
          await tester.pumpWidget(OpenCaptionApp(controller: c));
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          expect(find.text('结束'), findsOneWidget);
        }
        await tester.pumpWidget(const SizedBox());
        c.dispose();
      },
    );
  }

  testWidgets('320px at 1.5 system text scale keeps subtitle controls usable', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.5;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final c = (await tester.runAsync(() => controller('dark')))!;
    await tester.pumpWidget(OpenCaptionApp(controller: c));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('暂停'));
    await tester.pumpAndSettle();
    expect(find.text('继续'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('继续'));
    await tester.pumpAndSettle();
    expect(find.text('暂停'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    c.dispose();
  });

  testWidgets(
    'reading history keeps position when new caption arrives and controls stay reachable',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final c = (await tester.runAsync(() => controller('dark')))!;
      await tester.pumpWidget(OpenCaptionApp(controller: c));
      await tester.pumpAndSettle();
      final list = find.byType(ListView);
      await tester.drag(list, const Offset(0, 300));
      await tester.pumpAndSettle();
      final scroll = tester.widget<ListView>(list).controller!;
      final before = scroll.offset;
      append(c, 12);
      c.notifyListeners();
      await tester.pumpAndSettle();
      expect(scroll.offset, closeTo(before, 1));
      expect(find.textContaining('回到最新'), findsOneWidget);
      await tester.tap(find.text('暂停'));
      await tester.pumpAndSettle();
      expect(find.text('继续'), findsOneWidget);
      await tester.tap(find.text('继续'));
      await tester.pumpAndSettle();
      expect(find.text('暂停'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      c.dispose();
    },
  );
  testWidgets('mouse wheel review stays put and return latest restores follow', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final c = (await tester.runAsync(() => controller('dark')))!;
    await tester.pumpWidget(OpenCaptionApp(controller: c));
    await tester.pumpAndSettle();
    final list = find.byType(ListView);
    final scroll = tester.widget<ListView>(list).controller!;
    final initially = scroll.offset;
    await tester.sendEventToBinding(PointerScrollEvent(
      position: tester.getCenter(list), scrollDelta: const Offset(0, -300),
    ));
    await tester.pumpAndSettle();
    final reviewed = scroll.offset;
    expect(reviewed, lessThan(initially));
    append(c, 12);
    c.notifyListeners();
    await tester.pumpAndSettle();
    expect(scroll.offset, closeTo(reviewed, 1));
    expect(find.textContaining('回到最新'), findsOneWidget);
    await tester.tap(find.textContaining('回到最新'));
    await tester.pumpAndSettle();
    expect(scroll.offset, closeTo(scroll.position.maxScrollExtent, 1));
    expect(find.textContaining('回到最新'), findsNothing);
    final latestBeforeAppend = scroll.offset;
    append(c, 13);
    c.notifyListeners();
    await tester.pumpAndSettle();
    // Lazy variable-height rows can revise the extent during animation.
    // Verify the follow decision and movement, not an estimated extent.
    expect(scroll.offset, greaterThan(latestBeforeAppend));
    expect(find.textContaining('回到最新'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    c.dispose();
  });

}

void append(PreviewController c, int index) {
  final now = DateTime.now();
  final item = c.ledger.append(
    id: 'ui-$index',
    epoch: 0,
    startMs: index * 5000,
    endMs: (index + 1) * 5000,
    english:
        'Two players remain. The bomb is still outside, and the trade does not come through.',
    now: now,
  )!;
  c.ledger.start(item.id, 0, now);
  c.ledger.complete(item.id, 0, text: '还剩两名队员，炸弹仍在外场。时间只剩十二秒，队友没能完成补枪。');
}

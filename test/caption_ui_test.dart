import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/appearance.dart';
import 'package:opencaption/core/build_config.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/local_preview.dart';
import 'package:opencaption/main.dart';
import 'package:opencaption/models/model_store.dart';
import 'package:opencaption/platform/engine.g.dart';
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

  testWidgets('diagnostics report a painted bilingual row once', (
    tester,
  ) async {
    final c = (await tester.runAsync(() => controller('dark')))!;
    c.ledger.clear();
    c.showEnglish = true;
    final reports = <Map<Object?, Object?>>[];
    const channel = MethodChannel('dev.opencaption/playback');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'captionTiming') {
        reports.add(call.arguments as Map<Object?, Object?>);
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    await tester.pumpWidget(OpenCaptionApp(controller: c));
    c.bilingual(
      BilingualEvent(
        epoch: c.epoch,
        window: 7,
        startMs: 0,
        endMs: 5000,
        english: 'They are going B.',
        chinese: '他们要去 B 点。',
      ),
    );
    expect(reports.map((report) => report['stage']), ['controller']);
    await tester.pumpAndSettle();
    expect(reports.map((report) => report['stage']), [
      'controller',
      'flutter_paint',
    ]);
    expect(reports.last, containsPair('window', 7));
    expect(reports.last, containsPair('source', true));
    expect(reports.last, containsPair('translation', true));
    await tester.pumpWidget(OpenCaptionApp(controller: c));
    await tester.pumpAndSettle();
    expect(reports, hasLength(2));
    await tester.pumpWidget(const SizedBox());
    c.dispose();
  }, skip: !diagnosticsEnabled);

  testWidgets('Gemma preview is replaced by the final caption or cleared', (
    tester,
  ) async {
    final c = (await tester.runAsync(() => controller('dark')))!;
    c.ledger.clear();
    c.playbackAudio = true;
    final overlays = <String>[];
    const channel = MethodChannel('dev.opencaption/playback');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'subtitle') {
        overlays.add((call.arguments as Map)['text'] as String);
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    await tester.pumpWidget(OpenCaptionApp(controller: c));

    void preview(int window, String text, {bool closed = false, int? epoch}) {
      c.recognition(
        RecognitionEvent(
          epoch: epoch ?? c.epoch,
          window: window,
          revision: closed ? 1 : 0,
          startMs: 0,
          endMs: 5000,
          text: text,
          finalResult: closed,
        ),
      );
    }

    preview(7, 'They are going A.');
    await tester.pumpAndSettle();
    expect(find.text('临时英文：They are going A.'), findsOneWidget);
    expect(c.ledger.items, isEmpty);
    expect(overlays, ['They are going A.']);

    c.bilingual(
      BilingualEvent(
        epoch: c.epoch,
        window: 7,
        startMs: 0,
        endMs: 5000,
        english: 'They are going B.',
        chinese: '他们要去 B 点。',
      ),
    );
    preview(7, 'They are going A.');
    preview(8, 'Previous session.', epoch: c.epoch - 1);
    await tester.pumpAndSettle();
    expect(find.text('临时英文：They are going A.'), findsNothing);
    expect(find.text('They are going B.'), findsOneWidget);
    expect(c.ledger.items, hasLength(1));
    expect(overlays.last, 'They are going B.\n他们要去 B 点。');

    preview(8, 'This preview will be withdrawn.');
    await tester.pumpAndSettle();
    expect(c.e2eSourcePreview, 'This preview will be withdrawn.');
    preview(8, '', closed: true);
    preview(8, 'This preview will be withdrawn.');
    await tester.pumpAndSettle();
    expect(c.e2eSourcePreview, isEmpty);
    expect(c.ledger.items, hasLength(1));
    expect(overlays.last, isEmpty);
    c.phase = SessionPhase.pausing;
    preview(9, 'Late after pause.');
    expect(c.e2eSourcePreview, isEmpty);
    expect(overlays.last, isEmpty);
    await tester.pumpWidget(const SizedBox());
    c.dispose();
  });

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
  testWidgets(
    'mouse wheel review stays put and return latest restores follow',
    (tester) async {
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
      await tester.sendEventToBinding(
        PointerScrollEvent(
          position: tester.getCenter(list),
          scrollDelta: const Offset(0, -300),
        ),
      );
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
    },
  );
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

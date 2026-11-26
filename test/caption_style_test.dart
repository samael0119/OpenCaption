import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/caption_style.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/local_preview.dart';
import 'package:opencaption/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('unknown saved style falls back to the existing standard behavior', () {
    expect(CaptionStyle.fromId('unknown'), CaptionStyle.standard);
    expect(CaptionStyle.fromId(null), CaptionStyle.standard);
  });

  for (final theme in [ThemeData.light(), ThemeData.dark()]) {
    testWidgets(
      'style and nickname choices work at 320px with large text ${theme.brightness}',
      (tester) async {
        tester.view.physicalSize = const Size(320, 800);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 1.5;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final calls = <MethodCall>[];
        const channel = MethodChannel('dev.opencaption/playback');
        tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          channel,
          (call) async {
            calls.add(call);
            return null;
          },
        );
        addTearDown(
          () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
            channel,
            null,
          ),
        );
        final c = PreviewController();
        c.corpus = CorpusIndex.fromPacks(const []);
        await tester.pumpWidget(
          MaterialApp(
            theme: theme,
            home: SettingsPage(controller: c),
          ),
        );
        final dropdown = find.byType(DropdownButtonFormField<CaptionStyle>);
        await tester.ensureVisible(dropdown);
        await tester.tap(dropdown);
        await tester.pumpAndSettle();
        await tester.tap(find.text(CaptionStyle.community.label).last);
        await tester.pumpAndSettle();
        expect(c.captionStyle, CaptionStyle.community);
        expect(c.communityNicknames, isTrue);
        expect(calls.last.method, 'captionStyle');
        expect(calls.last.arguments, {'style': 'community', 'nicknames': true});
        final toggle = find.widgetWithText(SwitchListTile, '选手使用中文社区外号');
        await tester.ensureVisible(toggle);
        await tester.tap(toggle);
        await tester.pumpAndSettle();
        expect(c.communityNicknames, isFalse);
        expect(c.captionStyle, CaptionStyle.community);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
        c.dispose();
      },
    );
  }
}

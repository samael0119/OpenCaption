import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/session_controller.dart';

class BrokenCorpusBundle extends CachingAssetBundle {
  BrokenCorpusBundle({this.missing = false});
  final bool missing;
  @override
  Future<ByteData> load(String key) async =>
      throw FlutterError('missing test asset');
  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    if (missing) throw FlutterError('missing test asset');
    if (key.endsWith('manifest.json')) {
      return jsonEncode({
        'schema_version': 1,
        'packs': [
          {'asset': 'invalid.json'},
        ],
      });
    }
    return jsonEncode({
      'schema_version': 1,
      'terms': [
        {'english': 'save', 'chinese': '保枪', 'hint_sources': []},
      ],
    });
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
          (_) async => null,
        );
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
          null,
        );
  });

  test(
    'missing or invalid corpus falls back and asset repair restores requested selection',
    () async {
      for (final broken in [
        BrokenCorpusBundle(),
        BrokenCorpusBundle(missing: true),
      ]) {
        final c = SessionController()..corpusProfile = CorpusProfile.cs2;
        try {
          await c.loadCorpusAssets(broken);
          expect(c.corpusLoadFailed, true);
          expect(c.initializationFailed, false);
          expect(c.corpusProfile, CorpusProfile.none);
          expect(c.autoTermHints, false);
          expect(c.corpus.termCount, 0);
          expect(c.message, '词库暂不可用，已切换到通用字幕');
          await c.savePreferences();
          final prefs = await SharedPreferences.getInstance();
          expect(prefs.getString('corpusProfile'), 'cs2');
          expect(prefs.getBool('autoTermHints'), true);
          await c.loadCorpusAssets(rootBundle);
          expect(c.corpusLoadFailed, false);
          expect(c.corpusProfile, CorpusProfile.cs2);
          expect(c.autoTermHints, true);
          expect(c.message, isEmpty);
        } finally {
          c.dispose();
        }
      }
    },
  );

  test(
    'an explicit opt-out survives failure and successful asset repair',
    () async {
      final c = SessionController()..corpusProfile = CorpusProfile.cs2;
      c.autoTermHints = false;
      try {
        await c.loadCorpusAssets(BrokenCorpusBundle());
        await c.loadCorpusAssets(rootBundle);
        expect(c.corpusProfile, CorpusProfile.cs2);
        expect(c.autoTermHints, false);
        await c.loadCorpusAssets(BrokenCorpusBundle());
        c.corpusProfile = CorpusProfile.none;
        await c.loadCorpusAssets(rootBundle);
        expect(c.corpusProfile, CorpusProfile.none);
        expect(c.autoTermHints, false);
      } finally {
        c.dispose();
      }
    },
  );

  test(
    'asset reload cannot reset scene or hints while capture is active',
    () async {
      final c = SessionController()..phase = SessionPhase.listening;
      try {
        expect(c.loadCorpusAssets(BrokenCorpusBundle()), throwsStateError);
        expect(c.corpusLoadFailed, false);
      } finally {
        c.dispose();
      }
    },
  );
}

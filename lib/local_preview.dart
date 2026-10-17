// Explicit local visual preview; never invokes native capture or inference.
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'core/captions.dart';
import 'core/corpus.dart';
import 'core/session_controller.dart';
import 'models/model_store.dart';
import 'main.dart' show OpenCaptionApp;

class PreviewController extends SessionController {
  @override
  String get backendFlavor => 'gemmaE2E';
  @override
  Future<void> savePreferences() async => notifyListeners();
  @override
  Future<void> start() async {
    phase = SessionPhase.listening;
    notifyListeners();
  }

  @override
  Future<void> pause() async {
    phase = SessionPhase.paused;
    notifyListeners();
  }

  @override
  Future<void> resume() async {
    phase = SessionPhase.listening;
    notifyListeners();
  }

  @override
  Future<void> end() async {
    phase = SessionPhase.ended;
    notifyListeners();
  }

  @override
  void clearReview() {
    super.clearReview();
    message = '本机界面预览 · 示例字幕';
    notifyListeners();
  }
}

Future<void> main() async {
  if (!const bool.fromEnvironment('OPENCAPTION_LOCAL_PREVIEW')) {
    throw StateError('Local preview requires explicit build flag');
  }
  WidgetsFlutterBinding.ensureInitialized();
  final c = PreviewController();
  c.corpus = await CorpusIndex.load(rootBundle);
  c.models.catalog =
      (jsonDecode(await rootBundle.loadString('assets/models.json')) as List)
          .map((value) => ModelSpec(Map<String, dynamic>.from(value as Map)))
          .toList();
  c.asrId = 'gemma-4-e2b-litert';
  c.models.ready.add(c.asrId);
  c.corpusProfile = CorpusProfile.cs2;
  c.initialized = true;
  c.theme = Uri.base.queryParameters['theme'] ?? 'dark';
  c.fontSize = Uri.base.queryParameters['large'] == '1' ? 36 : 24;
  c.phase = Uri.base.queryParameters['home'] == '1'
      ? SessionPhase.idle
      : SessionPhase.listening;
  c.message = '本机界面预览 · 示例字幕';
  final now = DateTime.now();
  final samples = [
    [
      'FaZe hold their ground as NAVI move through lobby.',
      'FaZe 守住阵地，NAVI 正从大厅推进。',
    ],
    [
      'He drops into vent, but the trade does not come through.',
      '他跳进管道，但队友没能完成补枪。',
    ],
    [
      'They have two players alive and only twelve seconds left on the clock. The bomb is still outside.',
      '场上还剩两名队员，时间只剩十二秒。炸弹仍留在外场。',
    ],
  ];
  for (var i = 0; i < samples.length; i++) {
    final item = c.ledger.append(
      id: 'preview-$i',
      epoch: 0,
      startMs: i * 5000,
      endMs: (i + 1) * 5000,
      english: samples[i][0],
      now: now,
    )!;
    c.ledger.start(item.id, 0, now);
    c.ledger.complete(item.id, 0, text: samples[i][1]);
  }
  runApp(OpenCaptionApp(controller: c));
}

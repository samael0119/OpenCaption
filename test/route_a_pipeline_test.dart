import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/asr_normalizer.dart';
import 'package:opencaption/core/caption_style.dart';
import 'package:opencaption/core/captions.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/session_controller.dart';
import 'package:opencaption/core/translation.dart';
import 'package:opencaption/local_preview.dart';
import 'package:opencaption/main.dart';
import 'package:opencaption/models/model_store.dart';
import 'package:opencaption/platform/engine.g.dart';

class _RecordingHost extends EngineHost {
  final List<String> prompts = [];
  String reply = '他们正在向 B 点推进。';
  Future<String> Function(String text)? responder;

  @override
  Future<String> translate(
    int epoch,
    String id,
    String text,
    String payload,
  ) async {
    prompts.add(payload);
    if (responder != null) return responder!(text);
    return reply;
  }

  @override
  Future<void> pause() async {}

  @override
  Future<void> cancel() async {}

  int releaseCalls = 0;

  @override
  Future<void> release() async {
    releaseCalls++;
  }
}

class _GemmaTestController extends SessionController {
  _GemmaTestController(EngineHost host) : super(host: host);

  @override
  String get backendFlavor => 'gemmaE2E';

  @override
  Future<void> savePreferences() async => notifyListeners();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<List<ModelSpec>> loadCatalog() async =>
      (jsonDecode(await rootBundle.loadString('assets/models.json')) as List)
          .map((json) => ModelSpec(Map<String, dynamic>.from(json as Map)))
          .toList();

  test('assets/models.json includes curated ONNX ASR and HY-MT1.5 models', () async {
    final catalog = await loadCatalog();
    final ids = catalog.map((m) => m.id).toSet();
    expect(ids, containsAll([
      'gemma-4-e2b-litert',
      'gemma-4-e4b-litert',
      'parakeet-tdt-v3-int8',
      'sensevoice-small-int8',
      'hy-mt1.5-1.8b-q4',
    ]));
    expect(ids, isNot(contains('qwen2.5-0.5b-q4')));
    expect(ids, isNot(contains('qwen3.5-0.8b-q4')));
    expect(ids, isNot(contains('whisper-large-v3-turbo-q5')));
    expect(ids, isNot(contains('whisper-small-q5')));
    expect(ids, isNot(contains('whisper-base-q5')));

    final pk = catalog.firstWhere((m) => m.id == 'parakeet-tdt-v3-int8');
    expect(pk.kind, 'asr');
    expect(pk.recommended, isTrue);
    expect(pk.parts.map((p) => p.file), [
      'encoder.int8.onnx',
      'decoder.int8.onnx',
      'joiner.int8.onnx',
      'tokens.txt',
    ]);

    final sv = catalog.firstWhere((m) => m.id == 'sensevoice-small-int8');
    expect(sv.kind, 'asr');
    expect(sv.parts.map((p) => p.file), ['model.int8.onnx', 'tokens.txt']);
    expect(sv.parts.first.sources.first.id, 'modelscope');

    final hyMt = catalog.firstWhere((m) => m.id == 'hy-mt1.5-1.8b-q4');
    expect(hyMt.kind, 'translation');
    expect(hyMt.recommended, isTrue);
    expect(hyMt.runtimeSupported, isTrue);
    for (final id in [
      'sensevoice-small-int8',
      'hy-mt1.5-1.8b-q4',
    ]) {
      final spec = catalog.firstWhere((m) => m.id == id);
      expect(spec.sources.first.id, 'modelscope');
      expect(spec.sources.first.priority, 0);
    }
  });

  test('AsrPhoneticNormalizer fixes CS2 broadcast homophones and respects profile', () async {
    const sample =
        'Carrigan picks up the double orb through Maine on city side with U til for monastery and Shira.';
    expect(
      AsrPhoneticNormalizer.normalize(sample, profile: CorpusProfile.none),
      sample,
    );
    final fixed = AsrPhoneticNormalizer.normalize(
      sample,
      profile: CorpusProfile.cs2,
      activeTeams: const ['Spirit', 'Falcons'],
    );
    expect(fixed, contains('karrigan'));
    expect(fixed, contains('double AWP'));
    expect(fixed, contains('through Main'));
    expect(fixed, contains('CT side'));
    expect(fixed, contains('util'));
    expect(fixed, contains('m0NESY'));
    expect(fixed, contains('sh1ro'));

    final contextGated = AsrPhoneticNormalizer.normalize(
      'Shira hol looking for Money and magic on 3B2.',
      profile: CorpusProfile.cs2,
      activeTeams: const ['Spirit', 'Falcons'],
    );
    expect(contextGated, contains('sh1ro holding'));
    expect(contextGated, contains('m0NESY'));
    expect(contextGated, contains('magixx'));
    expect(contextGated, contains('3v2'));

    final expandedPros = AsrPhoneticNormalizer.normalize(
      "Monese's AWP finds Teneer while Hooxi, Kserato, Zantares, Boomich, Sjush and Spinks rotate.",
      profile: CorpusProfile.cs2,
    );
    expect(expandedPros, contains("m0NESY's"));
    expect(expandedPros, contains('tN1R'));
    expect(expandedPros, contains('HooXi'));
    expect(expandedPros, contains('KSCERATO'));
    expect(expandedPros, contains('XANTARES'));
    expect(expandedPros, contains('Boombl4'));
    expect(expandedPros, contains('sjuush'));
    expect(expandedPros, contains('Spinx'));

    final corpus = await CorpusIndex.load(rootBundle);
    expect(
      corpus.correctChinese(
        'Falcons push through Main as karrigan holds the big green.',
        '猎鹰队从缅因州推进，卡里根拿着绿色的大狺。',
        profile: CorpusProfile.cs2,
      ),
      'Falcons从A大推进，karrigan拿着大狙。',
    );
  });

  test('HY-MT1.5 prompt injects matched surface alias and custom A=B hint pairs', () async {
    await CaptionStyleRenderer.loadNicknames(rootBundle);
    final ctx = TranslationContext();
    final prompt = ctx.hyMtPrompt(
      'karrigan picks up the big green and throws util for a re-smoke.',
      const [
        {
          'english': 'AWP',
          'aliases': ['big green'],
          'chinese': '大狙',
          'preserve': false,
        },
        {
          'english': 'utility',
          'aliases': ['util'],
          'chinese': '道具',
          'preserve': false,
        },
      ],
      're-smoke=补烟, karrigan',
    );
    expect(prompt, contains('big green 翻译成 大狙'));
    expect(prompt, contains('util 翻译成 道具'));
    expect(prompt, contains('re-smoke 翻译成 补烟'));
    expect(prompt, contains('karrigan 翻译成 karrigan'));

    final naturalPrompt = ctx.hyMtPrompt(
      'karrigan holds the big green on B site.',
      const [
        {'english': 'karrigan', 'chinese': 'karrigan', 'preserve': true},
      ],
      '',
      style: CaptionStyle.natural,
      profile: CorpusProfile.cs2,
    );
    expect(naturalPrompt, contains('流畅口语化的中文CS2电竞解说字幕'));

    final communityPrompt = ctx.hyMtPrompt(
      'karrigan trades m0NESY after HooXi whiffs a full blind one tap on Mirage.',
      const [
        {'english': 'karrigan', 'chinese': 'karrigan', 'preserve': true},
        {'english': 'm0NESY', 'chinese': 'm0NESY', 'preserve': true},
      ],
      '',
      style: CaptionStyle.community,
      profile: CorpusProfile.cs2,
      communityNicknames: true,
      nicknameSeed: 0,
    );
    expect(communityPrompt, contains('生动接地气的中文CS社区解说风格'));
    expect(communityPrompt, contains('karrigan 翻译成 大表哥'));
    expect(communityPrompt, contains('m0NESY 翻译成 小孩'));
    expect(communityPrompt, contains('HooXi 翻译成 呼吸'));
    expect(communityPrompt, contains('whiff 翻译成 马枪'));
    expect(communityPrompt, contains('one tap 翻译成 一发入魂'));
    expect(communityPrompt, contains('full blind 翻译成 吃全白'));
    expect(communityPrompt, isNot(contains('karrigan 翻译成 karrigan')));

    // Multi-variant nicknames pick across variants and unknown/removed IDs pass through.
    final niko0 = CaptionStyleRenderer.matchedNicknames('NiKo ZywOo ropz huNter- Snax', seed: 0);
    final niko1 = CaptionStyleRenderer.matchedNicknames('NiKo ZywOo ropz huNter- Snax', seed: 1);
    final niko2 = CaptionStyleRenderer.matchedNicknames('NiKo ZywOo ropz huNter- Snax', seed: 2);
    expect(niko0['NiKo'], '尼公子');
    expect(niko1['NiKo'], '老尼');
    expect(niko0['ZywOo'], '载物');
    expect(niko1['ZywOo'], '载大哥');
    expect(niko2['ZywOo'], '大番薯');
    expect(niko0['ropz'], '肉铺子');
    expect(niko0['huNter-'], '表哥');
    expect(niko0.containsKey('Snax'), isFalse);
  });

  test('decoupled pipeline applies translation style and community nicknames to output', () async {
    final host = _RecordingHost()..reply = 'karrigan 获得了两次击杀，他们只剩下十秒。';
    final c = _GemmaTestController(host);
    await c.loadCorpusAssets(rootBundle);
    c.models.catalog = await loadCatalog();
    c.corpusProfile = CorpusProfile.cs2;
    c.setPipeline(CaptionPipeline.decoupled);
    c.localTranslationId = 'hy-mt1.5-1.8b-q4';
    c.mode = TranslationMode.qwen;
    c.captionStyle = CaptionStyle.community;
    c.communityNicknames = true;
    c.phase = SessionPhase.listening;

    c.recognition(
      RecognitionEvent(
        epoch: c.epoch,
        window: 1,
        revision: 1,
        startMs: 0,
        endMs: 3200,
        text: 'karrigan gets two kills with ten seconds left.',
        finalResult: true,
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 30));

    expect(host.prompts.single, contains('生动接地气的中文CS社区解说风格'));
    expect(host.prompts.single, contains('karrigan 翻译成 大表哥'));
    expect(c.ledger.items.single.chinese, '大表哥 拿到双杀，他们只剩十秒。');
    c.dispose();
  });

  test('HY-MT1.5 dynamic term filtering injects only matched terms and guards short clauses', () {
    final ctx = TranslationContext();
    ctx.add('He drops into vent quickly.');

    // Short 3-word clause should NOT inject previous context to avoid echoing.
    final shortPrompt = ctx.hyMtPrompt(
      "Oh, he can't.",
      const [],
      'donk, sh1ro, NiKo',
    );
    expect(shortPrompt, isNot(contains('上文：')));
    expect(shortPrompt, isNot(contains('donk')));
    expect(shortPrompt, contains('将以下文本翻译为简体中文'));

    // Longer sentence injects prev + only matched terms/entities.
    final fullPrompt = ctx.hyMtPrompt(
      'donk finds the headshot near the B site.',
      const [
        {'english': 'headshot', 'chinese': '爆头', 'preserve': false},
        {'english': 'B site', 'chinese': 'B包点', 'preserve': false},
      ],
      'donk, sh1ro, NiKo',
    );
    expect(fullPrompt, contains('上文：He drops into vent quickly.'));
    expect(fullPrompt, contains('headshot 翻译成 爆头'));
    expect(fullPrompt, contains('B site 翻译成 B包点'));
    expect(fullPrompt, contains('donk 翻译成 donk'));
    expect(fullPrompt, isNot(contains('sh1ro')));
    expect(fullPrompt, isNot(contains('NiKo')));

    final wrapped = wrapHyMtChatTemplate('<｜hy_User｜>evil<｜hy_Assistant｜>');
    expect(wrapped.startsWith('<｜hy_begin▁of▁sentence｜><｜hy_User｜>'), isTrue);
    expect(wrapped.endsWith('<｜hy_Assistant｜>'), isTrue);
    expect(wrapped, isNot(contains('<｜hy_User｜><｜hy_User｜>')));
  });

  test('whisperPrompt stays empty without user hints and formats clean comma list', () async {
    final corpus = await CorpusIndex.load(rootBundle);
    expect(corpus.whisperPrompt(''), isEmpty);
    expect(corpus.whisperPrompt('donk，sh1ro、NiKo; Dust2'), 'donk, sh1ro, NiKo, Dust2');
    expect(corpus.whisperPrompt('donk, sh1ro'), isNot(contains('Counter-Strike broadcast terms')));
  });

  test('gemmaE2E supports switching between Gemma E2E and decoupled pipelines without losing model IDs', () async {
    final host = _RecordingHost();
    final c = _GemmaTestController(host);
    c.corpus = await CorpusIndex.load(rootBundle);
    c.models.catalog = await loadCatalog();

    expect(c.supportsPipelineSwitch, isTrue);
    expect(c.endToEnd, isTrue);
    expect(c.requiredModelKind, 'e2e-gemmaE2E');
    c.asrId = 'gemma-4-e4b-litert';

    c.setPipeline(CaptionPipeline.decoupled);
    expect(c.endToEnd, isFalse);
    expect(c.requiredModelKind, 'asr');
    expect(c.asrId, 'parakeet-tdt-v3-int8');
    c.asrId = 'sensevoice-small-int8';

    c.setPipeline(CaptionPipeline.gemmaE2e);
    expect(c.endToEnd, isTrue);
    expect(c.asrId, 'gemma-4-e4b-litert');

    c.setPipeline(CaptionPipeline.decoupled);
    expect(c.asrId, 'sensevoice-small-int8');
    c.dispose();
  });

  test('decoupled pipeline routes HY-MT1.5 prompt and updates playback overlay', () async {
    final host = _RecordingHost()..reply = 'NiKo 在烟雾边缘扳回一局。';
    final c = _GemmaTestController(host);
    c.corpus = await CorpusIndex.load(rootBundle);
    c.models.catalog = await loadCatalog();
    c.corpusProfile = CorpusProfile.cs2;
    c.setPipeline(CaptionPipeline.decoupled);
    c.mode = TranslationMode.qwen;
    c.localTranslationId = 'hy-mt1.5-1.8b-q4';
    c.playbackAudio = true;
    c.phase = SessionPhase.listening;

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

    c.recognition(
      RecognitionEvent(
        epoch: c.epoch,
        window: 1,
        revision: 1,
        startMs: 0,
        endMs: 3200,
        text: 'NiKo finds a clawback at the edge of the smoke.',
        finalResult: true,
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 30));

    expect(host.prompts, hasLength(1));
    expect(
      host.prompts.single,
      startsWith('<｜hy_begin▁of▁sentence｜><｜hy_User｜>'),
    );
    expect(host.prompts.single, endsWith('<｜hy_Assistant｜>'));
    expect(c.ledger.items, hasLength(1));
    expect(c.ledger.items.single.status, CaptionStatus.ready);
    expect(c.ledger.items.single.chinese, 'NiKo 在烟雾边缘扳回一局。');
    expect(overlays.first, 'NiKo finds a clawback at the edge of the smoke.');
    expect(
      overlays.last,
      'NiKo finds a clawback at the edge of the smoke.\nNiKo 在烟雾边缘扳回一局。',
    );
    c.dispose();
  });

  test(
    'decoupled floating overlay still displays Chinese when ASR #2 arrives before MT #1 completes',
    () async {
      final firstGate = Completer<String>();
      final secondGate = Completer<String>();
      final host = _RecordingHost()
        ..responder = (text) => text.startsWith('First')
            ? firstGate.future
            : secondGate.future;
      final c = _GemmaTestController(host);
      c.corpus = await CorpusIndex.load(rootBundle);
      c.models.catalog = await loadCatalog();
      c.setPipeline(CaptionPipeline.decoupled);
      c.localTranslationId = 'hy-mt1.5-1.8b-q4';
      c.mode = TranslationMode.qwen;
      c.playbackAudio = true;
      c.phase = SessionPhase.listening;

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

      c.recognition(
        RecognitionEvent(
          epoch: c.epoch,
          window: 1,
          revision: 1,
          startMs: 0,
          endMs: 3000,
          text: 'First sentence arrives.',
          finalResult: true,
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 10));
      // Second ASR completes while first translation is still running.
      c.recognition(
        RecognitionEvent(
          epoch: c.epoch,
          window: 2,
          revision: 1,
          startMs: 3000,
          endMs: 6000,
          text: 'Second sentence arrives.',
          finalResult: true,
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 10));

      firstGate.complete('第一句到了。');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(overlays.last, 'First sentence arrives.\n第一句到了。');

      // Third ASR arrives after first translation is on screen; must not wipe
      // the bilingual overlay back to English-only before translation completes.
      c.recognition(
        RecognitionEvent(
          epoch: c.epoch,
          window: 3,
          revision: 1,
          startMs: 6000,
          endMs: 9000,
          text: 'Third sentence arrives.',
          finalResult: true,
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(overlays.last, 'First sentence arrives.\n第一句到了。');

      secondGate.complete('第二句到了。');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(overlays, contains('Second sentence arrives.\n第二句到了。'));
      c.dispose();
    },
  );

  test(
    'playback_stopped keeps translator loaded so retrying the interrupted last line succeeds',
    () async {
      final firstCall = Completer<String>();
      var attempts = 0;
      final host = _RecordingHost()
        ..responder = (_) {
          attempts++;
          if (attempts == 1) return firstCall.future;
          return Future.value('重试后的中文译文。');
        };
      final c = _GemmaTestController(host);
      c.corpus = await CorpusIndex.load(rootBundle);
      c.models.catalog = await loadCatalog();
      c.setPipeline(CaptionPipeline.decoupled);
      c.localTranslationId = 'hy-mt1.5-1.8b-q4';
      c.mode = TranslationMode.qwen;
      c.phase = SessionPhase.listening;

      c.recognition(
        RecognitionEvent(
          epoch: c.epoch,
          window: 1,
          revision: 1,
          startMs: 0,
          endMs: 3000,
          text: 'Last sentence before overlay stop.',
          finalResult: true,
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 10));

      c.interrupted(c.epoch, 'playback_stopped');
      firstCall.completeError(const TranslationFailure('translation_cancelled'));
      await Future<void>.delayed(const Duration(milliseconds: 30));

      expect(c.phase, SessionPhase.paused);
      expect(host.releaseCalls, 0);
      expect(c.ledger.items.single.status, CaptionStatus.failed);

      c.retryTranslation(c.ledger.items.single);
      await Future<void>.delayed(const Duration(milliseconds: 30));

      expect(c.ledger.items.single.status, CaptionStatus.ready);
      expect(c.ledger.items.single.chinese, '重试后的中文译文。');
      c.dispose();
    },
  );

  test('decoupled english-only task completes immediately without calling MT', () async {
    final host = _RecordingHost();
    final c = _GemmaTestController(host);
    c.corpus = await CorpusIndex.load(rootBundle);
    c.models.catalog = await loadCatalog();
    c.setPipeline(CaptionPipeline.decoupled);
    c.captionTask = 'english';
    c.phase = SessionPhase.listening;

    c.recognition(
      RecognitionEvent(
        epoch: c.epoch,
        window: 1,
        revision: 1,
        startMs: 0,
        endMs: 2500,
        text: 'They are rotating toward A site.',
        finalResult: true,
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 20));

    expect(host.prompts, isEmpty);
    expect(c.ledger.items, hasLength(1));
    expect(c.ledger.items.single.status, CaptionStatus.ready);
    expect(c.ledger.items.single.english, 'They are rotating toward A site.');
    c.dispose();
  });

  for (final theme in ['dark', 'light']) {
    testWidgets(
      'simplified home renders cleanly in $theme at 320px/1.5x and switches pipelines',
      (tester) async {
        tester.view.physicalSize = const Size(320, 640);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 1.5;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

        final c = PreviewController();
        c.corpus = await tester.runAsync(() => CorpusIndex.load(rootBundle))
            as CorpusIndex;
        c.models.catalog = (await tester.runAsync(loadCatalog))!;
        c.theme = theme;
        c.initialized = true;
        c.phase = SessionPhase.idle;

        await tester.pumpWidget(OpenCaptionApp(controller: c));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.text('离线实时字幕'), findsOneWidget);
        expect(find.text('开始字幕'), findsOneWidget);

        await tester.tap(find.text('听译分离'));
        await tester.pumpAndSettle();
        expect(c.pipeline, CaptionPipeline.decoupled);
        expect(find.text('语音识别模型'), findsOneWidget);
        expect(find.text('文本翻译模型'), findsOneWidget);
        expect(tester.takeException(), isNull);

        await tester.tap(find.text('端到端 Gemma'));
        await tester.pumpAndSettle();
        expect(c.pipeline, CaptionPipeline.gemmaE2e);
        expect(find.text('端到端语音模型'), findsOneWidget);
        expect(tester.takeException(), isNull);

        await tester.pumpWidget(const SizedBox());
        c.dispose();
      },
    );
  }
}

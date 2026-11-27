import 'dart:async';
import 'dart:collection';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/model_store.dart';
import '../platform/engine.g.dart';
import 'appearance.dart';
import 'asr_normalizer.dart';
import 'build_config.dart';
import 'captions.dart';
import 'caption_style.dart';
import 'corpus.dart';
import 'scene_assistant.dart';
import 'translation.dart';

class _RecentEnglish {
  _RecentEnglish(this.text, this.startMs, this.endMs);

  final String text;
  final int startMs, endMs;
}

class SessionController extends ChangeNotifier implements EngineEvents {
  static const _playback = MethodChannel('dev.opencaption/playback');
  bool playbackAudio = false;
  String captionTask = 'bilingual';
  CaptionStyle captionStyle = CaptionStyle.standard;
  bool communityNicknames = false;
  bool showChinese = true;
  CorpusProfile _corpusProfile = CorpusProfile.none;
  bool _autoTermHints = false;
  bool _corpusLoadFailed = false;
  static const _corpusFailureNotice = '词库暂不可用，已切换到通用字幕';
  bool get corpusLoadFailed => _corpusLoadFailed;
  final scene = SceneAssistant();
  final _hintedConcepts = <String>{};
  int _assistanceFloorMs = 0;
  int _recentClockMs = 0, _recentFloorMs = 0;
  String? _manualMap, _manualTeam1, _manualTeam2;
  String? get manualMap => _manualMap;
  String? get manualTeam1 => _manualTeam1;
  String? get manualTeam2 => _manualTeam2;
  bool get hasManualTeams => _manualTeam1 != null && _manualTeam2 != null;
  bool get hasSceneCorrection =>
      _manualMap != null || _manualTeam1 != null || _manualTeam2 != null;
  // The native flag controls automatic domain-only verification windows.
  // Explicit corrections remain in every window; Dart automatic assistance
  // and actual-hint provenance stay enabled, including scene conflict checks.
  bool get _nativeAutomaticAssist =>
      autoTermHints && _manualMap == null && !hasManualTeams;
  bool get canCorrectScene =>
      initialized &&
      endToEnd &&
      autoTermHints &&
      (running || phase == SessionPhase.paused);
  String? get assistanceMap => autoTermHints ? _manualMap ?? scene.map : null;
  List<String> get assistanceTeams => !autoTermHints
      ? const []
      : hasManualTeams
      ? List.unmodifiable([_manualTeam1!, _manualTeam2!])
      : scene.teams;
  bool get sceneCorrectionConflict =>
      autoTermHints &&
      ((_manualMap != null && scene.map != null && _manualMap != scene.map) ||
          (hasManualTeams &&
              scene.teams.length == 2 &&
              !scene.teams.toSet().containsAll([
                _manualTeam1!,
                _manualTeam2!,
              ])));

  void _clearManualScene() {
    _manualMap = _manualTeam1 = _manualTeam2 = null;
  }

  void correctScene({String? map, String? team1, String? team2}) {
    if (!canCorrectScene) throw StateError('Scene correction unavailable');
    if (map != null && !corpus.sceneChoices('map').contains(map)) {
      throw ArgumentError.value(map, 'map', 'Unknown map');
    }
    final first = team1 == null ? null : corpus.canonicalTeam(team1);
    final second = team2 == null ? null : corpus.canonicalTeam(team2);
    if ((team1 != null && first == null) ||
        (team2 != null && second == null) ||
        (first != null && first == second)) {
      throw ArgumentError('Choose two different known teams');
    }
    _manualMap = map;
    _manualTeam1 = first;
    _manualTeam2 = second;
    _resetAssistance(
      clearInjected: false,
      floorMs: max(_audioMs, _recentClockMs),
    );
    _updateEndToEndHints();
    notifyListeners();
  }

  void restoreAutomaticScene() {
    if (!canCorrectScene) throw StateError('Scene correction unavailable');
    correctScene();
  }

  CorpusProfile get corpusProfile =>
      _corpusLoadFailed ? CorpusProfile.none : _corpusProfile;
  set corpusProfile(CorpusProfile value) {
    _corpusProfile = value;
    _clearManualScene();
    // Selecting a library is the opt-in; no second required switch.
    _autoTermHints = value != CorpusProfile.none;
    _resetAssistance(floorMs: running ? max(_audioMs, _recentClockMs) : 0);
    if (initialized) _updateEndToEndHints();
  }

  bool get autoTermHints => _autoTermHints && !_corpusLoadFailed;
  set autoTermHints(bool value) {
    _autoTermHints = value && _corpusProfile != CorpusProfile.none;
    _clearManualScene();
    _resetAssistance(floorMs: running ? max(_audioMs, _recentClockMs) : 0);
    if (initialized) _updateEndToEndHints();
  }

  // Sticky 5-minute match memory for decoupled mode (unlike E2E's short 45s/90s
  // anti-pollution hint TTL, decoupled mode does not prompt-inject the ASR, so
  // keeping detected CS2 teams and map alive across a 5-minute match span makes
  // phonetic normalizers and map-specific callouts stay accurate).
  static const _decoupledContextTtlMs = 300000;
  final Map<String, int> _decoupledTeamSeenAt = {};
  String? _decoupledMap;
  int _decoupledMapSeenAt = 0;

  List<String> _activeDecoupledTeams(int nowMs) {
    _decoupledTeamSeenAt.removeWhere(
      (_, seenAt) => nowMs - seenAt > _decoupledContextTtlMs,
    );
    return List.unmodifiable(_decoupledTeamSeenAt.keys);
  }

  String? _activeDecoupledMap(int nowMs) {
    if (_decoupledMap != null && nowMs - _decoupledMapSeenAt > _decoupledContextTtlMs) {
      _decoupledMap = null;
    }
    return _manualMap ?? _decoupledMap;
  }

  void _observeDecoupledMatch(String text, int endMs) {
    if (corpusProfile != CorpusProfile.cs2) return;
    final matches = corpus.match(text, limit: 12, profile: corpusProfile);
    for (final term in matches) {
      final cat = term['category'];
      final name = term['english'] as String? ?? '';
      if (cat == 'team' && name.isNotEmpty) {
        _decoupledTeamSeenAt[name] = endMs;
        if (_decoupledTeamSeenAt.length > 3) {
          final oldest = _decoupledTeamSeenAt.entries.reduce(
            (a, b) => a.value <= b.value ? a : b,
          );
          _decoupledTeamSeenAt.remove(oldest.key);
        }
      } else if (cat == 'map' && corpus.isSceneMap(term) && name.isNotEmpty) {
        _decoupledMap = name;
        _decoupledMapSeenAt = endMs;
      }
    }
  }

  void _resetAssistance({bool clearInjected = true, int floorMs = 0}) {
    _assistanceFloorMs = floorMs;
    _recentEnglish.clear();
    _recentClockMs = _recentFloorMs = floorMs;
    _decoupledTeamSeenAt.clear();
    _decoupledMap = null;
    _decoupledMapSeenAt = 0;
    if (clearInjected) {
      _hintedConcepts.clear();
    }
    scene.reset(epoch);
  }

  double overlayBackgroundOpacity = .86;
  SubtitleColor sourceSubtitleColor = SubtitleColor.yellow;
  SubtitleColor translationSubtitleColor = SubtitleColor.green;
  // Kept as a source-color alias for callers compiled against the previous
  // single-color setting. New UI and persistence use the two explicit colors.
  @Deprecated('Use sourceSubtitleColor')
  SubtitleColor get subtitleColor => sourceSubtitleColor;
  @Deprecated('Use sourceSubtitleColor')
  set subtitleColor(SubtitleColor value) => sourceSubtitleColor = value;
  final Queue<_RecentEnglish> _recentEnglish = Queue<_RecentEnglish>();

  Future<void> _configureAudio() async {
    try {
      await _playback.invokeMethod<void>('task', {'task': captionTask});
      await applyCaptionStyle();
      if (playbackAudio) {
        await _playback.invokeMethod<void>('opacity', {
          'value': overlayBackgroundOpacity.clamp(.2, 1.0),
        });
        await _playback.invokeMethod<void>('colors', {
          'sourceArgb': sourceSubtitleColor.argb,
          'translationArgb': translationSubtitleColor.argb,
        });
        await applyFontSize(explicit: false);
      }
      await _playback.invokeMethod<void>(
        playbackAudio ? 'start' : 'microphone',
      );
    } on MissingPluginException {
      if (playbackAudio) rethrow;
    }
  }

  SessionController({EngineHost? host}) : host = host ?? EngineHost();
  final EngineHost host;
  final models = ModelStore();
  final ledger = CaptionLedger();
  final stable = StableText();
  final context = TranslationContext();
  final external = ExternalTranslator();
  final storage = const FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  final Map<String, int> metrics = {};
  final Map<String, String> _translationPayloads = {};
  final Map<String, int> _itemOrder = {};
  final Queue<String> _translationQueue = Queue<String>();
  String? _activeTranslationId;
  int _lastOverlayTranslatedOrder = -1;
  late CorpusIndex corpus;
  CaptionPipeline pipeline = CaptionPipeline.gemmaE2e;
  TranslationMode mode = TranslationMode.qwen;
  SessionPhase phase = SessionPhase.idle;
  String _e2eModelId = 'gemma-4-e2b-litert';
  String _decoupledAsrId = 'parakeet-tdt-v3-int8';
  String get asrId => endToEnd ? _e2eModelId : _decoupledAsrId;
  set asrId(String value) {
    if (endToEnd) {
      _e2eModelId = value;
    } else {
      _decoupledAsrId = value;
    }
  }

  String localTranslationId = 'hy-mt1.5-1.8b-q4',
      contextHint = '',
      message = '',
      sessionId = '';
  ServiceConfig service = const ServiceConfig();
  int epoch = 0, threads = 4, _segment = 0, _lastVoice = 0, _audioMs = 0;
  double level = 0, fontSize = 24;
  bool showEnglish = true, mlReady = false, initialized = false;
  bool initializationFailed = false;

  /// Compatibility alias for older integrations. The field is now a generic,
  /// bounded scene hint rather than a names-only input.
  @Deprecated('Use contextHint')
  String get names => contextHint;
  @Deprecated('Use contextHint')
  set names(String value) => contextHint = value;
  // Follow the device appearance unless the user explicitly chooses a theme.
  String theme = 'system';
  Timer? _ticker;
  DateTime? _startedAt;
  Future<void>? _stopping;
  final Map<int, int> _revisions = {};
  final Set<int> _closedWindows = {};
  RecognitionEvent? _e2ePreview;
  String get e2eSourcePreview {
    final preview = _e2ePreview;
    return running && showEnglish && preview != null && preview.epoch == epoch
        ? preview.text
        : '';
  }

  bool _needsPrepare = false;
  bool _releaseOnPause = false;
  bool get canConfigure =>
      phase == SessionPhase.idle || phase == SessionPhase.ended;
  bool get running =>
      phase == SessionPhase.listening || phase == SessionPhase.waiting;
  String get backendFlavor => appFlavor ?? 'cascade';
  bool get supportsPipelineSwitch => backendFlavor == 'gemmaE2E';
  bool get endToEnd =>
      backendFlavor == 'qwenE2E' ||
      (backendFlavor == 'gemmaE2E' && pipeline == CaptionPipeline.gemmaE2e);
  bool get _needsDecoupledTranslation =>
      captionTask != 'english' && captionTask != 'chinese';
  String get requiredModelKind => endToEnd ? 'e2e-$backendFlavor' : 'asr';
  bool get activeModelsReady {
    if (!models.ready.contains(asrId)) return false;
    if (endToEnd || !_needsDecoupledTranslation) return true;
    return switch (mode) {
      TranslationMode.qwen => models.ready.contains(localTranslationId),
      TranslationMode.mlKit => mlReady,
      TranslationMode.external => true,
    };
  }

  void setPipeline(CaptionPipeline value) {
    if (!supportsPipelineSwitch || pipeline == value) return;
    pipeline = value;
    _ensureValidModelSelections();
    notifyListeners();
  }

  void _ensureValidModelSelections() {
    if (models.catalog.isEmpty) return;
    final e2eKind = 'e2e-$backendFlavor';
    if (models.catalog.any((s) => s.kind == e2eKind) &&
        !models.catalog.any((s) => s.id == _e2eModelId && s.kind == e2eKind)) {
      _e2eModelId = models.catalog
          .firstWhere((s) => s.kind == e2eKind)
          .id;
    }
    if (!models.catalog.any(
      (s) => s.id == _decoupledAsrId && s.kind == 'asr',
    )) {
      _decoupledAsrId = models.catalog.any((s) => s.id == 'parakeet-tdt-v3-int8')
          ? 'parakeet-tdt-v3-int8'
          : models.catalog.any((s) => s.id == 'sensevoice-small-int8')
          ? 'sensevoice-small-int8'
          : models.catalog.firstWhere((s) => s.kind == 'asr').id;
    }
    if (!models.catalog.any(
      (m) =>
          m.id == localTranslationId &&
          m.kind == 'translation' &&
          m.runtimeSupported,
    )) {
      localTranslationId =
          models.catalog.any(
            (m) => m.id == 'hy-mt1.5-1.8b-q4' && m.runtimeSupported,
          )
          ? 'hy-mt1.5-1.8b-q4'
          : models.catalog
                .firstWhere((m) => m.kind == 'translation' && m.runtimeSupported)
                .id;
    }
  }

  String get selectedAsrLabel => models.catalog
      .firstWhere(
        (model) => model.id == asrId,
        orElse: () => models.catalog.first,
      )
      .label;
  ModelSpec get selectedLocalTranslation => models.catalog.firstWhere(
    (model) => model.id == localTranslationId,
    orElse: () => models.catalog.firstWhere((m) => m.kind == 'translation'),
  );
  String get translationLabel => endToEnd
      ? switch (captionTask) {
          'english' => '$selectedAsrLabel（仅英文转写）',
          'chinese' => '$selectedAsrLabel（仅中文转写）',
          'auto_zh' => '$selectedAsrLabel（原文＋中文）',
          _ => '$selectedAsrLabel（中英字幕）',
        }
      : !_needsDecoupledTranslation
      ? switch (captionTask) {
          'chinese' => '$selectedAsrLabel（仅中文转写）',
          _ => '$selectedAsrLabel（仅英文转写）',
        }
      : switch (mode) {
          TranslationMode.mlKit => 'ML Kit 英中端侧翻译（无上下文）',
          TranslationMode.qwen => '${selectedLocalTranslation.label}（动态术语）',
          TranslationMode.external =>
            service.model.trim().isEmpty
                ? '外部兼容 API（尚未配置模型）'
                : '外部兼容 API · ${service.model.trim()}',
        };
  int get retryableTranslations =>
      ledger.items.where((item) => item.status == CaptionStatus.failed).length;

  Future<void> initialize() async {
    initializationFailed = false;
    notifyListeners();
    try {
      await _initialize();
    } catch (_) {
      initializationFailed = true;
      message = '初始化失败，请重试';
      notifyListeners();
    }
  }

  Future<void> _initialize() async {
    EngineEvents.setUp(this);
    _playback.setMethodCallHandler((call) async {
      if (call.method == 'overlayFontSizeChanged') {
        final value = (call.arguments as Map?)?['value'];
        if (value is num) {
          fontSize = value.toDouble().clamp(14, 36);
          notifyListeners();
          unawaited(savePreferences());
        }
      }
      return null;
    });
    await models.initialize();
    await loadCorpusAssets(rootBundle);
    final prefs = await SharedPreferences.getInstance();
    fontSize = (prefs.getDouble('fontSize') ?? 24).clamp(14, 36);
    try {
      final savedOverlaySize = await _playback.invokeMethod<double>(
        'getOverlayFontSize',
      );
      if (savedOverlaySize != null) {
        fontSize = savedOverlaySize.clamp(14, 36);
      }
    } catch (_) {}
    showEnglish = prefs.getBool('showEnglish') ?? true;
    showChinese = prefs.getBool('showChinese') ?? true;
    if (!showEnglish && !showChinese) showChinese = true;
    playbackAudio = prefs.getBool('playbackAudio') ?? false;
    contextHint = prefs.getString('contextHint') ?? '';
    corpusProfile = CorpusProfile.fromId(prefs.getString('corpusProfile'));
    // Legacy false was the old default, not evidence of an explicit opt-out.
    if (prefs.getBool('auxiliaryV020Initialized') == true) {
      autoTermHints = prefs.getBool('autoTermHints') ?? true;
    }
    overlayBackgroundOpacity =
        (prefs.getDouble('overlayBackgroundOpacity') ?? .86).clamp(.2, 1.0);
    final savedSourceColor = prefs.getString('sourceSubtitleColor');
    sourceSubtitleColor = SubtitleColor.fromId(
      savedSourceColor ?? prefs.getString('subtitleColor'),
      fallback: SubtitleColor.yellow,
    );
    translationSubtitleColor = SubtitleColor.fromId(
      prefs.getString('translationSubtitleColor') ?? 'green',
      fallback: SubtitleColor.green,
    );
    final savedCaptionTask = prefs.getString('captionTask');
    captionStyle = CaptionStyle.fromId(prefs.getString('captionStyle'));
    communityNicknames = prefs.getBool('communityNicknames') ?? false;
    captionTask =
        const {
          'bilingual',
          'auto_zh',
          'english',
          'chinese',
        }.contains(savedCaptionTask)
        ? savedCaptionTask!
        : 'bilingual';
    theme = prefs.getString('theme') ?? 'system';
    pipeline = supportsPipelineSwitch
        ? CaptionPipeline.fromId(prefs.getString('captionPipeline'))
        : (backendFlavor == 'qwenE2E'
              ? CaptionPipeline.gemmaE2e
              : CaptionPipeline.decoupled);
    mode = switch (prefs.getString('translationMode')) {
      'qwen' => TranslationMode.qwen,
      'mlKit' => TranslationMode.mlKit,
      'external' when externalTranslationEnabled => TranslationMode.external,
      _ => TranslationMode.qwen,
    };
    _e2eModelId =
        prefs.getString('e2eModelId') ??
        (backendFlavor == 'qwenE2E'
            ? 'qwen2.5-omni-3b-mnn'
            : 'gemma-4-e2b-litert');
    _decoupledAsrId =
        prefs.getString('decoupledAsrId') ??
        prefs.getString('asrId') ??
        'parakeet-tdt-v3-int8';
    localTranslationId =
        prefs.getString('localTranslationId') ?? 'hy-mt1.5-1.8b-q4';
    _ensureValidModelSelections();
    // Older builds could persist the external mode. Keep that preference
    // harmless while the feature is hidden from the current product UI.
    if (!externalTranslationEnabled && mode == TranslationMode.external) {
      mode = TranslationMode.qwen;
    }
    final savedThreads = prefs.getInt('threads');
    threads = const {2, 4, 6, 8}.contains(savedThreads) ? savedThreads! : 4;
    String key = '';
    try {
      key = await storage.read(key: 'external_api_key') ?? '';
    } catch (_) {
      message = '密钥存储不可用，请重新配置服务';
    }
    service = ServiceConfig(
      baseUrl: prefs.getString('baseUrl') ?? '',
      model: prefs.getString('model') ?? '',
      apiKey: key,
      allowLocalHttp: prefs.getBool('localHttp') ?? false,
      tokenBudget: prefs.getInt('tokenBudget') ?? 0,
    );
    try {
      mlReady = await host.mlKitReady();
    } catch (_) {
      message = '原生服务不可用，请在 Android 实机运行';
    }
    initialized = true;
    if (_corpusLoadFailed && !message.contains(_corpusFailureNotice)) {
      message = message.isEmpty
          ? _corpusFailureNotice
          : '$_corpusFailureNotice；$message';
    }
    _ticker = Timer.periodic(const Duration(milliseconds: 200), (_) => tick());
    notifyListeners();
  }

  Future<void> savePreferences() async {
    final p = await SharedPreferences.getInstance();
    await p.setDouble('fontSize', fontSize);
    await p.setBool('showEnglish', showEnglish);
    await p.setBool('showChinese', showChinese);
    await p.setBool('playbackAudio', playbackAudio);
    await p.setString('contextHint', contextHint);
    // A transient bad asset is not a user opt-out. Persist their requested
    // selection so a repaired bundle can restore it without another prompt.
    await p.setString('corpusProfile', _corpusProfile.id);
    await p.setBool('autoTermHints', _autoTermHints);
    await p.setBool('auxiliaryV020Initialized', true);
    await p.setDouble('overlayBackgroundOpacity', overlayBackgroundOpacity);
    await p.setString('sourceSubtitleColor', sourceSubtitleColor.id);
    await p.setString('translationSubtitleColor', translationSubtitleColor.id);
    // Keep the legacy key in sync so an older build does not lose the source
    // color if the user temporarily rolls back.
    await p.setString('subtitleColor', sourceSubtitleColor.id);
    await p.setString('captionTask', captionTask);
    await p.setString('captionStyle', captionStyle.name);
    await p.setBool('communityNicknames', communityNicknames);
    await p.setString('theme', theme);
    await p.setString('captionPipeline', pipeline.id);
    await p.setString('e2eModelId', _e2eModelId);
    await p.setString('decoupledAsrId', _decoupledAsrId);
    await p.setString('asrId', asrId);
    await p.setString('localTranslationId', localTranslationId);
    await p.setString(
      'translationMode',
      !externalTranslationEnabled && mode == TranslationMode.external
          ? TranslationMode.qwen.name
          : mode.name,
    );
    await p.setInt('threads', threads);
    await p.setString('baseUrl', service.baseUrl);
    await p.setString('model', service.model);
    await p.setBool('localHttp', service.allowLocalHttp);
    await p.setInt('tokenBudget', service.tokenBudget);
    try {
      await storage.write(key: 'external_api_key', value: service.apiKey);
    } catch (_) {}
    notifyListeners();
  }

  /// Load packaged data while idle; failed data must not block plain captions.
  /// Accepting a bundle keeps the same recovery path testable without devices.
  Future<void> loadCorpusAssets(AssetBundle bundle) async {
    if (!canConfigure) {
      throw StateError('cannot reload corpus during an active session');
    }
    try {
      corpus = await CorpusIndex.load(bundle);
      _corpusLoadFailed = false;
      if (message == _corpusFailureNotice) {
        message = '';
      } else if (message.startsWith('$_corpusFailureNotice；')) {
        message = message.substring(_corpusFailureNotice.length + 1);
      }
    } catch (_) {
      corpus = CorpusIndex.fromPacks(const []);
      _corpusLoadFailed = true;
      metrics['corpus_load_errors'] = (metrics['corpus_load_errors'] ?? 0) + 1;
      message = _corpusFailureNotice;
    }
    try {
      await CaptionStyleRenderer.loadNicknames(bundle);
    } catch (_) {}
    _resetAssistance(floorMs: _audioMs);
    _clearManualScene();
    if (initialized) _updateEndToEndHints();
    notifyListeners();
  }

  Future<void> start() async {
    if (!canConfigure) return;
    if (!models.ready.contains(asrId) ||
        (!endToEnd &&
            _needsDecoupledTranslation &&
            ((mode == TranslationMode.qwen &&
                    !models.ready.contains(localTranslationId)) ||
                (mode == TranslationMode.mlKit && !mlReady)))) {
      message = endToEnd
          ? '请先准备所选 Gemma 语音模型'
          : _needsDecoupledTranslation
          ? '请先准备所选语音识别与翻译模型'
          : '请先准备所选语音识别模型';
      notifyListeners();
      return;
    }
    if (!endToEnd &&
        _needsDecoupledTranslation &&
        mode == TranslationMode.external) {
      try {
        service.endpoint;
      } catch (_) {
        message = '请先配置并测试外部翻译服务';
        notifyListeners();
        return;
      }
    }
    phase = SessionPhase.preparing;
    message = '准备模型…';
    final e = ++epoch;
    _clearManualScene();
    _resetAssistance();
    notifyListeners();
    try {
      if (!await host.requestMicrophone()) {
        if (e != epoch) return;
        phase = SessionPhase.idle;
        message = '麦克风权限被拒绝，可前往系统设置';
        notifyListeners();
        return;
      }
      if (e != epoch) return;
      final preparation = Stopwatch()..start();
      final verification = Stopwatch()..start();
      await models.verifyForUse(asrId);
      if (!endToEnd &&
          _needsDecoupledTranslation &&
          mode == TranslationMode.qwen) {
        await models.verifyForUse(localTranslationId);
      }
      if (e != epoch) return;
      final verificationMs = verification.elapsedMilliseconds;
      await host.prepare(
        EngineConfig(
          asrPath: models.path(asrId),
          vadPath: '',
          translationPath:
              !endToEnd &&
                  _needsDecoupledTranslation &&
                  mode == TranslationMode.qwen
              ? models.path(localTranslationId)
              : '',
          mode: endToEnd
              ? 'e2e'
              : _needsDecoupledTranslation
              ? mode.name
              : 'asr_only',
          threads: threads,
          automaticAssist: _nativeAutomaticAssist,
          names: endToEnd
              ? _preparedHints()
              : corpus.whisperPrompt(contextHint),
        ),
      );
      if (e != epoch) return;
      final preparationMs = preparation.elapsedMilliseconds;
      _needsPrepare = _releaseOnPause = false;
      ledger.clear();
      stable.reset();
      context.clear();
      external.reset();
      _revisions.clear();
      _closedWindows.clear();
      _e2ePreview = null;
      _translationPayloads.clear();
      _itemOrder.clear();
      _translationQueue.clear();
      _activeTranslationId = null;
      _lastOverlayTranslatedOrder = -1;
      _recentEnglish.clear();
      metrics.clear();
      metrics['prepare_ms'] = preparationMs;
      metrics['verify_ms'] = verificationMs;
      _segment = _lastVoice = _audioMs = 0;
      sessionId = DateTime.now().microsecondsSinceEpoch.toString();
      if (backendFlavor == 'gemmaE2E') await _configureAudio();
      if (e != epoch) return;
      unawaited(
        _playback
            .invokeMethod<void>('startupTiming', {'verifyMs': verificationMs})
            .catchError((_) {}),
      );
      await host.start(epoch);
      if (e != epoch) return;
      _startedAt = DateTime.now();
      phase = SessionPhase.listening;
      message = '';
      notifyListeners();
    } catch (error) {
      if (e != epoch) return;
      phase = SessionPhase.idle;
      message = error is PlatformException && error.message != null
          ? error.message!
          : '准备失败，请检查模型完整性和音频采集权限';
      unawaited(host.release().catchError((_) {}));
      notifyListeners();
    }
  }

  Future<void> pause() {
    if (_stopping != null) return _stopping!;
    if (!running) return Future.value();
    _stopping = _pause().whenComplete(() => _stopping = null);
    return _stopping!;
  }

  Future<void> _pause() async {
    final e = epoch;
    phase = SessionPhase.pausing;
    _e2ePreview = null;
    level = 0;
    context.clear();
    notifyListeners();
    await host.pause();
    await host.cancel();
    if (e != epoch) return;
    external.cancelAll();
    _translationQueue.clear();
    ledger.cancelEpoch(e);
    stable.reset();
    context.clear();
    phase = SessionPhase.paused;
    if (_releaseOnPause) {
      _needsPrepare = true;
      _releaseOnPause = false;
      unawaited(host.release().catchError((_) {}));
    }
    notifyListeners();
  }

  Future<void> resume() async {
    if (phase != SessionPhase.paused) return;
    final e = ++epoch;
    phase = SessionPhase.preparing;
    notifyListeners();
    _lastVoice = _audioMs = 0;
    _revisions.clear();
    _closedWindows.clear();
    _resetAssistance();
    stable.reset();
    context.clear();
    ledger.gap(epoch, '暂停间隔 · 从当前声音继续', DateTime.now());
    _pruneTranslationState();
    try {
      if (_needsPrepare) {
        message = '重新加载模型…';
        notifyListeners();
        final preparation = Stopwatch()..start();
        await host.prepare(
          EngineConfig(
            asrPath: models.path(asrId),
            vadPath: '',
            translationPath:
                !endToEnd &&
                    _needsDecoupledTranslation &&
                    mode == TranslationMode.qwen
                ? models.path(localTranslationId)
                : '',
            mode: endToEnd
                ? 'e2e'
                : _needsDecoupledTranslation
                ? mode.name
                : 'asr_only',
            threads: threads,
            automaticAssist: _nativeAutomaticAssist,
            names: endToEnd
                ? _preparedHints()
                : corpus.whisperPrompt(contextHint),
          ),
        );
        if (e != epoch) return;
        metrics['prepare_ms'] = preparation.elapsedMilliseconds;
        _needsPrepare = false;
      }
      if (e != epoch) return;
      if (backendFlavor == 'gemmaE2E') await _configureAudio();
      if (e != epoch) return;
      if (endToEnd) {
        await host.updateHints(_preparedHints(), _nativeAutomaticAssist);
      }
      if (e != epoch) return;
      await host.start(e);
      if (e != epoch) return;
      phase = SessionPhase.listening;
      message = '';
    } catch (_) {
      if (e != epoch) return;
      phase = SessionPhase.paused;
      message = '恢复失败，请结束后重新开始';
    }
    notifyListeners();
  }

  Future<void> end() async {
    if (phase == SessionPhase.preparing) {
      epoch++;
      await host.cancel();
      _finishSessionMetrics();
      phase = SessionPhase.ended;
      unawaited(host.release().catchError((_) {}));
      notifyListeners();
      return;
    }
    if (_stopping != null) await _stopping;
    if (running) {
      phase = SessionPhase.pausing;
      _e2ePreview = null;
      level = 0;
      notifyListeners();
      await host.pause();
      await host.cancel();
      external.cancelAll();
      _translationQueue.clear();
      ledger.cancelEpoch(epoch);
    } else {
      await host.cancel();
      external.cancelAll();
      _translationQueue.clear();
    }
    stable.reset();
    context.clear();
    _finishSessionMetrics();
    phase = SessionPhase.ended;
    level = 0;
    message = retryableTranslations > 0 ? '部分译文失败，可在回看页重试' : '';
    notifyListeners();
  }

  void _finishSessionMetrics() {
    if (_startedAt == null) return;
    metrics['session_seconds'] = DateTime.now()
        .difference(_startedAt!)
        .inSeconds;
    _startedAt = null;
  }

  void clearReview() {
    epoch++;
    _e2ePreview = null;
    unawaited(host.release().catchError((_) {}));
    ledger.clear();
    _translationPayloads.clear();
    _itemOrder.clear();
    _translationQueue.clear();
    _lastOverlayTranslatedOrder = -1;
    _clearManualScene();
    _resetAssistance();
    phase = SessionPhase.idle;
    message = '';
    metrics.clear();
    notifyListeners();
  }

  /// Remove translation payloads and queued IDs whose visible caption was
  /// trimmed by the bounded ledger. The active request keeps its local
  /// payload and is allowed to finish normally.
  void _pruneTranslationState() {
    final liveIds = ledger.items.map((item) => item.id).toSet();
    _translationPayloads.removeWhere((id, _) => !liveIds.contains(id));
    _itemOrder.removeWhere((id, _) => !liveIds.contains(id));
    _translationQueue.removeWhere((id) => !liveIds.contains(id));
    metrics['translation_queue_depth'] = _translationQueue.length;
  }

  void _trimRecognitionState(int currentWindow) {
    // Recognition revisions only protect against late callbacks from recent
    // windows. Keeping a small rolling window prevents hours-long sessions
    // from growing these two maps/sets without bound.
    final oldestWindow = currentWindow - 256;
    _revisions.removeWhere((window, _) => window < oldestWindow);
    _closedWindows.removeWhere((window) => window < oldestWindow);
  }

  void tick() {
    final idle = running && _audioMs - _lastVoice >= 1500;
    final stillTranslating = ledger.items.any(
      (item) =>
          item.status == CaptionStatus.translating ||
          item.status == CaptionStatus.queued,
    );
    if (idle && !stillTranslating) {
      for (final item in ledger.items) {
        if (_canAutoRetry(item)) {
          retryTranslation(item);
          break;
        }
      }
    }
  }

  bool _canAutoRetry(Caption item) =>
      item.status == CaptionStatus.failed &&
      item.attempts < 2 &&
      const {
        'translation_timeout',
        'translation_failed',
        'empty_translation',
        'invalid_translation',
        'translation_queue_full',
      }.contains(item.errorCode);

  void retryTranslation(Caption item) {
    final payload = _translationPayloads[item.id];
    if (payload == null || item.epoch != epoch) return;
    if (item.english.isNotEmpty) {
      final activeMap = _activeDecoupledMap(item.endMs);
      final related = corpus.match(
        item.english,
        profile: corpusProfile,
        map: activeMap,
      );
      _translationPayloads[item.id] =
          mode == TranslationMode.qwen && isHyMtModelId(localTranslationId)
          ? context.hyMtPrompt(
              item.english,
              related,
              contextHint,
              style: captionStyle,
              profile: corpusProfile,
              communityNicknames: communityNicknames,
              nicknameSeed: item.sequence,
              activeContext: _activeDecoupledTeams(item.endMs).join(' '),
            )
          : context.payload(item.english, related, contextHint);
    }
    if (!ledger.retry(item.id, item.epoch, DateTime.now())) return;
    _enqueueTranslation(item.id);
    notifyListeners();
  }

  void retryAllTranslations() {
    for (final item in List<Caption>.of(ledger.items)) {
      if (item.status == CaptionStatus.failed) retryTranslation(item);
    }
  }

  @override
  void recognition(RecognitionEvent event) {
    if (endToEnd) {
      _recognitionPreview(event);
      return;
    }
    if (event.epoch != epoch ||
        !(running || phase == SessionPhase.pausing) ||
        _closedWindows.contains(event.window) ||
        event.revision <= (_revisions[event.window] ?? -1)) {
      return;
    }
    // Do not let an older utterance's late provisional result replace the current one.
    if (_revisions.keys.any((w) => w > event.window)) return;
    _revisions[event.window] = event.revision;
    _trimRecognitionState(event.window);
    final rawEnglish = stable.accept(
      event.window,
      event.text,
      finalResult: event.finalResult,
      allowEarly: event.endMs - event.startMs >= 4000,
    );
    if (event.finalResult) _closedWindows.add(event.window);
    if (stable.conflict) message = '识别结果发生冲突，已确认字幕保持不变';
    final assistanceChanged = _advanceAssistanceClock(event.endMs);
    if (rawEnglish.isNotEmpty) {
      final english = captionTask == 'chinese'
          ? rawEnglish
          : AsrPhoneticNormalizer.normalize(
              rawEnglish,
              profile: corpusProfile,
              activeTeams: _activeDecoupledTeams(event.endMs),
              contextHint: contextHint,
            );
      if (captionTask != 'chinese') {
        _observeDecoupledMatch(english, event.endMs);
      }
      final id = '$sessionId-$epoch-${_segment++}';
      final item = ledger.append(
        id: id,
        epoch: epoch,
        startMs: event.startMs,
        endMs: event.endMs,
        english: captionTask == 'chinese' ? '' : english,
        now: DateTime.now(),
      )!;
      _pruneTranslationState();
      if (!_needsDecoupledTranslation) {
        ledger.start(item.id, epoch, DateTime.now());
        ledger.complete(
          item.id,
          epoch,
          text: captionTask == 'chinese' ? english : '',
          allowEmpty: true,
        );
        if (playbackAudio) {
          _showOverlay([
            {'kind': 'source', 'text': english},
          ]);
        }
      } else {
        final activeMap = _activeDecoupledMap(event.endMs);
        final related = corpus.match(
          english,
          profile: corpusProfile,
          map: activeMap,
        );
        final payload =
            mode == TranslationMode.qwen && isHyMtModelId(localTranslationId)
            ? context.hyMtPrompt(
                english,
                related,
                contextHint,
                style: captionStyle,
                profile: corpusProfile,
                communityNicknames: communityNicknames,
                nicknameSeed: item.sequence,
                activeContext: _activeDecoupledTeams(event.endMs).join(' '),
              )
            : context.payload(english, related, contextHint);
        _translationPayloads[item.id] = payload;
        _itemOrder[item.id] = _segment;
        _rememberRecentEnglish(english, event.startMs, event.endMs);
        _updateEndToEndHints();
        if (running) context.add(english);
        if (playbackAudio &&
            showEnglish &&
            (!showChinese || _lastOverlayTranslatedOrder < 0)) {
          _showOverlay([
            {'kind': 'source', 'text': english},
          ]);
        }
        _enqueueTranslation(item.id);
      }
    } else if (assistanceChanged) {
      _updateEndToEndHints();
    }
    notifyListeners();
  }

  // E2E drafts are display-only. The final bilingual event owns history and
  // scene evidence, including when it revises or retracts the draft.
  void _recognitionPreview(RecognitionEvent event) {
    if (event.epoch != epoch || !(running || phase == SessionPhase.pausing)) {
      return;
    }
    if (event.finalResult) {
      if (!_closedWindows.add(event.window)) return;
      _trimRecognitionState(event.window);
      if (_advanceAssistanceClock(event.endMs)) _updateEndToEndHints();
      if (_e2ePreview?.window == event.window) {
        _e2ePreview = null;
        if (playbackAudio && showEnglish) _showOverlay([]);
      }
    } else {
      if (!running ||
          backendFlavor != 'gemmaE2E' ||
          captionTask != 'bilingual' ||
          !showEnglish ||
          event.text.trim().isEmpty ||
          (_e2ePreview?.window ?? -1) >= event.window ||
          _closedWindows.any((window) => window >= event.window)) {
        return;
      }
      _e2ePreview = event;
      if (playbackAudio) {
        _showOverlay([
          {'kind': 'source', 'text': event.text.trim()},
        ]);
      }
    }
    notifyListeners();
  }

  @override
  void bilingual(BilingualEvent event) {
    if (!endToEnd ||
        event.epoch != epoch ||
        !(running || phase == SessionPhase.pausing)) {
      return;
    }
    if (!_closedWindows.add(event.window)) return;
    if ((_e2ePreview?.window ?? -1) <= event.window) _e2ePreview = null;
    final timer = diagnosticsEnabled ? (Stopwatch()..start()) : null;
    _trimRecognitionState(event.window);
    final eligibleEvidence = event.startMs >= _assistanceFloorMs;
    final previousMap = scene.map;
    if (eligibleEvidence &&
        autoTermHints &&
        corpusProfile != CorpusProfile.none) {
      final injected = event.appliedHints == null
          ? _hintedConcepts
          : corpus
                .match(
                  event.appliedHints!,
                  limit: corpus.termCount,
                  profile: corpusProfile,
                )
                .map(corpus.sceneConceptFor)
                .toSet();
      scene.observe(
        corpus,
        event.english,
        epoch: epoch,
        window: event.window,
        endMs: event.endMs,
        injectedConcepts: injected,
      );
    }
    final mapChanged = _clearRecentForMapChange(previousMap, event.startMs);
    final id = '$sessionId-$epoch-${_segment++}';
    final item = ledger.append(
      id: id,
      epoch: epoch,
      startMs: event.startMs,
      endMs: event.endMs,
      english: event.english.trim(),
      now: DateTime.now(),
      diagnosticWindow: diagnosticsEnabled ? event.window : null,
    );
    _pruneTranslationState();
    if (item != null) {
      if (eligibleEvidence &&
          !(mapChanged && scene.map == null) &&
          event.english.trim().isNotEmpty) {
        _rememberRecentEnglish(event.english, event.startMs, event.endMs);
      }
      _updateEndToEndHints();
      String corrected = '';
      if (captionTask == 'chinese') {
        try {
          corrected = _parseCaptionChinese(event);
        } on TranslationFailure {
          corrected = translationUnavailableText;
        }
      } else if (captionTask != 'english') {
        try {
          corrected = corpus.correctChinese(
            event.english,
            _parseCaptionChinese(event),
            profile: corpusProfile,
            map: assistanceMap,
          );
        } on TranslationFailure {
          corrected = translationUnavailableText;
        }
      }
      ledger.start(id, epoch, DateTime.now());
      ledger.complete(
        id,
        epoch,
        text: corrected,
        allowEmpty: captionTask == 'english',
      );
      if (timer != null) {
        _reportCaptionTiming('controller', event.epoch, event.window, {
          'workUs': timer.elapsedMicroseconds,
        });
      }
      if (playbackAudio && _e2ePreview == null) {
        final overlayLines = <Map<String, String>>[
          if ((showEnglish || captionTask == 'english') &&
              event.english.trim().isNotEmpty)
            {'kind': 'source', 'text': event.english.trim()},
          if (showChinese && captionTask != 'english' && corrected.isNotEmpty)
            {
              'kind': item.status == CaptionStatus.failed
                  ? 'error'
                  : captionTask == 'chinese'
                  ? 'source'
                  : 'translation',
              'text': corrected,
            },
        ];
        _showOverlay(overlayLines, event: event);
      }
    }
    notifyListeners();
  }

  void _showOverlay(List<Map<String, String>> lines, {BilingualEvent? event}) {
    unawaited(
      _playback
          .invokeMethod<void>('subtitle', {
            'text': lines.map((line) => line['text']).join('\n'),
            'lines': lines,
            if (diagnosticsEnabled && event != null) ...{
              'epoch': event.epoch,
              'window': event.window,
              'source': lines.any((line) => line['kind'] == 'source'),
              'translation': lines.any(
                (line) =>
                    line['kind'] == 'translation' &&
                    line['text'] != translationUnavailableText,
              ),
            },
          })
          .catchError((_) {}),
    );
  }

  void reportCaptionPaint(
    Caption caption, {
    required bool source,
    required bool translation,
  }) {
    final window = caption.diagnosticWindow;
    if (window == null ||
        caption.diagnosticPaintReported ||
        caption.epoch != epoch) {
      return;
    }
    caption.diagnosticPaintReported = true;
    _reportCaptionTiming('flutter_paint', caption.epoch, window, {
      'source': source,
      'translation': translation,
    });
  }

  void _reportCaptionTiming(
    String stage,
    int epoch,
    int window,
    Map<String, Object> fields,
  ) {
    unawaited(
      _playback
          .invokeMethod<void>('captionTiming', {
            'stage': stage,
            'epoch': epoch,
            'window': window,
            ...fields,
          })
          .catchError((_) {}),
    );
  }

  void _enqueueTranslation(String id, {bool first = false}) {
    if (_activeTranslationId == id || _translationQueue.contains(id)) return;
    if (first) {
      _translationQueue.addFirst(id);
    } else {
      _translationQueue.addLast(id);
    }
    metrics['translation_queue_depth'] = _translationQueue.length;
    unawaited(_drainTranslations());
  }

  Future<void> _drainTranslations() async {
    if (_activeTranslationId != null) return;
    while (_translationQueue.isNotEmpty) {
      final id = _translationQueue.removeFirst();
      final matches = ledger.items.where((item) => item.id == id);
      final payload = _translationPayloads[id];
      if (matches.isEmpty || payload == null) continue;
      final item = matches.first;
      if (!ledger.start(id, item.epoch, DateTime.now())) continue;
      _activeTranslationId = id;
      metrics['translation_queue_depth'] = _translationQueue.length;
      notifyListeners();
      await _translate(item, payload);
      _activeTranslationId = null;
    }
    metrics['translation_queue_depth'] = 0;
    notifyListeners();
  }

  Future<void> _translate(Caption item, String payload) async {
    try {
      String result;
      if (mode == TranslationMode.external) {
        result = (await external.translate(
          item.id,
          payload,
          service,
          instruction: translationInstructionFor(
            corpusProfile,
            style: captionStyle,
          ),
        )).text;
      } else {
        if (!endToEnd && mode == TranslationMode.qwen && _needsPrepare) {
          await host.prepare(
            EngineConfig(
              asrPath: models.path(asrId),
              vadPath: '',
              translationPath: models.path(localTranslationId),
              mode: mode.name,
              threads: threads,
              automaticAssist: _nativeAutomaticAssist,
              names: corpus.whisperPrompt(contextHint),
            ),
          );
          _needsPrepare = false;
        }
        if (isHyMtModelId(localTranslationId)) {
          final prompt = wrapHyMtChatTemplate(payload);
          result = await host
              .translate(item.epoch, item.id, item.english, prompt)
              .timeout(const Duration(seconds: 45));
        } else {
          // Escape chat control markers inside user data before tokenization.
          final escaped = payload.replaceAll('<|', '< |').replaceAll('|>', '| >');
          final prompt =
              '<|im_start|>system\n/no_think\n${translationInstructionFor(corpusProfile, style: captionStyle)}<|im_end|>\n'
              '<|im_start|>user\n$escaped<|im_end|>\n'
              '<|im_start|>assistant\n';
          result = await host
              .translate(item.epoch, item.id, item.english, prompt)
              .timeout(const Duration(seconds: 45));
        }
      }
      if (item.epoch == epoch) {
        final parsed = parseTranslationText(
          result,
          allowNumeric: true,
          preservedIdentifiers: corpus.preservedIdentifiers(
            profile: corpusProfile,
          ),
        );
        final corrected = corpusProfile == CorpusProfile.none
            ? parsed
            : corpus.correctChinese(
                item.english,
                parsed,
                profile: corpusProfile,
                map: assistanceMap ?? _activeDecoupledMap(item.endMs),
              );
        final styled = CaptionStyleRenderer.render(
          english: item.english,
          chinese: corrected,
          style: captionStyle,
          nicknames: communityNicknames,
          cs2: corpusProfile == CorpusProfile.cs2,
          nicknameSeed: item.sequence,
          activeContext:
              '${_activeDecoupledTeams(item.endMs).join(' ')} $contextHint',
        );
        ledger.complete(item.id, item.epoch, text: styled);
        final order = _itemOrder[item.id] ?? -1;
        if (playbackAudio && order >= _lastOverlayTranslatedOrder) {
          _lastOverlayTranslatedOrder = order;
          final overlayLines = <Map<String, String>>[
            if (showEnglish && item.english.isNotEmpty)
              {'kind': 'source', 'text': item.english},
            if (showChinese && styled.isNotEmpty)
              {'kind': 'translation', 'text': styled},
          ];
          if (overlayLines.isNotEmpty) {
            _showOverlay(overlayLines);
          }
        }
      }
    } catch (e) {
      if (item.epoch == epoch) {
        final code = e is TranslationFailure
            ? e.code
            : e is PlatformException
            ? e.code
            : e is TimeoutException
            ? 'translation_timeout'
            : 'translation_failed';
        if (code == 'translation_preempted') {
          ledger.requeue(item.id, item.epoch);
          if (!_translationQueue.contains(item.id)) {
            _translationQueue.addFirst(item.id);
          }
        } else {
          ledger.complete(item.id, item.epoch, error: code);
          if (playbackAudio &&
              showEnglish &&
              item.english.isNotEmpty &&
              ledger.items.isNotEmpty &&
              ledger.items.last.id == item.id) {
            _showOverlay([
              {'kind': 'source', 'text': item.english},
            ]);
          }
          if (code == 'translation_timeout') {
            external.cancel(item.id);
            unawaited(host.cancelTranslation(item.id).catchError((_) {}));
          }
        }
      }
    }
    notifyListeners();
  }

  @override
  void activity(int epoch, double level, bool speech, int audioMs) {
    if (epoch != this.epoch || !running) return;
    if (audioMs < _audioMs) return;
    this.level = level;
    _audioMs = audioMs;
    if (_advanceAssistanceClock(audioMs)) _updateEndToEndHints();
    if (speech) _lastVoice = audioMs;
    phase = audioMs - _lastVoice >= 8000
        ? SessionPhase.waiting
        : SessionPhase.listening;
    notifyListeners();
  }

  @override
  void interrupted(int epoch, String code) {
    if (epoch != this.epoch || !running) return;
    // Only unload native weights on memory/thermal/background pressure.
    // User-initiated overlay stop (`playback_stopped`) keeps the loaded
    // translator warm so retrying an interrupted tail line or resuming is instant.
    _releaseOnPause = code == 'memory_pressure' ||
        code == 'thermal' ||
        code == 'app_background';
    message = switch (code) {
      'app_background' => '应用离开前台，已暂停；返回后手动继续',
      'thermal' => '手机温度过高，已暂停；请降温后继续',
      'memory_pressure' => '系统内存紧张，已暂停并释放模型',
      'playback_stopped' => '本设备音频采集已停止；返回后可重新授权继续',
      'playback_projection_revoked' => '系统音频授权已结束，请重新授权；锁屏也可能中断采集',
      _ => '麦克风被打断，请检查后继续',
    };
    unawaited(pause());
  }

  @override
  void gap(int epoch, int startMs, int endMs) {
    if (epoch != this.epoch || !(running || phase == SessionPhase.pausing)) {
      return;
    }
    _resetAssistance(
      clearInjected: false,
      floorMs: max(_assistanceFloorMs, endMs),
    );
    _updateEndToEndHints();
    ledger.gap(
      epoch,
      '此处收音未完成（${(startMs / 1000).toStringAsFixed(1)}–${(endMs / 1000).toStringAsFixed(1)} 秒）',
      DateTime.now(),
      startMs: startMs,
      endMs: endMs,
    );
    _pruneTranslationState();
    metrics['gaps'] = (metrics['gaps'] ?? 0) + 1;
    notifyListeners();
  }

  @override
  void diagnostic(int epoch, String code, int durationMs) {
    if (epoch == this.epoch) {
      metrics[code] = durationMs;
      metrics['event_${code}_count'] =
          (metrics['event_${code}_count'] ?? 0) + 1;
      if (code == 'asr_ms' || code == 'translation_ms') {
        final prefix = code == 'asr_ms' ? 'asr' : 'translation';
        metrics['${prefix}_count'] = (metrics['${prefix}_count'] ?? 0) + 1;
        metrics['${prefix}_total_ms'] =
            (metrics['${prefix}_total_ms'] ?? 0) + durationMs;
        metrics['${prefix}_max_ms'] = max(
          metrics['${prefix}_max_ms'] ?? 0,
          durationMs,
        );
      } else if (code == 'e2e_ms') {
        metrics['e2e_count'] = (metrics['e2e_count'] ?? 0) + 1;
        metrics['e2e_total_ms'] = (metrics['e2e_total_ms'] ?? 0) + durationMs;
        metrics['e2e_max_ms'] = max(metrics['e2e_max_ms'] ?? 0, durationMs);
      }
      notifyListeners();
    }
  }

  String _parseCaptionChinese(BilingualEvent event) {
    String identity(String value) =>
        value.trim().replaceFirst(RegExp(r'[.!。！]+$'), '').toLowerCase();
    final sameName = identity(event.english) == identity(event.chinese);
    return parseTranslationText(
      event.chinese,
      allowNumeric: true,
      preservedIdentifiers: captionTask == 'chinese' || sameName
          ? corpus.preservedIdentifiers(profile: corpusProfile)
          : const {},
    );
  }

  bool _pruneRecentEnglish(int audioMs) {
    _recentClockMs = max(_recentClockMs, max(_audioMs, audioMs));
    final before = _recentEnglish.length;
    _recentEnglish.removeWhere(
      (entry) =>
          _recentClockMs - entry.endMs > 60000 ||
          entry.startMs < _recentFloorMs,
    );
    final removed = before - _recentEnglish.length;
    if (removed > 0) {
      metrics['recent_context_expired'] =
          (metrics['recent_context_expired'] ?? 0) + removed;
    }
    metrics['recent_context_entries'] = _recentEnglish.length;
    return removed > 0;
  }

  bool _clearRecentForMapChange(String? previousMap, int floorMs) {
    if (_manualMap != null) return false;
    if (previousMap == null || previousMap == scene.map) return false;
    _recentEnglish.clear();
    _recentFloorMs = max(_recentFloorMs, floorMs);
    metrics['recent_context_entries'] = 0;
    metrics['recent_context_scope_clears'] =
        (metrics['recent_context_scope_clears'] ?? 0) + 1;
    return true;
  }

  bool _advanceAssistanceClock(int audioMs) {
    if (!autoTermHints) return false;
    final previousMap = scene.map;
    final sceneChanged = scene.advanceClock(audioMs);
    final expired = _pruneRecentEnglish(audioMs);
    final scopeChanged = _clearRecentForMapChange(previousMap, audioMs);
    return sceneChanged || expired || scopeChanged;
  }

  void _rememberRecentEnglish(String text, int startMs, int endMs) {
    if (!autoTermHints || corpusProfile == CorpusProfile.none) return;
    _pruneRecentEnglish(endMs);
    if (startMs < _recentFloorMs || _recentClockMs - endMs > 60000) return;
    final clean = CorpusIndex.sanitizeContext(text);
    if (clean.isEmpty || _recentEnglish.any((entry) => entry.text == clean)) {
      return;
    }
    _recentEnglish.addLast(_RecentEnglish(clean, startMs, endMs));
    while (_recentEnglish.length > 6) {
      _recentEnglish.removeFirst();
    }
    metrics['recent_context_entries'] = _recentEnglish.length;
  }

  String _preparedHints() {
    final hints = corpus.e2eHints(
      contextHint,
      profile: corpusProfile,
      map: assistanceMap,
      teams: assistanceTeams,
      mapIsManual: _manualMap != null,
      teamsAreManual: hasManualTeams,
    );
    _registerHints(hints);
    return hints;
  }

  void _registerHints(String hints) {
    // Permanently exclude injected concepts for this epoch. Conservative but
    // independent of bridge timing: hinted output never reinforces its source.
    for (final term in corpus.match(
      hints,
      limit: corpus.termCount,
      profile: corpusProfile,
    )) {
      _hintedConcepts.add(corpus.sceneConceptFor(term));
    }
    metrics['hint_token_estimate'] = CorpusIndex.estimateHintTokens(hints);
    metrics['hint_characters'] = hints.length;
  }

  void _updateEndToEndHints() {
    if (!endToEnd) return;
    _pruneRecentEnglish(_audioMs);
    final hints = corpus.e2eHints(
      contextHint,
      profile: corpusProfile,
      recentEnglish: _recentEnglish.map((entry) => entry.text),
      includeRecent: autoTermHints,
      map: assistanceMap,
      teams: assistanceTeams,
      mapIsManual: _manualMap != null,
      teamsAreManual: hasManualTeams,
    );
    _registerHints(hints);
    unawaited(
      host.updateHints(hints, _nativeAutomaticAssist).catchError((_) {}),
    );
  }

  Future<void> applyCaptionStyle() async {
    if (backendFlavor != 'gemmaE2E') return;
    try {
      await _playback.invokeMethod<void>('captionStyle', {
        'style': captionStyle.name,
        'nicknames': communityNicknames,
      });
    } on MissingPluginException {
      // Web/local preview has no native inference backend.
    }
  }

  Future<void> applyOverlayOpacity() async {
    try {
      await _playback.invokeMethod<void>('opacity', {
        'value': overlayBackgroundOpacity.clamp(.2, 1.0),
      });
    } on MissingPluginException {
      // Older/non-Android builds apply the value on the next capture start.
    }
  }

  void setFontSize(double value) {
    fontSize = value.clamp(14, 36);
    notifyListeners();
    unawaited(applyFontSize(explicit: true));
  }

  Future<void> applyFontSize({bool explicit = true}) async {
    try {
      await _playback.invokeMethod<void>('fontSize', {
        'value': fontSize.clamp(14, 36),
        'explicit': explicit,
      });
    } on MissingPluginException {
      // Older/non-Android builds apply the value on the next capture start.
    }
  }

  Future<void> applySubtitleColors() async {
    try {
      await _playback.invokeMethod<void>('colors', {
        'sourceArgb': sourceSubtitleColor.argb,
        'translationArgb': translationSubtitleColor.argb,
      });
    } on MissingPluginException {
      // Older/non-Android builds apply the value on the next capture start.
    }
  }

  @Deprecated('Use applySubtitleColors')
  Future<void> applySubtitleColor() => applySubtitleColors();

  @override
  void dispose() {
    _ticker?.cancel();
    external.cancelAll();
    EngineEvents.setUp(null);
    _playback.setMethodCallHandler(null);
    unawaited(host.release().catchError((_) {}));
    models.dispose();
    super.dispose();
  }
}

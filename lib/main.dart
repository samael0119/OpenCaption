import 'dart:async';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'core/captions.dart';
import 'core/build_config.dart';
import 'core/appearance.dart';
import 'core/session_controller.dart';
import 'core/corpus.dart';
import 'core/translation.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  LicenseRegistry.addLicense(() async* {
    yield LicenseEntryWithLineBreaks([
      'whisper.cpp',
      'llama.cpp',
      'GGML',
    ], await rootBundle.loadString('assets/native_licenses.txt'));
  });
  final controller = SessionController();
  runApp(OpenCaptionApp(controller: controller));
  unawaited(controller.initialize());
}

class OpenCaptionApp extends StatelessWidget {
  const OpenCaptionApp({super.key, required this.controller});
  final SessionController controller;
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: controller,
    builder: (context, _) => MaterialApp(
      title: 'OpenCaption',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff007c78)),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff52d5bb),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      themeMode: controller.theme == 'light'
          ? ThemeMode.light
          : controller.theme == 'system'
          ? ThemeMode.system
          : ThemeMode.dark,
      home: CaptionShell(controller: controller),
    ),
  );
}

class CaptionShell extends StatefulWidget {
  const CaptionShell({super.key, required this.controller});
  final SessionController controller;
  @override
  State<CaptionShell> createState() => _CaptionShellState();
}

class _CaptionShellState extends State<CaptionShell> {
  SessionController get c => widget.controller;
  final scroll = ScrollController();
  bool following = true;
  bool diagnosticsExpanded = false;
  int unread = 0, seen = 0;
  int seenSequence = -1;
  @override
  void dispose() {
    scroll.dispose();
    super.dispose();
  }

  Future<void> _begin() async {
    if (c.mode == TranslationMode.external) {
      final agreed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('启用外部文本翻译'),
          content: const Text(
            '当前句、最近英文上下文和相关术语将发送到你配置的服务。音频仍在手机识别，不上传。服务可能产生费用。',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('启用并开始'),
            ),
          ],
        ),
      );
      if (agreed != true) return;
    }
    setState(() {
      following = true;
      unread = seen = 0;
      seenSequence = -1;
    });
    await c.start();
  }

  Future<void> _showInfo(String title, String details) async {
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) {
        final maxHeight = MediaQuery.of(sheetContext).size.height * .72;
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 20),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxHeight: maxHeight),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: Theme.of(sheetContext).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 12),
                  Flexible(
                    child: SingleChildScrollView(
                      child: SelectableText(details),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      onPressed: () => Navigator.pop(sheetContext),
                      child: const Text('关闭'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _infoHint({
    required String summary,
    required String title,
    required String details,
  }) => _InfoHint(
    summary: summary,
    title: title,
    onTap: () => unawaited(_showInfo(title, details)),
  );

  Widget _infoCard({
    required String summary,
    required String title,
    required String details,
  }) => Card(
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: () => unawaited(_showInfo(title, details)),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text(
                summary,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 12),
            const Icon(Icons.info_outline),
          ],
        ),
      ),
    ),
  );

  Future<void> _leave() async {
    if (c.phase != SessionPhase.ended && c.phase != SessionPhase.idle) {
      await c.end();
    }
    if (!mounted) return;
    if (c.ledger.items.isNotEmpty) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('清除本次字幕？'),
          content: const Text('字幕只保留在本次会话，返回首页后将清除。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('继续回看'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('清除并返回'),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }
    c.clearReview();
  }

  @override
  Widget build(BuildContext context) {
    final home =
        c.phase == SessionPhase.idle || c.phase == SessionPhase.preparing;
    final latestSequence = c.ledger.latestSequence;
    if (latestSequence >= 0 && latestSequence != seenSequence) {
      final delta = seenSequence < 0
          ? c.ledger.items.length
          : latestSequence - seenSequence;
      if (!following && delta > 0) unread += delta;
      seenSequence = latestSequence;
      seen = c.ledger.items.length;
      if (following) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted && scroll.hasClients) {
            scroll.animateTo(
              scroll.position.maxScrollExtent,
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
            );
          }
        });
      }
    }
    return PopScope(
      canPop: c.phase == SessionPhase.idle,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) unawaited(_leave());
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('OpenCaption'),
          actions: [
            if (home && c.phase != SessionPhase.preparing)
              IconButton(
                tooltip: '设置',
                onPressed: c.initialized
                    ? () => Navigator.push(
                        context,
                        MaterialPageRoute<void>(
                          builder: (_) => SettingsPage(controller: c),
                        ),
                      )
                    : null,
                icon: const Icon(Icons.settings_outlined),
              ),
            if (diagnosticsEnabled)
              IconButton(
                tooltip: '诊断指标',
                onPressed: () => showDialog<void>(
                  context: context,
                  builder: (context) => AlertDialog(
                    title: const Text('本次诊断'),
                    content: Text(_diagnosticText()),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('关闭'),
                      ),
                    ],
                  ),
                ),
                icon: const Icon(Icons.monitor_heart_outlined),
              ),
          ],
        ),
        body: SafeArea(
          child: !c.initialized
              ? Center(
                  child: c.initializationFailed
                      ? Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(c.message),
                            TextButton(
                              onPressed: c.initialize,
                              child: const Text('重试'),
                            ),
                          ],
                        )
                      : const CircularProgressIndicator(),
                )
              : home
              ? _home()
              : _captions(),
        ),
      ),
    );
  }

  Widget _home() => ListView(
    padding: const EdgeInsets.all(24),
    children: [
      const SizedBox(height: 20),
      Text('听懂每一次采访', style: Theme.of(context).textTheme.headlineLarge),
      const SizedBox(height: 12),
      const Text('英语 → 简体中文 · 本地离线字幕'),
      if (c.backendFlavor == 'gemmaE2E')
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('本设备音频 · 后台悬浮字幕'),
          subtitle: _infoHint(
            summary: 'Android 10+ · 插耳机可用 · 点击查看完整说明',
            title: '本设备音频 · 后台悬浮字幕',
            details:
                '开始字幕并完成系统授权后，切换到直播 App 播放。此模式需要 Android 10+；系统弹窗可能称“录屏/投屏权限”，本应用只采集播放音频，不录制画面。佩戴耳机时也可使用，但目标 App 必须允许共享音频；部分 App、通话或 DRM 内容禁止采集，锁屏可能中断采集。',
          ),
          trailing: Switch(
            value: c.playbackAudio,
            onChanged: c.phase == SessionPhase.preparing
                ? null
                : (value) => setState(() => c.playbackAudio = value),
          ),
          onTap: c.phase == SessionPhase.preparing
              ? null
              : () => setState(() => c.playbackAudio = !c.playbackAudio),
        ),
      const SizedBox(height: 24),
      _infoCard(
        summary: c.playbackAudio
            ? '后台模式可采集其它 App 播放音频，插耳机也可用；需系统授权。'
            : '麦克风模式适合外放声音；耳机内音频无法通过麦克风获取。',
        title: c.playbackAudio ? '本设备音频模式说明' : '麦克风模式说明',
        details: c.playbackAudio
            ? '开始字幕并完成系统授权后，切换到直播 App 播放。此模式需要 Android 10+；系统弹窗可能称“录屏/投屏权限”，本应用只采集播放音频，不录制画面。佩戴耳机时也可使用，但目标 App 必须允许共享音频；部分 App、通话或 DRM 内容禁止采集，锁屏可能中断采集。'
            : '麦克风模式：将手机放在电脑或电视音箱附近，建议先从约 0.5 米开始。请保持 App 在前台；耳机内的声音无法通过麦克风收取。',
      ),
      const SizedBox(height: 16),
      _runtimeModels(),
      if (c.backendFlavor == 'gemmaE2E') ...[
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: c.captionTask,
          decoration: InputDecoration(
            labelText: '语音任务',
            helper: _infoHint(
              summary: isTestBuild
                  ? '共用已下载的 Gemma · 自动语言模式验证中'
                  : '共用已下载的 Gemma · 点击查看各模式说明',
              title: '语音任务',
              details:
                  '中英字幕：输出英文原文和简体中文译文。\n自动识别语言：识别输入语言，并在可翻译时提供中文和原文。\n仅英文转写：只输出英文原文，不执行翻译。\n仅中文转写：只输出中文转写，不执行翻译。\n所有模式共用当前已下载的 Gemma 模型，音频按顺序处理。',
            ),
          ),
          items: [
            const DropdownMenuItem(
              value: 'bilingual',
              child: Text('英文语音 → 中英字幕（默认）'),
            ),
            DropdownMenuItem(
              value: 'auto_zh',
              child: Text(
                isTestBuild ? '自动识别语言 → 中文＋原文（验证中）' : '自动识别语言 → 中文＋原文',
              ),
            ),
            const DropdownMenuItem(
              value: 'english',
              child: Text('仅英文转写 · 不执行翻译'),
            ),
            const DropdownMenuItem(
              value: 'chinese',
              child: Text('仅中文转写 · 不执行翻译'),
            ),
          ],
          onChanged: c.phase == SessionPhase.preparing
              ? null
              : (value) {
                  if (value == null) return;
                  setState(() => c.captionTask = value);
                  unawaited(c.savePreferences());
                },
        ),
      ],
      const SizedBox(height: 12),
      TextField(
        enabled: c.phase != SessionPhase.preparing,
        maxLength: 240,
        decoration: InputDecoration(
          labelText: '前置上下文提示补充（可选）',
          hintText: '如：XXX赛后采访 / XXX比赛，XXX VS XXX',
          helper: _infoHint(
            summary: '场景与专名提示 · 命令和无关内容会被忽略',
            title: '前置上下文提示补充',
            details:
                '可填写赛事、队伍、地图、采访场景或专有名词，例如“XXX比赛，XXX VS XXX”。模型加载后会把它作为不可信的场景数据提供给 Gemma，用于消歧；不会当作指令执行。命令、脚本、提示词注入、控制字符和过长内容会被自动忽略。',
          ),
          border: OutlineInputBorder(),
        ),
        onChanged: (v) => c.contextHint = v,
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<CorpusProfile>(
        initialValue: c.corpusProfile,
        decoration: InputDecoration(
          labelText: '术语库',
          helper: _infoHint(
            summary: '默认通用模式 · 点击查看术语提示规则',
            title: '术语库',
            details:
                '默认通用模式不附加领域术语。选择 CS2 后，只会把当前句命中的少量术语提供给模型；动态术语提示还会参考最近约 1 分钟的已确认英文。术语只用于消歧，不会覆盖模型对完整句意的判断。',
          ),
        ),
        items: CorpusProfile.values
            .map(
              (profile) =>
                  DropdownMenuItem(value: profile, child: Text(profile.label)),
            )
            .toList(),
        onChanged: c.phase == SessionPhase.preparing
            ? null
            : (value) {
                if (value == null) return;
                setState(() => c.corpusProfile = value);
                unawaited(c.savePreferences());
              },
      ),
      if (c.endToEnd && c.corpusProfile == CorpusProfile.cs2)
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(isTestBuild ? '动态术语提示（验证中）' : '动态术语提示'),
          subtitle: _infoHint(
            summary: '最近 1 分钟重复出现的术语才会进入提示 · 最多 6 条',
            title: '动态术语提示',
            details:
                '根据最近约 1 分钟的已确认英文，只有重复出现且命中 CS2 术语库的词条才会进入下一段提示，最多 6 条。它是轻量规则，不会启动第二个模型，也不会让整张术语表进入 prompt。',
          ),
          trailing: Switch(
            value: c.autoTermHints,
            onChanged: c.phase == SessionPhase.preparing
                ? null
                : (value) {
                    setState(() => c.autoTermHints = value);
                    unawaited(c.savePreferences());
                  },
          ),
          onTap: c.phase == SessionPhase.preparing
              ? null
              : () {
                  setState(() => c.autoTermHints = !c.autoTermHints);
                  unawaited(c.savePreferences());
                },
        ),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        isExpanded: true,
        initialValue: c.asrId,
        decoration: InputDecoration(
          labelText: c.endToEnd ? '端到端语音模型' : '本地识别模型',
          helper: _infoHint(
            summary: c.models.ready.contains(c.asrId)
                ? '已下载 · 本次字幕将使用此模型'
                : '尚未下载 · 点击查看准备方式',
            title: c.endToEnd ? '端到端语音模型' : '本地识别模型',
            details: c.models.ready.contains(c.asrId)
                ? '模型已下载并通过完整性校验。开始字幕时会按当前设备和模式加载它。'
                : '请点击“准备与管理模型”，选择模型并等待下载、校验完成。下载期间应用会保持屏幕常亮；模型准备好后可断网运行。',
          ),
        ),
        items: c.models.catalog
            .where((m) => m.kind == c.requiredModelKind)
            .map((m) => DropdownMenuItem(value: m.id, child: Text(m.label)))
            .toList(),
        onChanged: c.phase == SessionPhase.preparing
            ? null
            : (v) async {
                setState(() => c.asrId = v!);
                await c.savePreferences();
              },
      ),
      if (!c.endToEnd) ...[
        const SizedBox(height: 16),
        DropdownButtonFormField<TranslationMode>(
          isExpanded: true,
          initialValue: c.mode,
          decoration: InputDecoration(
            labelText: '英译中模型',
            helper: _infoHint(
              summary: '只影响已识别英文的翻译 · 不参与收音和英文识别',
              title: '英译中模型',
              details:
                  '此设置只用于级联模式中已经确认的英文，不参与收音、语音活动判断或英文识别。Gemma 端到端模式不会显示此项。',
            ),
          ),
          items: [
            const DropdownMenuItem(
              value: TranslationMode.mlKit,
              child: Text('ML Kit 端侧翻译 · 启动快，不支持上下文'),
            ),
            const DropdownMenuItem(
              value: TranslationMode.qwen,
              child: Text('本地 GGUF · 支持术语和上下文'),
            ),
            if (externalTranslationEnabled)
              const DropdownMenuItem(
                value: TranslationMode.external,
                child: Text('外部兼容 API · 使用自备模型服务'),
              ),
          ],
          onChanged: c.phase == SessionPhase.preparing
              ? null
              : (v) async {
                  setState(() => c.mode = v!);
                  await c.savePreferences();
                },
        ),
        if (c.mode == TranslationMode.qwen) ...[
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            isExpanded: true,
            initialValue: c.localTranslationId,
            decoration: InputDecoration(
              labelText: '本地翻译模型',
              helper: _infoHint(
                summary: c.models.ready.contains(c.localTranslationId)
                    ? '已下载 · 本次字幕将使用此模型'
                    : '尚未下载 · 点击查看准备方式',
                title: '本地翻译模型',
                details: c.models.ready.contains(c.localTranslationId)
                    ? '模型已下载并通过完整性校验。级联模式会在英文识别完成后使用它生成译文。'
                    : '请点击“准备与管理模型”，选择模型并等待下载、校验完成。',
              ),
            ),
            items: c.models.catalog
                .where(
                  (model) =>
                      model.kind == 'translation' && model.runtimeSupported,
                )
                .map(
                  (model) => DropdownMenuItem(
                    value: model.id,
                    child: Text(model.label),
                  ),
                )
                .toList(),
            onChanged: c.phase == SessionPhase.preparing
                ? null
                : (value) async {
                    setState(() => c.localTranslationId = value!);
                    await c.savePreferences();
                  },
          ),
        ],
      ] else ...[
        const SizedBox(height: 12),
        _infoHint(
          summary: '端到端处理 · 单模型串行生成字幕',
          title: '端到端处理说明',
          details:
              'Gemma 端到端模式由同一个模型完成语音理解、英文转写和中文输出，不再启动独立的翻译模型。新的音频窗口按顺序进入队列，避免多个推理任务争抢内存和算力。',
        ),
      ],
      const SizedBox(height: 16),
      OutlinedButton.icon(
        onPressed: c.phase == SessionPhase.preparing
            ? null
            : () => Navigator.push(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => ModelsPage(controller: c),
                ),
              ),
        icon: const Icon(Icons.download_outlined),
        label: const Text('准备与管理模型'),
      ),
      const SizedBox(height: 16),
      _infoHint(
        summary: isTestBuild ? '测试评测版 · 点击查看运行说明' : '本地离线字幕 · 点击查看隐私说明',
        title: isTestBuild ? '测试评测版说明' : '本地离线字幕与隐私',
        details: isTestBuild
            ? '当前为测试评测版，模型组合仍需持续验证离线质量、延迟、功耗和长时间稳定性。若遇到异常，请保留 Downloads 目录中的最新日志。'
            : '音频默认只在设备本地处理，不上传服务器；字幕只保留在当前会话，返回首页后会清除。后台模式还受目标 App、系统授权、锁屏和 DRM 限制。',
      ),
      if (c.message.isNotEmpty)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: _infoHint(
            summary: c.message,
            title: '当前状态',
            details: c.message,
          ),
        ),
      if (c.message.contains('权限'))
        TextButton(
          onPressed: c.host.openAppSettings,
          child: const Text('去系统设置'),
        ),
      const SizedBox(height: 20),
      FilledButton.icon(
        onPressed: c.phase == SessionPhase.preparing ? null : _begin,
        icon: const Icon(Icons.mic),
        label: Padding(
          padding: const EdgeInsets.all(14),
          child: Text(c.phase == SessionPhase.preparing ? '正在准备…' : '开始字幕'),
        ),
      ),
      if (diagnosticsEnabled)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: _infoHint(
            summary: '测试版会生成运行日志 · 点击查看保存位置',
            title: '测试日志',
            details:
                '测试版会在系统 Downloads 目录生成 opencaption_时间.log。若出现闪退、无字幕或长时间等待，请保留最新日志并记录对应的音频片段。正式版不会显示这条提示。',
          ),
        ),
      if (c.phase == SessionPhase.preparing)
        TextButton(onPressed: c.end, child: const Text('取消准备')),
    ],
  );

  String _phaseLabel() => switch (c.phase) {
    SessionPhase.listening => '收音中 · ${c.playbackAudio ? '本设备音频' : '麦克风'}',
    SessionPhase.waiting => '等待讲话',
    SessionPhase.pausing => '正在收尾',
    SessionPhase.paused => '已暂停',
    SessionPhase.ended => '运行结束',
    _ => '准备中',
  };

  String _formatDuration(int milliseconds) => milliseconds >= 1000
      ? '${(milliseconds / 1000).toStringAsFixed(1)} s'
      : '$milliseconds ms';

  String _statusSummary() {
    final metrics = c.metrics;
    final parts = <String>[_phaseLabel()];
    final latency = metrics['e2e_ms'] ?? metrics['asr_ms'];
    if (latency != null) parts.add('最近推理 ${_formatDuration(latency)}');
    final queue =
        metrics['e2e_queue_depth'] ?? metrics['translation_queue_depth'];
    if (queue != null && queue > 0) parts.add('待处理 $queue');
    final cpu = metrics['cpu_process_load_percent'];
    if (cpu != null) parts.add('CPU $cpu%');
    final gpu = metrics['gpu_load_percent'];
    if (gpu != null) parts.add('GPU $gpu%');
    final thermal = metrics['e2e_thermal_status'];
    if (thermal != null && thermal >= 3) parts.add('设备温度偏高');
    return parts.join(' · ');
  }

  Widget _statusDetails() {
    final metrics = c.metrics;
    final latency = metrics['e2e_ms'] ?? metrics['asr_ms'];
    final queue =
        metrics['e2e_queue_depth'] ?? metrics['translation_queue_depth'];
    final heap = metrics['e2e_native_heap_mb'];
    final thermal = metrics['e2e_thermal_status'];
    final cpu = metrics['cpu_process_load_percent'];
    final gpu = metrics['gpu_load_percent'];
    final lines = <String>[
      latency == null
          ? '最近处理：等待首个字幕窗口完成'
          : '最近处理：${_formatDuration(latency)}${metrics['e2e_ms'] != null ? '（端到端）' : '（识别）'}',
      if (queue != null) '待处理窗口：$queue',
      if (c.ledger.items.length >= c.ledger.maxItems)
        '字幕历史：仅保留最近 ${c.ledger.maxItems} 条（旧记录自动移除）',
      if (heap != null) '模型运行内存：约 $heap MB',
      if (cpu != null) 'CPU（本应用占全机容量）：$cpu%',
      if (gpu != null)
        'GPU（系统可读利用率）：$gpu%'
      else if (cpu != null && c.endToEnd)
        'GPU 负载：系统未提供可读接口',
      if (thermal != null)
        '设备温度：${thermal >= 4
            ? '严重'
            : thermal >= 3
            ? '偏高'
            : '正常'}',
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: lines.map(Text.new).toList(),
      ),
    );
  }

  String _diagnosticText() {
    final metrics = c.metrics;
    final lines = <String>['仅显示本次会话已收到的指标'];
    var hasTiming = false;
    final e2eCount = metrics['e2e_count'] ?? 0;
    if (e2eCount > 0) {
      hasTiming = true;
      final average = (metrics['e2e_total_ms'] ?? 0) ~/ e2eCount;
      lines.add(
        '端到端推理：$e2eCount 次 · 平均 ${_formatDuration(average)} · 最大 ${_formatDuration(metrics['e2e_max_ms'] ?? 0)}',
      );
      if (metrics['e2e_rtf_milli'] != null) {
        lines.add(
          '端到端实时比：${(metrics['e2e_rtf_milli']! / 1000).toStringAsFixed(2)}',
        );
      }
    }
    final asrCount = metrics['asr_count'] ?? 0;
    if (asrCount > 0) {
      hasTiming = true;
      lines.add(
        '英文识别：$asrCount 次 · 平均 ${_formatDuration((metrics['asr_total_ms'] ?? 0) ~/ asrCount)} · 最大 ${_formatDuration(metrics['asr_max_ms'] ?? 0)}',
      );
    }
    final translationCount = metrics['translation_count'] ?? 0;
    if (translationCount > 0) {
      hasTiming = true;
      lines.add(
        '文本翻译：$translationCount 次 · 平均 ${_formatDuration((metrics['translation_total_ms'] ?? 0) ~/ translationCount)} · 最大 ${_formatDuration(metrics['translation_max_ms'] ?? 0)}',
      );
    }
    final heap = metrics['e2e_native_heap_mb'];
    if (heap != null) lines.add('最近模型运行内存：约 $heap MB');
    final cpu = metrics['cpu_process_load_percent'];
    if (cpu != null) lines.add('最近 CPU（本应用占全机容量）：$cpu%');
    final gpu = metrics['gpu_load_percent'];
    if (gpu != null) {
      lines.add('最近 GPU（系统可读利用率）：$gpu%');
    } else if (cpu != null && c.endToEnd) {
      lines.add('GPU 负载：系统未提供可读接口');
    }
    final thermal = metrics['e2e_thermal_status'];
    if (thermal != null) {
      lines.add(
        '最近设备温度：${thermal >= 4
            ? '严重'
            : thermal >= 3
            ? '偏高'
            : '正常'}',
      );
    }
    final queue =
        metrics['e2e_queue_depth'] ?? metrics['translation_queue_depth'];
    if (queue != null) lines.add('最近待处理窗口：$queue');
    if (c.ledger.items.length >= c.ledger.maxItems) {
      lines.add('字幕历史：仅保留最近 ${c.ledger.maxItems} 条（旧记录自动移除）');
    }
    final gaps = metrics['gaps'];
    if (gaps != null) lines.add('未完成区间：$gaps');
    for (final code in const [
      'e2e_timeout',
      'e2e_parse_failed',
      'e2e_filtered_no_speech',
      'asr_filtered_noise',
    ]) {
      final count = metrics['event_${code}_count'] ?? 0;
      if (count > 0) lines.add('$code：$count 次');
    }
    if (c.external.requests > 0) {
      lines.add('外部翻译请求：${c.external.requests} 次');
      if (c.external.tokens > 0) lines.add('已知 token：${c.external.tokens}');
      if (c.external.usageUnknown) lines.add('部分请求未返回用量');
    }
    if (!hasTiming) {
      lines.add('尚未完成可计时的识别或字幕生成；完成一个语音窗口后再查看。');
    }
    lines.add('默认不记录音频、字幕或密钥。');
    return lines.join('\n');
  }

  Widget _runtimeModels() => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('本次字幕设置', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          Text('语音模型：${c.selectedAsrLabel}'),
          Text(c.endToEnd ? '音频处理：连续收音，按时间窗口生成字幕' : '音频处理：按语音停顿自动分段'),
          Text('字幕任务：${c.translationLabel}'),
          Text(
            c.backendFlavor == 'gemmaE2E'
                ? 'CPU 辅助：${c.threads} 线程（音频编码 / GPU 回退）'
                : c.backendFlavor == 'qwenE2E'
                ? '推理线程：由 MNN 运行时管理'
                : 'CPU 推理：${c.threads} 线程',
          ),
          Text(
            '领域语料：${c.corpusProfile.label} · '
            '${c.corpus.packCountFor(c.corpusProfile)} 个包 · '
            '${c.corpus.termCountFor(c.corpusProfile)} 条术语',
          ),
        ],
      ),
    ),
  );

  Widget _performance() {
    final metrics = c.metrics;
    final ended = c.phase == SessionPhase.ended;
    final e2eCount = metrics['e2e_count'] ?? 0;
    final asrCount = metrics['asr_count'] ?? 0;
    final translationCount = metrics['translation_count'] ?? 0;
    final values = <String>[];
    if (metrics['prepare_ms'] != null) {
      values.add('模型准备 ${metrics['prepare_ms']} ms');
    }
    if (e2eCount > 0) {
      final average = (metrics['e2e_total_ms'] ?? 0) ~/ e2eCount;
      values.add(
        ended
            ? '端到端 $e2eCount 次 · 平均 $average ms · 最大 ${metrics['e2e_max_ms']} ms'
            : '端到端 ${metrics['e2e_ms']} ms · RTF ${((metrics['e2e_rtf_milli'] ?? 0) / 1000).toStringAsFixed(2)}',
      );
    }
    if (asrCount > 0) {
      final average = (metrics['asr_total_ms'] ?? 0) ~/ asrCount;
      values.add(
        ended
            ? '识别 $asrCount 次 · 平均 $average ms · 最大 ${metrics['asr_max_ms']} ms'
            : '识别 ${metrics['asr_ms']} ms · RTF ${((metrics['asr_rtf_milli'] ?? 0) / 1000).toStringAsFixed(2)}',
      );
      if (!ended && metrics['asr_characters_per_second'] != null) {
        values.add('识别输出 ${metrics['asr_characters_per_second']} 字符/秒');
      }
    }
    if (translationCount > 0) {
      final average =
          (metrics['translation_total_ms'] ?? 0) ~/ translationCount;
      values.add(
        ended
            ? '翻译 $translationCount 次 · 平均 $average ms · 最大 ${metrics['translation_max_ms']} ms'
            : '翻译 ${metrics['translation_ms']} ms · 输出 ${metrics['translation_characters_per_second'] ?? 0} 字符/秒',
      );
    }
    if ((metrics['translation_queue_depth'] ?? 0) > 0) {
      values.add('等待翻译 ${metrics['translation_queue_depth']} 条（识别继续运行）');
    }
    if (ended) {
      values.add(
        '运行 ${metrics['session_seconds'] ?? 0} 秒 · 丢段 ${metrics['gaps'] ?? 0}',
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(ended ? '本次运行汇总' : '模型运行'),
            const SizedBox(height: 4),
            if (values.isEmpty)
              const Text('等待首次识别…')
            else
              ...values.map(Text.new),
          ],
        ),
      ),
    );
  }

  Widget _statusBar() => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 16),
    child: ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: ColoredBox(
        color: Theme.of(context).colorScheme.surfaceContainer,
        child: ExpansionTile(
          dense: true,
          initiallyExpanded: diagnosticsExpanded,
          onExpansionChanged: (value) => setState(() {
            diagnosticsExpanded = value;
          }),
          title: Text(
            _statusSummary(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          childrenPadding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
          children: [
            _statusDetails(),
            if (diagnosticsEnabled) ...[_runtimeModels(), _performance()],
          ],
        ),
      ),
    ),
  );

  Widget _captions() => Column(
    children: [
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LinearProgressIndicator(
              value: (c.level * 20).clamp(0, 1),
              semanticsLabel: '音量活动，不代表已识别',
            ),
            if (c.message.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(c.message),
              ),
          ],
        ),
      ),
      _statusBar(),
      Expanded(
        child: NotificationListener<ScrollNotification>(
          onNotification: (n) {
            if (n is ScrollStartNotification && n.dragDetails != null) {
              setState(() => following = false);
            }
            return false;
          },
          child: ListView.builder(
            controller: scroll,
            padding: const EdgeInsets.all(16),
            itemCount: c.ledger.items.length + 1,
            itemBuilder: (context, index) {
              if (index == c.ledger.items.length) {
                return Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    c.stable.temporary.isEmpty
                        ? (c.running ? '正在听…' : '')
                        : '临时英文：${c.stable.temporary}',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                );
              }
              final item = c.ledger.items[index];
              if (item.status == CaptionStatus.gap) {
                return Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(item.chinese),
                );
              }
              final resolved = c.ledger.canShowTranslation(item);
              final sourceColor = Color(c.sourceSubtitleColor.argb);
              final translationColor = Color(c.translationSubtitleColor.argb);
              final errorColor = Theme.of(context).colorScheme.error;
              final chinese = item.status == CaptionStatus.ready && resolved
                  ? item.chinese
                  : item.status == CaptionStatus.failed && resolved
                  ? switch (item.errorCode) {
                      'translation_timeout' => translationTimeoutText,
                      _ => translationUnavailableText,
                    }
                  : translationPendingText;
              return Card(
                key: ValueKey(item.id),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (item.english.trim().isNotEmpty &&
                          (c.showEnglish ||
                              c.captionTask == 'english' ||
                              item.status == CaptionStatus.failed))
                        Text(
                          item.english,
                          style: TextStyle(
                            fontSize: 14,
                            color: item.status == CaptionStatus.failed
                                ? errorColor
                                : sourceColor,
                          ),
                        ),
                      if (c.showChinese && c.captionTask != 'english') ...[
                        const SizedBox(height: 8),
                        Text(
                          chinese,
                          style: TextStyle(
                            fontSize: c.fontSize,
                            height: 1.45,
                            color: item.status == CaptionStatus.failed
                                ? errorColor
                                : c.captionTask == 'chinese'
                                ? sourceColor
                                : translationColor,
                          ),
                        ),
                      ],
                      if (item.status == CaptionStatus.failed &&
                          c.phase == SessionPhase.ended)
                        Align(
                          alignment: Alignment.centerRight,
                          child: TextButton.icon(
                            onPressed: () => c.retryTranslation(item),
                            icon: const Icon(Icons.refresh),
                            label: Text('重试翻译（已尝试 ${item.attempts} 次）'),
                          ),
                        ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
      if (!following)
        TextButton.icon(
          onPressed: () => setState(() {
            following = true;
            unread = 0;
            if (scroll.hasClients) {
              scroll.jumpTo(scroll.position.maxScrollExtent);
            }
          }),
          icon: const Icon(Icons.arrow_downward),
          label: Text('回到最新（$unread 条）'),
        ),
      if (c.phase == SessionPhase.ended && c.retryableTranslations > 0)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: FilledButton.icon(
            onPressed: c.retryAllTranslations,
            icon: const Icon(Icons.refresh),
            label: Text('重试全部失败译文（${c.retryableTranslations} 条）'),
          ),
        ),
      Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            if (c.phase != SessionPhase.ended)
              Expanded(
                child: FilledButton.icon(
                  onPressed: c.phase == SessionPhase.pausing
                      ? null
                      : c.phase == SessionPhase.paused
                      ? c.resume
                      : c.pause,
                  icon: Icon(
                    c.phase == SessionPhase.paused ? Icons.mic : Icons.pause,
                  ),
                  label: Text(c.phase == SessionPhase.paused ? '继续' : '暂停'),
                ),
              ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton(
                onPressed: c.phase == SessionPhase.ended ? _leave : c.end,
                child: Text(c.phase == SessionPhase.ended ? '返回首页' : '结束'),
              ),
            ),
          ],
        ),
      ),
    ],
  );
}

class _InfoHint extends StatelessWidget {
  const _InfoHint({
    required this.summary,
    required this.title,
    required this.onTap,
  });

  final String summary;
  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.onSurfaceVariant;
    return Semantics(
      button: true,
      label: '$title，点击查看完整说明',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            children: [
              Icon(Icons.info_outline, size: 15, color: color),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  summary,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: color),
                ),
              ),
              const SizedBox(width: 2),
              Icon(Icons.chevron_right, size: 16, color: color),
            ],
          ),
        ),
      ),
    );
  }
}

class ModelsPage extends StatefulWidget {
  const ModelsPage({super.key, required this.controller});
  final SessionController controller;
  @override
  State<ModelsPage> createState() => _ModelsPageState();
}

class _ModelsPageState extends State<ModelsPage> {
  static const _power = MethodChannel('dev.opencaption/power');
  bool mlBusy = false;
  String mlMessage = '';
  int _awakeOperations = 0;
  SessionController get c => widget.controller;

  Future<T> _whileKeepingScreenOn<T>(Future<T> Function() operation) async {
    _awakeOperations++;
    if (_awakeOperations == 1) {
      await _power.invokeMethod<void>('setKeepScreenOn', {'enabled': true});
    }
    try {
      return await operation();
    } finally {
      _awakeOperations--;
      if (_awakeOperations == 0) {
        await _power.invokeMethod<void>('setKeepScreenOn', {'enabled': false});
      }
    }
  }

  Future<void> _installModel(String id, {String? importPath}) =>
      _whileKeepingScreenOn(() => c.models.install(id, importPath: importPath));

  Future<void> _ml(bool remove) async {
    setState(() {
      mlBusy = true;
      mlMessage = '';
    });
    try {
      if (remove) {
        await c.host.deleteMlKit();
      } else {
        await _whileKeepingScreenOn(c.host.downloadMlKit);
      }
      c.mlReady = await c.host.mlKitReady();
    } catch (_) {
      mlMessage = '语言包操作失败，请检查网络后重试；也可准备 Qwen 离线组合';
    }
    if (mounted) setState(() => mlBusy = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('模型准备')),
    body: AnimatedBuilder(
      animation: c.models,
      builder: (context, _) => ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            c.endToEnd
                ? '模型准备好后可断网运行。实时字幕优先选择 Gemma 4 E2B；E4B 更偏向质量优先。下载优先使用魔搭国内源，不可用时自动切换备用源。'
                : '模型准备好后可断网运行。下载源会按优先级测速，并自动切换可用备用源。',
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            initialValue: c.asrId,
            decoration: const InputDecoration(labelText: '本地识别候选'),
            items: c.models.catalog
                .where((m) => m.kind == c.requiredModelKind)
                .map(
                  (m) => DropdownMenuItem(
                    value: m.id,
                    child: Text(m.recommended ? '${m.label} · 推荐' : m.label),
                  ),
                )
                .toList(),
            onChanged: (v) async {
              setState(() => c.asrId = v!);
              await c.savePreferences();
            },
          ),
          const SizedBox(height: 16),
          ...c.models.catalog
              .where(
                (m) => c.endToEnd
                    ? m.kind == c.requiredModelKind
                    : !m.kind.startsWith('e2e-'),
              )
              .map((m) {
                final busy = c.models.progress.containsKey(m.id),
                    ready = c.models.ready.contains(m.id);
                final selected =
                    m.id == c.asrId ||
                    (m.id == c.localTranslationId &&
                        c.mode == TranslationMode.qwen);
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          m.label,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        Text(
                          '${(m.size / 1000000).toStringAsFixed(1)} MB · ${ready ? '已准备' : '未准备'}',
                        ),
                        if (m.description.isNotEmpty)
                          Text(
                            m.description,
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                        if (!m.runtimeSupported)
                          Text(
                            m.unavailableReason,
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        if (m.recommended)
                          const Chip(label: Text('优先推荐 · 实时首选')),
                        if (selected)
                          Chip(
                            label: Text(m.kind == 'asr' ? '当前识别模型' : '当前翻译模型'),
                          ),
                        if (busy)
                          LinearProgressIndicator(
                            value: c.models.progress[m.id],
                          ),
                        if (c.models.states[m.id] != null)
                          Text(c.models.states[m.id]!),
                        if (c.models.activeSources[m.id] != null)
                          Text('来源：${c.models.activeSources[m.id]}'),
                        if (c.models.errors[m.id] != null)
                          Text(c.models.errors[m.id]!),
                        Wrap(
                          spacing: 8,
                          children: [
                            TextButton(
                              onPressed: !m.runtimeSupported
                                  ? null
                                  : busy
                                  ? () => c.models.cancel(m.id)
                                  : () => _installModel(m.id),
                              child: Text(
                                busy
                                    ? '取消'
                                    : ready
                                    ? '重新下载'
                                    : '下载',
                              ),
                            ),
                            TextButton(
                              onPressed: !m.runtimeSupported || busy
                                  ? null
                                  : () async {
                                      final file = await openFile(
                                        acceptedTypeGroups: [
                                          const XTypeGroup(
                                            label: '模型',
                                            extensions: [
                                              'bin',
                                              'gguf',
                                              'litertlm',
                                            ],
                                          ),
                                        ],
                                      );
                                      if (file != null) {
                                        await _installModel(
                                          m.id,
                                          importPath: file.path,
                                        );
                                      }
                                    },
                              child: const Text('导入'),
                            ),
                            if (ready)
                              TextButton(
                                onPressed: busy
                                    ? null
                                    : () => c.models.delete(m.id),
                                child: const Text('删除'),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              }),
          if (!c.endToEnd)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('ML Kit 英中翻译 · ${c.mlReady ? '已准备' : '未准备'}'),
                    const Text(
                      'Google 端侧 SDK 的语言包由 SDK 自行下载，应用无法替换下载源。国内网络若下载失败，建议使用上方 Qwen 本地翻译模型。',
                    ),
                    if (mlBusy) const LinearProgressIndicator(),
                    if (mlMessage.isNotEmpty) Text(mlMessage),
                    Wrap(
                      children: [
                        TextButton(
                          onPressed: mlBusy ? null : () => _ml(false),
                          child: const Text('Wi-Fi 下载语言包'),
                        ),
                        if (c.mlReady)
                          TextButton(
                            onPressed: mlBusy ? null : () => _ml(true),
                            child: const Text('删除语言包'),
                          ),
                      ],
                    ),
                    const Text('翻译由 Google 提供。'),
                    if (c.mode == TranslationMode.mlKit)
                      const Chip(label: Text('当前翻译模型')),
                  ],
                ),
              ),
            ),
        ],
      ),
    ),
  );
}

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key, required this.controller});
  final SessionController controller;
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final url = TextEditingController(text: c.service.baseUrl);
  late final model = TextEditingController(text: c.service.model);
  late final keyField = TextEditingController(text: c.service.apiKey);
  late final budget = TextEditingController(text: '${c.service.tokenBudget}');
  late bool localHttp = c.service.allowLocalHttp;
  bool testing = false;
  String status = '';
  SessionController get c => widget.controller;
  ServiceConfig get service => ServiceConfig(
    baseUrl: url.text.trim(),
    model: model.text.trim(),
    apiKey: keyField.text.trim(),
    allowLocalHttp: localHttp,
    tokenBudget: int.tryParse(budget.text) ?? 0,
  );
  @override
  void dispose() {
    url.dispose();
    model.dispose();
    keyField.dispose();
    budget.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('设置')),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text('字幕字号 ${c.fontSize.round()}'),
        Slider(
          value: c.fontSize,
          min: 20,
          max: 36,
          divisions: 16,
          onChanged: (v) {
            setState(() => c.fontSize = v);
          },
        ),
        DropdownButtonFormField<String>(
          initialValue: c.showEnglish
              ? (c.showChinese ? 'both' : 'english')
              : 'chinese',
          decoration: const InputDecoration(labelText: '字幕显示（不改变模型任务）'),
          items: const [
            DropdownMenuItem(value: 'both', child: Text('双语')),
            DropdownMenuItem(value: 'english', child: Text('仅原文 / 英文')),
            DropdownMenuItem(value: 'chinese', child: Text('仅中文')),
          ],
          onChanged: (value) => setState(() {
            c.showEnglish = value != 'chinese';
            c.showChinese = value != 'english';
          }),
        ),
        DropdownButtonFormField<SubtitleColor>(
          initialValue: c.sourceSubtitleColor,
          decoration: const InputDecoration(
            labelText: '原文 / 转写颜色',
            helperText: '双语时用于原文；仅原文或仅中文转写也使用此颜色，默认黄色',
          ),
          items: SubtitleColor.values
              .map(
                (color) => DropdownMenuItem(
                  value: color,
                  child: Text(
                    color.label,
                    style: TextStyle(color: Color(color.argb)),
                  ),
                ),
              )
              .toList(),
          onChanged: (value) {
            if (value == null) return;
            setState(() => c.sourceSubtitleColor = value);
            unawaited(c.applySubtitleColors());
            unawaited(c.savePreferences());
          },
        ),
        DropdownButtonFormField<SubtitleColor>(
          initialValue: c.translationSubtitleColor,
          decoration: const InputDecoration(
            labelText: '译文颜色',
            helperText: '双语时用于中文译文，错误提示固定为红色，默认绿色',
          ),
          items: SubtitleColor.values
              .map(
                (color) => DropdownMenuItem(
                  value: color,
                  child: Text(
                    color.label,
                    style: TextStyle(color: Color(color.argb)),
                  ),
                ),
              )
              .toList(),
          onChanged: (value) {
            if (value == null) return;
            setState(() => c.translationSubtitleColor = value);
            unawaited(c.applySubtitleColors());
            unawaited(c.savePreferences());
          },
        ),
        DropdownButtonFormField<String>(
          initialValue: c.theme,
          decoration: const InputDecoration(labelText: '主题'),
          items: const [
            DropdownMenuItem(value: 'dark', child: Text('深色')),
            DropdownMenuItem(value: 'light', child: Text('浅色')),
            DropdownMenuItem(value: 'system', child: Text('跟随系统')),
          ],
          onChanged: (v) {
            if (v == null) return;
            setState(() => c.theme = v);
            // savePreferences notifies OpenCaptionApp after persisting, so the
            // root MaterialApp applies the new theme immediately.
            unawaited(c.savePreferences());
          },
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<CorpusProfile>(
          initialValue: c.corpusProfile,
          decoration: const InputDecoration(
            labelText: '术语库',
            helperText: '通用模式默认不注入领域术语；CS2 模式只发送相关少量词条',
          ),
          items: CorpusProfile.values
              .map(
                (profile) => DropdownMenuItem(
                  value: profile,
                  child: Text(profile.label),
                ),
              )
              .toList(),
          onChanged: (value) {
            if (value == null) return;
            setState(() => c.corpusProfile = value);
            unawaited(c.savePreferences());
          },
        ),
        if (c.endToEnd && c.corpusProfile == CorpusProfile.cs2)
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(isTestBuild ? '动态术语提示（验证中）' : '动态术语提示'),
            subtitle: const Text('最近 1 分钟内重复或高优先级的 CS2 术语才会进入下一段提示'),
            value: c.autoTermHints,
            onChanged: (value) {
              setState(() => c.autoTermHints = value);
              unawaited(c.savePreferences());
            },
          ),
        if (c.backendFlavor == 'gemmaE2E') ...[
          const SizedBox(height: 12),
          Text('悬浮字幕背景不透明度 ${(c.overlayBackgroundOpacity * 100).round()}%'),
          Slider(
            value: c.overlayBackgroundOpacity,
            min: .2,
            max: 1,
            divisions: 16,
            label: '${(c.overlayBackgroundOpacity * 100).round()}%',
            onChanged: (value) {
              setState(() => c.overlayBackgroundOpacity = value);
              unawaited(c.applyOverlayOpacity());
            },
          ),
          const Text('仅影响后台悬浮字幕面板；越低越透明，文字仍保持高对比度。'),
        ],
        const SizedBox(height: 16),
        if (c.backendFlavor == 'qwenE2E')
          const ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('推理线程'),
            subtitle: Text('Qwen Omni 由 MNN 运行时自动管理'),
          )
        else
          DropdownButtonFormField<int>(
            initialValue: c.threads,
            decoration: InputDecoration(
              labelText: c.backendFlavor == 'gemmaE2E'
                  ? 'CPU 辅助线程'
                  : isTestBuild
                  ? 'CPU 推理线程（评测）'
                  : 'CPU 推理线程',
              helperText: c.backendFlavor == 'gemmaE2E'
                  ? 'GPU 优先；CPU 回退与音频编码使用相同线程数。4 默认，6 为性能档'
                  : isTestBuild
                  ? '4 默认；6 预留约 2 核余量；8 仅建议短时使用'
                  : '4 默认；6 预留约 2 核余量；8 适合短时高负载',
            ),
            items: const [
              DropdownMenuItem(value: 2, child: Text('2 线程 · 低功耗')),
              DropdownMenuItem(value: 4, child: Text('4 线程 · 默认')),
              DropdownMenuItem(value: 6, child: Text('6 线程 · 性能档')),
              DropdownMenuItem(value: 8, child: Text('8 线程 · 短时高负载')),
            ],
            onChanged: (v) {
              if (v == null) return;
              setState(() => c.threads = v);
              unawaited(c.savePreferences());
            },
          ),
        if (externalTranslationEnabled) ...[
          const SizedBox(height: 28),
          Text('可选外部文本翻译', style: Theme.of(context).textTheme.titleLarge),
          const Text('识别始终在手机完成。这里保存配置；只有首页主动选择外部增强后才发送会话文字。'),
          const SizedBox(height: 16),
          TextField(
            controller: url,
            decoration: const InputDecoration(
              labelText: 'API 基础地址（包含 /v1 等前缀）',
              hintText: 'https://example.com/v1',
            ),
          ),
          TextField(
            controller: model,
            decoration: const InputDecoration(labelText: '模型名'),
          ),
          TextField(
            controller: keyField,
            obscureText: true,
            enableSuggestions: false,
            autocorrect: false,
            decoration: const InputDecoration(labelText: 'API Key（可选，安全存储）'),
          ),
          SwitchListTile(
            title: const Text('允许局域网 HTTP'),
            subtitle: const Text('仅限私有 IP 或 localhost；手机上的 localhost 指手机本身'),
            value: localHttp,
            onChanged: (v) => setState(() => localHttp = v),
          ),
          TextField(
            controller: budget,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: '每场已知 token 软预算（0 为不限）',
            ),
          ),
          const Text('服务未返回用量时无法完整计算；软预算不保证账单硬上限。费用未知。'),
          const SizedBox(height: 16),
          OutlinedButton(
            onPressed: testing
                ? null
                : () async {
                    setState(() {
                      testing = true;
                      status = '测试中…';
                    });
                    final client = ExternalTranslator();
                    try {
                      final reply = await client.translate(
                        'connection-test',
                        '{"CURRENT":"Hello. This is a connection test."}',
                        service,
                      );
                      status = '连接成功：${reply.text}';
                    } catch (e) {
                      status =
                          '测试失败：${e is TranslationFailure ? e.code : 'service_unavailable'}';
                    } finally {
                      client.cancelAll();
                    }
                    if (mounted) setState(() => testing = false);
                  },
            child: Text(testing ? '测试中…' : '用固定测试句检查连接'),
          ),
          if (status.isNotEmpty) Text(status),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () async {
              try {
                final next = service;
                if (next.baseUrl.isNotEmpty ||
                    next.model.isNotEmpty ||
                    next.apiKey.isNotEmpty) {
                  next.endpoint;
                }
                if (next.tokenBudget < 0) {
                  throw const TranslationFailure('invalid_budget');
                }
                c.service = next;
                await c.savePreferences();
                if (context.mounted) Navigator.pop(context);
              } catch (_) {
                setState(() => status = '保存失败，请检查地址、模型名、预算及安全存储');
              }
            },
            child: const Text('保存设置'),
          ),
        ],
        TextButton(
          onPressed: () => showLicensePage(
            context: context,
            applicationName: 'OpenCaption',
            applicationVersion: isTestBuild ? '0.1.1 测试评测版' : '0.1.1',
          ),
          child: const Text('开源许可'),
        ),
      ],
    ),
  );
}

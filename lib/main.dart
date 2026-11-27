import 'dart:async';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart'
    show PaintingContext, RenderProxyBox, ScrollDirection;
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'core/captions.dart';
import 'core/build_config.dart';
import 'core/appearance.dart';
import 'core/session_controller.dart';
import 'core/corpus.dart';
import 'core/caption_style.dart';
import 'core/translation.dart';
import 'models/model_store.dart';
import 'widgets/caption_transcript.dart';
import 'widgets/scene_controls.dart';

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

class _CaptionPaintProbe extends SingleChildRenderObjectWidget {
  const _CaptionPaintProbe({
    super.key,
    required this.afterPaint,
    required super.child,
  });

  final VoidCallback afterPaint;

  @override
  _CaptionPaintBox createRenderObject(BuildContext context) =>
      _CaptionPaintBox(afterPaint);

  @override
  void updateRenderObject(BuildContext context, _CaptionPaintBox renderObject) {
    renderObject.afterPaint = afterPaint;
  }
}

class _CaptionPaintBox extends RenderProxyBox {
  _CaptionPaintBox(this.afterPaint);

  VoidCallback? afterPaint;

  @override
  void paint(PaintingContext context, Offset offset) {
    super.paint(context, offset);
    final callback = afterPaint;
    if (callback == null) return;
    afterPaint = null;
    WidgetsBinding.instance.addPostFrameCallback((_) => callback());
  }
}

class _CaptionShellState extends State<CaptionShell> {
  SessionController get c => widget.controller;
  final scroll = ScrollController();
  final _hintController = TextEditingController();
  bool following = true;
  bool diagnosticsExpanded = false;
  int unread = 0, seen = 0;
  int seenSequence = -1;
  String seenE2ePreview = '';
  @override
  void dispose() {
    scroll.dispose();
    _hintController.dispose();
    super.dispose();
  }

  Future<void> _begin() async {
    if (!c.endToEnd && c.mode == TranslationMode.external) {
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

  Future<void> _openModels() => Navigator.push(
    context,
    MaterialPageRoute<void>(builder: (_) => ModelsPage(controller: c)),
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
    final finalArrived = latestSequence >= 0 && latestSequence != seenSequence;
    final preview = c.e2eSourcePreview;
    final previewArrived = preview.isNotEmpty && preview != seenE2ePreview;
    seenE2ePreview = preview;
    if (finalArrived) {
      final delta = seenSequence < 0
          ? c.ledger.items.length
          : latestSequence - seenSequence;
      if (!following && delta > 0) unread += delta;
      seenSequence = latestSequence;
      seen = c.ledger.items.length;
    }
    if (following && (finalArrived || previewArrived)) {
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
    return PopScope(
      canPop: c.phase == SessionPhase.idle,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) unawaited(_leave());
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('OpenCaption'),
          actions: [
            if (home && c.phase != SessionPhase.preparing) ...[
              IconButton(
                tooltip: '使用与隐私说明',
                onPressed: () => unawaited(
                  _showInfo(
                    '离线字幕说明',
                    '1. 隐私与本地运行：音频默认完全在手机本地处理，不上传服务器；字幕仅保留在本次会话，返回首页后清除。\n\n'
                        '2. 本设备音频（Android 10+）：授权系统投屏/音频采集后，可切到视频或直播 App 显示悬浮字幕，佩戴耳机也可使用；部分 App、通话或 DRM 内容禁止采集，锁屏可能中断采集。\n\n'
                        '3. 引擎选择：听译分离（Whisper + HY-MT1.5）响应更快、术语更稳；端到端（Gemma 4）单模型直出，支持流式预览与社区外号风格。'
                        '${diagnosticsEnabled ? '\n\n4. 测试日志：当前构建会在系统 Downloads 目录生成 opencaption_时间.log。' : ''}',
                  ),
                ),
                icon: const Icon(Icons.info_outline),
              ),
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
            ],
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

  Widget _sectionPanel({
    required BuildContext context,
    required List<Widget> children,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainerLow,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: scheme.outlineVariant.withValues(alpha: .6)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: children,
        ),
      ),
    );
  }

  String _decoupledTranslatorChoice() => switch (c.mode) {
    TranslationMode.qwen => 'local:${c.localTranslationId}',
    TranslationMode.mlKit => 'mlKit',
    TranslationMode.external => 'external',
  };

  List<DropdownMenuItem<String>> _decoupledTranslatorItems() {
    final localModels = c.models.catalog.where(
      (m) => m.kind == 'translation' && m.runtimeSupported,
    );
    return [
      for (final model in localModels)
        DropdownMenuItem(
          value: 'local:${model.id}',
          child: Text(
            model.label,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      const DropdownMenuItem(
        value: 'mlKit',
        child: Text('ML Kit 端侧翻译（无上下文）', overflow: TextOverflow.ellipsis),
      ),
      if (externalTranslationEnabled)
        const DropdownMenuItem(
          value: 'external',
          child: Text('外部兼容 API', overflow: TextOverflow.ellipsis),
        ),
    ];
  }

  Widget _home() {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final busy = c.phase == SessionPhase.preparing;
    final ready = c.activeModelsReady;
    final needsMt =
        !c.endToEnd && c.captionTask != 'english' && c.captionTask != 'chinese';
    final translatorItems = _decoupledTranslatorItems();
    final currentTranslator = _decoupledTranslatorChoice();
    final selectedTranslator = translatorItems.any(
      (item) => item.value == currentTranslator,
    )
        ? currentTranslator
        : translatorItems.first.value!;
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
            children: [
              Text(
                '离线实时字幕',
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '本地推理 · 音频不上传',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: scheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 16),
              if (c.supportsPipelineSwitch) ...[
                SegmentedButton<CaptionPipeline>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(
                      value: CaptionPipeline.decoupled,
                      icon: Icon(Icons.tune, size: 18),
                      label: Text('听译分离'),
                    ),
                    ButtonSegment(
                      value: CaptionPipeline.gemmaE2e,
                      icon: Icon(Icons.auto_awesome, size: 18),
                      label: Text('端到端 Gemma'),
                    ),
                  ],
                  selected: {c.pipeline},
                  onSelectionChanged: busy
                      ? null
                      : (selected) async {
                          c.setPipeline(selected.first);
                          await c.savePreferences();
                        },
                ),
                const SizedBox(height: 8),
                Text(
                  c.endToEnd
                      ? 'Gemma 4 单模型直接听译，保留完整端到端流程'
                      : '极速 ONNX 语音识别 + HY-MT1.5 动态术语翻译，更快更稳',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 12),
              ],
              _sectionPanel(
                context: context,
                children: [
                  Row(
                    children: [
                      Icon(
                        ready
                            ? Icons.check_circle_outline
                            : Icons.download_for_offline_outlined,
                        size: 18,
                        color: ready ? scheme.primary : scheme.error,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          ready ? '模型已就绪' : '所选模型尚未下载',
                          style: theme.textTheme.titleSmall?.copyWith(
                            color: ready ? scheme.primary : scheme.error,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: busy ? null : _openModels,
                        style: TextButton.styleFrom(
                          visualDensity: VisualDensity.compact,
                        ),
                        child: const Text('管理模型'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    initialValue: c.asrId,
                    key: ValueKey('asr-${c.requiredModelKind}-${c.asrId}'),
                    decoration: InputDecoration(
                      labelText: c.endToEnd ? '端到端语音模型' : '语音识别模型',
                      isDense: true,
                      border: const OutlineInputBorder(),
                    ),
                    items: c.models.catalog
                        .where((m) => m.kind == c.requiredModelKind)
                        .map(
                          (m) => DropdownMenuItem(
                            value: m.id,
                            child: Text(
                              m.label,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: busy
                        ? null
                        : (v) async {
                            if (v == null) return;
                            setState(() => c.asrId = v);
                            await c.savePreferences();
                          },
                  ),
                  if (needsMt) ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      isExpanded: true,
                      initialValue: selectedTranslator,
                      key: ValueKey('mt-$selectedTranslator'),
                      decoration: const InputDecoration(
                        labelText: '文本翻译模型',
                        isDense: true,
                        border: OutlineInputBorder(),
                      ),
                      items: translatorItems,
                      onChanged: busy
                          ? null
                          : (value) async {
                              if (value == null) return;
                              setState(() {
                                if (value == 'mlKit') {
                                  c.mode = TranslationMode.mlKit;
                                } else if (value == 'external') {
                                  c.mode = TranslationMode.external;
                                } else if (value.startsWith('local:')) {
                                  c.mode = TranslationMode.qwen;
                                  c.localTranslationId = value.substring(6);
                                }
                              });
                              await c.savePreferences();
                            },
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 12),
              _sectionPanel(
                context: context,
                children: [
                  if (c.backendFlavor == 'gemmaE2E') ...[
                    Row(
                      children: [
                        Text('收音来源', style: theme.textTheme.titleSmall),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            c.playbackAudio ? '插耳机可用 · 悬浮窗' : '外放收音 · 前台',
                            textAlign: TextAlign.end,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: scheme.onSurfaceVariant,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    SegmentedButton<bool>(
                      showSelectedIcon: false,
                      segments: const [
                        ButtonSegment(
                          value: false,
                          icon: Icon(Icons.mic_none, size: 18),
                          label: Text('麦克风'),
                        ),
                        ButtonSegment(
                          value: true,
                          icon: Icon(Icons.hearing_outlined, size: 18),
                          label: Text('本设备音频'),
                        ),
                      ],
                      selected: {c.playbackAudio},
                      onSelectionChanged: busy
                          ? null
                          : (selected) {
                              setState(() => c.playbackAudio = selected.first);
                              unawaited(c.savePreferences());
                            },
                    ),
                    const SizedBox(height: 14),
                  ],
                  if (c.backendFlavor == 'gemmaE2E') ...[
                    DropdownButtonFormField<String>(
                      isExpanded: true,
                      initialValue: c.captionTask,
                      key: ValueKey('task-${c.captionTask}'),
                      decoration: const InputDecoration(
                        labelText: '语言任务',
                        isDense: true,
                        border: OutlineInputBorder(),
                      ),
                      items: const [
                        DropdownMenuItem(
                          value: 'bilingual',
                          child: Text('英文语音 → 中英字幕'),
                        ),
                        DropdownMenuItem(
                          value: 'auto_zh',
                          child: Text('自动识别语言 → 中文＋原文'),
                        ),
                        DropdownMenuItem(
                          value: 'english',
                          child: Text('仅英文转写'),
                        ),
                        DropdownMenuItem(
                          value: 'chinese',
                          child: Text('仅中文转写'),
                        ),
                      ],
                      onChanged: busy
                          ? null
                          : (value) {
                              if (value == null) return;
                              setState(() => c.captionTask = value);
                              unawaited(c.savePreferences());
                            },
                    ),
                    const SizedBox(height: 12),
                  ],
                  DropdownButtonFormField<CorpusProfile>(
                    isExpanded: true,
                    initialValue: c.corpusProfile,
                    key: ValueKey('corpus-${c.corpusProfile.id}'),
                    decoration: const InputDecoration(
                      labelText: '领域术语',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    items: CorpusProfile.values
                        .map(
                          (profile) => DropdownMenuItem(
                            value: profile,
                            child: Text(profile.label),
                          ),
                        )
                        .toList(),
                    onChanged: busy
                        ? null
                        : (value) {
                            if (value == null) return;
                            setState(() => c.corpusProfile = value);
                            unawaited(c.savePreferences());
                          },
                  ),
                  const SizedBox(height: 4),
                  Theme(
                    data: theme.copyWith(dividerColor: Colors.transparent),
                    child: ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      childrenPadding: const EdgeInsets.only(top: 6),
                      dense: true,
                      title: Text(
                        c.contextHint.trim().isEmpty
                            ? '赛前上下文 / 专名提示（可选）'
                            : '已填写上下文提示',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                      children: [
                        Builder(
                          builder: (context) {
                            if (_hintController.text != c.contextHint) {
                              _hintController.value = TextEditingValue(
                                text: c.contextHint,
                                selection: TextSelection.collapsed(
                                  offset: c.contextHint.length,
                                ),
                              );
                            }
                            return TextField(
                              controller: _hintController,
                              enabled: !busy,
                              maxLength: 240,
                              decoration: const InputDecoration(
                                hintText: '如：donk, sh1ro, NiKo, re-smoke=补烟',
                                isDense: true,
                                border: OutlineInputBorder(),
                              ),
                              onChanged: (v) {
                                c.contextHint = v;
                                unawaited(c.savePreferences());
                              },
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.fromLTRB(20, 10, 20, 16),
          decoration: BoxDecoration(
            color: scheme.surface,
            border: Border(
              top: BorderSide(color: scheme.outlineVariant.withValues(alpha: .5)),
            ),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (c.message.isNotEmpty) ...[
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: scheme.errorContainer.withValues(alpha: .7),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          c.message,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: scheme.onErrorContainer,
                          ),
                        ),
                      ),
                      if (c.message.contains('权限'))
                        TextButton(
                          onPressed: c.host.openAppSettings,
                          child: const Text('去设置'),
                        )
                      else if (c.message.contains('准备所选'))
                        TextButton(
                          onPressed: busy ? null : _openModels,
                          child: const Text('去下载'),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
              ],
              FilledButton.icon(
                onPressed: busy ? null : _begin,
                icon: Icon(c.playbackAudio ? Icons.hearing : Icons.mic),
                label: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  child: Text(
                    busy
                        ? '正在准备模型…'
                        : c.playbackAudio
                        ? '开始悬浮字幕'
                        : '开始字幕',
                  ),
                ),
              ),
              if (busy)
                TextButton(onPressed: c.end, child: const Text('取消准备')),
            ],
          ),
        ),
      ],
    );
  }

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
    if (c.autoTermHints && c.corpusProfile != CorpusProfile.none) {
      parts.add(
        c.assistanceMap == null
            ? '场景待确认'
            : '${c.assistanceMap}${c.manualMap == null ? '' : '（已纠正）'}',
      );
      if (c.assistanceTeams.length == 2) {
        parts.add(
          '${c.assistanceTeams.join(' vs ')}${c.hasManualTeams ? '（已纠正）' : ''}',
        );
      }
    }
    if (!diagnosticsEnabled) return parts.join(' · ');
    if (c.autoTermHints &&
        c.scene.teams.isEmpty &&
        c.scene.teamCandidates.isNotEmpty) {
      parts.add('战队候选（未确认）${c.scene.teamCandidates.join(' / ')}');
    }
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
      child: Material(
        color: Theme.of(context).colorScheme.surfaceContainer,
        child: ExpansionTile(
          dense: true,
          initiallyExpanded: diagnosticsExpanded,
          onExpansionChanged: (value) => setState(() {
            diagnosticsExpanded = value;
          }),
          title: Text(
            _statusSummary(),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          childrenPadding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
          children: [
            ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * .36,
              ),
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (c.initialized && c.endToEnd && c.autoTermHints)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                        child: SceneControls(controller: c),
                      ),
                    _statusDetails(),
                    if (diagnosticsEnabled) ...[
                      _runtimeModels(),
                      _performance(),
                    ],
                  ],
                ),
              ),
            ),
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
            if ((n is ScrollStartNotification && n.dragDetails != null) ||
                (n is UserScrollNotification &&
                    n.direction != ScrollDirection.idle)) {
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
                final temporary = c.endToEnd
                    ? c.e2eSourcePreview
                    : c.stable.temporary;
                return Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    temporary.isEmpty
                        ? (c.running ? '正在听…' : '')
                        : '临时英文：$temporary',
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
              final chinese = item.status == CaptionStatus.ready && resolved
                  ? item.chinese
                  : item.status == CaptionStatus.failed && resolved
                  ? switch (item.errorCode) {
                      'translation_timeout' => translationTimeoutText,
                      _ => translationUnavailableText,
                    }
                  : translationPendingText;
              final showSource =
                  c.showEnglish ||
                  c.captionTask == 'english' ||
                  item.status == CaptionStatus.failed;
              final showTranslation =
                  c.showChinese && c.captionTask != 'english';
              final transcript = CaptionTranscript(
                key: ValueKey(item.id),
                source: item.english,
                translation: chinese,
                showSource: showSource,
                showTranslation: showTranslation,
                fontSize: c.fontSize,
                sourceColor: c.captionTask == 'chinese'
                    ? translationColor
                    : sourceColor,
                translationColor: c.captionTask == 'chinese'
                    ? sourceColor
                    : translationColor,
                failed: item.status == CaptionStatus.failed,
                latest: index == c.ledger.items.length - 1,
                footer:
                    item.status == CaptionStatus.failed &&
                        c.phase == SessionPhase.ended
                    ? Align(
                        alignment: Alignment.centerRight,
                        child: TextButton.icon(
                          onPressed: () => c.retryTranslation(item),
                          icon: const Icon(Icons.refresh),
                          label: Text('重试翻译（已尝试 ${item.attempts} 次）'),
                        ),
                      )
                    : null,
              );
              if (!diagnosticsEnabled ||
                  c.playbackAudio ||
                  item.diagnosticWindow == null ||
                  item.diagnosticPaintReported) {
                return transcript;
              }
              final translated =
                  showTranslation &&
                  item.status == CaptionStatus.ready &&
                  resolved &&
                  chinese.isNotEmpty &&
                  chinese != translationUnavailableText;
              final source =
                  (showSource && item.english.isNotEmpty) ||
                  (translated && c.captionTask == 'chinese');
              final translation = translated && c.captionTask != 'chinese';
              if (!source && !translation) return transcript;
              return _CaptionPaintProbe(
                key: ValueKey('paint-${item.id}'),
                afterPaint: () => c.reportCaptionPaint(
                  item,
                  source: source,
                  translation: translation,
                ),
                child: transcript,
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
  late CaptionPipeline _tab = c.pipeline;
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
      mlMessage = '语言包操作失败，请检查网络后重试；推荐使用 HY-MT1.5 本地离线翻译模型';
    }
    if (mounted) setState(() => mlBusy = false);
  }

  Widget _modelCard(ModelSpec m) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final busy = c.models.progress.containsKey(m.id);
    final ready = c.models.ready.contains(m.id);
    final selected =
        m.id == c.asrId ||
        (!c.endToEnd &&
            m.id == c.localTranslationId &&
            c.mode == TranslationMode.qwen);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      color: scheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(
          color: selected
              ? scheme.primary.withValues(alpha: .7)
              : scheme.outlineVariant.withValues(alpha: .5),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(m.label, style: theme.textTheme.titleMedium),
                ),
                const SizedBox(width: 8),
                Text(
                  ready ? '已就绪' : '未下载',
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: ready ? scheme.primary : scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${(m.size / 1000000).toStringAsFixed(1)} MB',
              style: theme.textTheme.bodySmall?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
            ),
            if (m.description.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(m.description, style: theme.textTheme.bodySmall),
            ],
            if (!m.runtimeSupported) ...[
              const SizedBox(height: 6),
              Text(
                m.unavailableReason,
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.error),
              ),
            ],
            if (m.recommended || selected) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  if (m.recommended)
                    const Chip(
                      label: Text('推荐'),
                      visualDensity: VisualDensity.compact,
                    ),
                  if (selected)
                    Chip(
                      label: Text(
                        m.kind == 'translation' ? '当前翻译模型' : '当前识别模型',
                      ),
                      visualDensity: VisualDensity.compact,
                    ),
                ],
              ),
            ],
            if (busy) ...[
              const SizedBox(height: 8),
              LinearProgressIndicator(value: c.models.progress[m.id]),
            ],
            if (c.models.states[m.id] != null) ...[
              const SizedBox(height: 4),
              Text(c.models.states[m.id]!, style: theme.textTheme.bodySmall),
            ],
            if (c.models.activeSources[m.id] != null)
              Text(
                '来源：${c.models.activeSources[m.id]}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: scheme.onSurfaceVariant,
                ),
              ),
            if (c.models.errors[m.id] != null)
              Text(
                c.models.errors[m.id]!,
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.error),
              ),
            const SizedBox(height: 6),
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
                if (m.parts.isEmpty)
                  TextButton(
                    onPressed: !m.runtimeSupported || busy
                        ? null
                        : () async {
                            final file = await openFile(
                              acceptedTypeGroups: [
                                const XTypeGroup(
                                  label: '模型',
                                  extensions: ['bin', 'gguf', 'litertlm'],
                                ),
                              ],
                            );
                            if (file != null) {
                              await _installModel(m.id, importPath: file.path);
                            }
                          },
                    child: const Text('手动导入'),
                  ),
                if (ready)
                  TextButton(
                    onPressed: busy ? null : () => c.models.delete(m.id),
                    child: const Text('删除'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final showE2e = c.supportsPipelineSwitch
        ? _tab == CaptionPipeline.gemmaE2e
        : c.endToEnd;
    final e2eModels = c.models.catalog.where(
      (m) => m.kind == 'e2e-${c.backendFlavor}',
    );
    final asrModels = c.models.catalog.where((m) => m.kind == 'asr');
    final mtModels = c.models.catalog.where(
      (m) => m.kind == 'translation' && m.runtimeSupported,
    );
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('模型管理')),
      body: AnimatedBuilder(
        animation: c.models,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              '模型下载并校验后可完全断网运行，优先使用国内镜像源，下载期间屏幕保持常亮。',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (c.models.orphanedBytes > 0) ...[
              const SizedBox(height: 12),
              Card(
                elevation: 0,
                color: theme.colorScheme.secondaryContainer.withValues(alpha: .55),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    children: [
                      Icon(
                        Icons.cleaning_services_outlined,
                        color: theme.colorScheme.onSecondaryContainer,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '发现 ${c.models.orphanedCount} 项旧版废弃模型',
                              style: theme.textTheme.titleSmall?.copyWith(
                                color: theme.colorScheme.onSecondaryContainer,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '可释放 ${(c.models.orphanedBytes / (1024 * 1024)).toStringAsFixed(1)} MB，不影响当前在用模型',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSecondaryContainer,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      FilledButton.tonal(
                        onPressed: c.models.busy
                            ? null
                            : () async {
                                final freed = await c.models
                                    .cleanupOrphanedModels();
                                if (!context.mounted) return;
                                final mb = (freed / (1024 * 1024))
                                    .toStringAsFixed(1);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text('已清理旧版废弃模型，释放 $mb MB')),
                                );
                              },
                        child: const Text('一键清理'),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            if (c.supportsPipelineSwitch) ...[
              const SizedBox(height: 16),
              SegmentedButton<CaptionPipeline>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(
                    value: CaptionPipeline.decoupled,
                    label: Text('听译分离模型'),
                  ),
                  ButtonSegment(
                    value: CaptionPipeline.gemmaE2e,
                    label: Text('端到端模型'),
                  ),
                ],
                selected: {_tab},
                onSelectionChanged: (selected) =>
                    setState(() => _tab = selected.first),
              ),
            ],
            const SizedBox(height: 16),
            if (showE2e) ...[
              Text('Gemma 4 端到端语音模型', style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              ...e2eModels.map(_modelCard),
            ] else ...[
              Text('1. 语音识别模型（ONNX 极速）', style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              ...asrModels.map(_modelCard),
              const SizedBox(height: 8),
              Text('2. 文本翻译模型（本地 GGUF）', style: theme.textTheme.titleSmall),
              const SizedBox(height: 8),
              ...mtModels.map(_modelCard),
              Card(
                elevation: 0,
                color: theme.colorScheme.surfaceContainerLow,
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'ML Kit 英中端侧翻译 · ${c.mlReady ? '已就绪' : '未准备'}',
                        style: theme.textTheme.titleMedium,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Google 端侧语言包由 SDK 自行下载，无上下文支持。国内网络若失败，推荐使用上方 HY-MT1.5 1.8B。',
                        style: theme.textTheme.bodySmall,
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
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
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
    body: AnimatedBuilder(
      animation: c,
      builder: (context, _) => ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text('字幕字号 ${c.fontSize.round()}（应用内与悬浮窗同步）'),
        Slider(
          value: c.fontSize.clamp(14, 36),
          min: 14,
          max: 36,
          divisions: 22,
          label: '${c.fontSize.round()}',
          onChanged: (v) {
            setState(() => c.setFontSize(v));
          },
          onChangeEnd: (_) {
            unawaited(c.savePreferences());
          },
        ),
        DropdownButtonFormField<String>(
          key: ValueKey('display-${c.showEnglish}-${c.showChinese}'),
          initialValue: c.showEnglish
              ? (c.showChinese ? 'both' : 'english')
              : 'chinese',
          decoration: const InputDecoration(labelText: '字幕显示（不改变模型任务）'),
          items: const [
            DropdownMenuItem(value: 'both', child: Text('双语')),
            DropdownMenuItem(value: 'english', child: Text('仅原文 / 英文')),
            DropdownMenuItem(value: 'chinese', child: Text('仅中文')),
          ],
          onChanged: (value) {
            setState(() {
              c.showEnglish = value != 'chinese';
              c.showChinese = value != 'english';
            });
            unawaited(c.savePreferences());
          },
        ),
        if (c.backendFlavor == 'gemmaE2E') ...[
          const SizedBox(height: 16),
          DropdownButtonFormField<CaptionStyle>(
            key: ValueKey('captionStyle-${c.captionStyle.name}'),
            initialValue: c.captionStyle,
            isExpanded: true,
            decoration: InputDecoration(
              labelText: '翻译风格',
              helperText: '${c.captionStyle.description}；切换后用于后续片段',
              helperMaxLines: 3,
            ),
            items: CaptionStyle.values
                .map(
                  (style) =>
                      DropdownMenuItem(value: style, child: Text(style.label)),
                )
                .toList(),
            onChanged: (value) async {
              if (value == null) return;
              setState(() {
                c.captionStyle = value;
                if (value == CaptionStyle.community) {
                  c.communityNicknames = true;
                }
              });
              await c.applyCaptionStyle();
              await c.savePreferences();
            },
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('选手使用中文社区外号'),
            subtitle: const Text('仅 CS2 词库生效；已确认的选手可显示为“大表哥”等，未知名称保留 ID'),
            value: c.communityNicknames,
            onChanged: (value) async {
              setState(() => c.communityNicknames = value);
              await c.applyCaptionStyle();
              await c.savePreferences();
            },
          ),
          if (c.captionStyle == CaptionStyle.community)
            const Text('含少量趣味改写；仅在原意明确时使用，不改数字、否定或人物关系。'),
          const SizedBox(height: 12),
        ],
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
            helperText: '选库默认开启自动辅助，通用模式不注入领域术语',
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
            title: const Text('自动辅助'),
            subtitle: const Text('参考近期字幕检索术语和判断场景；证据不足自动回退'),
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
            onChangeEnd: (_) {
              unawaited(c.savePreferences());
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
            applicationVersion: isTestBuild ? '0.2.0 测试评测版' : '0.2.0',
          ),
          child: const Text('开源许可'),
        ),
        ],
      ),
    ),
  );
}

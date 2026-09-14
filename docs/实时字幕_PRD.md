# OpenCaption 实时字幕产品需求文档

版本：v1.1（当前实现基线）
日期：2026-09-14
状态：开发评测版，未通过正式发布验收
首发平台：Android，当前构建目标为 `arm64-v8a`

本文同时记录产品要求、当前实现和已知差距。标为“目标”的指标不能被单次实验结果替代；标为“当前结果”的数据只代表已记录的样本和设备。

## 1. 产品定义与当前决策

OpenCaption 是一个本地优先的 Android 实时字幕工具：从手机麦克风或受系统授权的本设备播放音频中获取语音，在设备端生成原文和简体中文字幕。首要场景仍是电脑、电视或直播 App 中的英文采访，产品结构不再把识别能力硬编码为英语专用。

当前主线是 `gemmaE2E`：

- 使用 LiteRT Community 的 Gemma 4 E2B/E4B `.litertlm` 部署包和 LiteRT-LM Android `0.17.0`。
- E2B 是默认、优先推荐和实时首选；E4B 是质量优先的手动选项。
- Android 初始化优先 GPU，失败后回退 CPU；音频编码使用 CPU。E2B/E4B 都开启 MTP/speculative decoding，`maxNumTokens=768`，最大输出 128 token，关闭 thinking。
- App 默认使用跟随系统主题；模型页显示用途说明，E2B 显示“优先推荐 · 实时首选”。

旧的 `cascade`（whisper.cpp＋ML Kit／GGUF 翻译）和 `qwenE2E`（Qwen Omni MNN）仍保留为兼容或历史实验变体，但不再是产品下一步方向。新模型评估优先要求 `litert-community` 和 LiteRT-LM 可加载格式，不继续扩展 llama.cpp 模型路线。

## 2. 范围与边界

### 2.1 当前交付范围

| 优先级 | 能力 | 当前状态 |
| --- | --- | --- |
| P0 | 麦克风收音、权限、音量活动、开始／暂停／继续／结束 | 已实现，仍需长稳验收 |
| P0 | Gemma 端到端中英字幕 | 已实现，E2B 默认，E4B 可选 |
| P0 | 英文转写、中文转写、自动识别语言任务 | 已实现于 Gemma 协议，需继续测多语言质量 |
| P0 | 会话内字幕、回到最新、结束回看、失败译文重试 | 已实现，当前不持久化整场字幕 |
| P0 | 模型下载／导入／断点续传／多源测速／大小与 SHA-256 校验 | 已实现 |
| P0 | 测试诊断、推理延迟、RTF、队列、CPU／GPU／温度／模型运行内存 | Debug 测试包已实现 |
| P1 | CS2 术语包、当场上下文、动态提示 | 已实现；默认不启用 CS2 术语 |
| P1 | Android 本设备播放音频捕获与悬浮字幕 | Gemma 开发评测路径已实现，兼容性仍需专项验收 |
| P1 | 浅色／深色／跟随系统、字幕颜色、字号和悬浮背景透明度 | 已实现 |
| P2 | 其他直播 App 的稳定同机捕获、iOS、保存／导出、更多领域包 | 未完成 |

### 2.2 不在当前交付范围

中文配音、独立后端、自动云端切换、系统全局音频抓取、锁屏持续收音、说话人识别、账号／付费体系、将字幕作为正式会议记录保存，以及“任何语言都保证同等质量”均不属于当前发布承诺。

外部 Chat Completions 文本翻译代码和安全存储配置仍保留，但当前产品构建通过编译期开关隐藏入口；不能把外部翻译描述为当前默认或已验收功能。

## 3. 用户、场景与使用边界

### 3.1 主要用户任务

1. 用户打开 App，准备一个已下载模型，选择麦克风或本设备音频。
2. 用户在采访或直播期间查看原文与中文，能暂停、继续、结束并回看本次字幕。
3. 用户可以提供比赛、队伍、选手、地图或采访场景等有限上下文，帮助模型消歧。
4. 用户可以在通用模式和 CS2 术语模式之间选择；通用模式不注入 CS2 词表。

### 3.2 输入方式

- **麦克风模式**：手机靠近外放音源，耳机内音频不能通过麦克风获取。建议先从约 0.5 米开始，距离和音量只作为现场调试参考。
- **本设备音频模式**：Android 10+ 使用 MediaProjection 播放音频捕获和前台服务，系统弹窗可能称录屏／投屏授权；应用只采集音频，不录制画面。需要悬浮窗和通知权限，目标 App、DRM、通话、锁屏或音频策略可能禁止共享。

应用保持前台时处理麦克风；离开前台、麦克风被打断、播放投影被撤销、严重温升或内存压力出现时暂停或结束，不在后台静默重新开启麦克风。

## 4. 页面和交互

### 4.1 首页

首页显示当前输入方式、语音任务、上下文、领域语料、实际模型、模型是否就绪和“准备与管理模型”入口。Gemma 任务包括：

- 英文语音 → 中英字幕（默认）；
- 自动识别语言 → 中文＋原文；
- 仅英文转写，不执行翻译；
- 仅中文转写，不执行翻译。

上下文最多 240 字符，过滤控制字符、标签、常见提示注入和命令式内容；它是模型输入中的不可信数据，不是第二条指令通道。

### 4.2 字幕页

字幕页显示收音状态、音量活动、最近推理耗时、RTF、待处理窗口和可读的资源／温度信息。测试包展开状态栏后显示完整计时与过滤计数；没有收到的指标不伪造为 0。

已确认字幕保持顺序和稳定 ID；用户上滑时停止自动跟随，显示“回到最新（N 条）”。失败译文保留英文，并在会话结束后允许单条或全部重试。字幕历史限制为最近 1000 条，当前会话结束后不落盘。

原文默认黄色、译文默认绿色，错误固定使用主题错误色；悬浮字幕支持 20%～100% 背景透明度和有限字号调整。

### 4.3 模型准备页

模型卡显示用途文案、大小、准备状态、运行时支持状态、进度、当前下载源、校验和错误。E2B 在下拉框中带“推荐”，卡片带“优先推荐 · 实时首选”。用户可以下载、取消、重新下载、导入或删除；下载完成前不能使用，大小和 SHA-256 不一致不能启用。

### 4.4 设置页

设置包括字幕字号、原文／译文颜色、主题、语料 profile、动态术语提示、Gemma CPU 辅助线程和悬浮字幕透明度。主题默认 `system`，用户明确选择的浅色／深色会持久化；外部翻译配置只为未来开关保留。

## 5. 技术架构与运行参数

### 5.1 变体

| Flavor | 引擎 | 模型 | 定位 |
| --- | --- | --- | --- |
| `gemmaE2E` | LiteRT-LM Android 0.17 | Gemma 4 E2B/E4B `.litertlm` | 当前主线 |
| `cascade` | whisper.cpp＋原生翻译路径／ML Kit | Whisper、GGUF Qwen、Silero 清单 | 旧兼容与对照 |
| `qwenE2E` | MNN | Qwen2.5 Omni 3B | 实验变体 |

Flutter／Dart 负责页面、会话状态、字幕排序、上下文和语料；Kotlin 负责 AudioRecord、播放捕获、生命周期、队列、温度和运行时桥接；Gemma flavor 的端到端推理由 LiteRT-LM Kotlin API 完成。原生旧引擎仍编译在 cascade 路径中，但不参与 Gemma 主线。

### 5.2 Gemma Android 参数

- 输入：16 kHz、单声道 PCM；Gemma 使用 `VOICE_RECOGNITION` 音频源，设备音频模式使用播放捕获。
- 分段：固定 5 秒窗口、0 重叠；音频连续收集，除精确全零窗口外不使用 RMS 作为语音门。末尾不足一个完整窗口时按剩余音频收尾。
- 调度：单一推理 worker；保留正在执行的窗口，替换尚未开始的旧窗口，防止慢设备无限积压。
- LiteRT-LM：GPU 优先，CPU 回退；E2B/E4B 开启 `ExperimentalFlags.enableSpeculativeDecoding`，`EngineConfig.maxNumTokens=768`，`ConversationConfig.maxOutputToken=128`，`topK=1`、`temperature=0`、关闭 thinking。
- Cache：Android 使用应用 `cacheDir`，即磁盘 cache；本机 CPU 评测才可以比较 `memory` cache。App 启动不插入 dummy warmup，避免增加用户开始录音前的等待。
- 超时：单个 Gemma 窗口 watchdog 15 秒；取消、暂停、结束或代次过期后的结果不会回写字幕。
- 线程：应用设置接受 2／4／6／8，默认 4；Gemma 音频编码和 CPU 回退使用同一线程数。

### 5.3 Cascade 当前行为

Cascade 仍使用 16 kHz 单声道音频、能量／停顿分段、Whisper 识别和 ML Kit 或 GGUF 翻译。Silero 在当前 Android 兼容路径中不作为启动必需项；这条路线保留用于历史对照，不是 Gemma E2E 的参数基线。新模型选择不再以这条路线为主。

## 6. 模型策略与已知实验结果

### 6.1 模型目录

| 模型 | 用途 | 当前判断 |
| --- | --- | --- |
| Gemma 4 E2B LiteRT-LM | 实时字幕 | 默认、优先推荐 |
| Gemma 4 E4B LiteRT-LM | 更看重英文识别质量的字幕 | 可选质量档，延迟明显更高 |
| Whisper small/base English | 英文专用识别对照 | 旧级联候选，不是通用多语言默认 |
| Qwen2.5 0.5B／Qwen3.5 0.8B GGUF | 级联本地翻译实验 | 暂停下一步；Qwen3.5 真实内存复核失败 |
| Qwen Omni 3B MNN | 端到端实验 | 不作为当前主线 |
| NLLB 600M | 多语言翻译候选 | 当前 encoder-decoder 运行时不支持 |

TranslateGemma 4B 的 `litert-community` 文件是 MediaPipe Web `.task`，不是 LiteRT-LM `.litertlm`；LiteRT-LM 0.17 无法加载，因此没有加入当前目录和金标对比。

### 6.2 本机金标探索

以下均为同一约 120 秒音频、5 秒窗口、4 线程、128 输出、6 GiB cgroup、memory cache、1 个 warmup、MTP＋768 的当前探索口径。WER 排除了金标中明确标记为不确定的 cue，不代表产品整体准确率：

| 指标 | Gemma 4 E2B | Gemma 4 E4B |
| --- | ---: | ---: |
| 平均窗口推理 | 2.862 s | 5.311 s |
| P50 / P95 | 2.772 / 3.895 s | 5.081 / 6.673 s |
| RTF | 0.572 | 1.062 |
| 峰值 RSS | 约 2.15 GiB | 约 3.85 GiB |
| 英文 WER | 29.90% | 22.36% |
| 双语窗口率 | 95.83% | 100% |

E4B 的英文识别质量在这份样本上更好，但在本机约慢一倍以上，且专名／中文语义没有同步达到可用标准；它不适合当前实时默认。完整命令和逐窗口结果见 [Gemma 4 加速探索](../evaluation/gemma4_acceleration_exploration.md) 与 [E2B/E4B 对比](../evaluation/gemma4_e4b_exploration.md)。

### 6.3 手机实测状态

当前设备实测报告的 Gemma 推理范围为：E2B 约 600 ms～1.6 s，E4B 约 2.6 s～6 s。E2B 的体感适合实时字幕；E4B 会产生明显滞后，只适合质量优先、可接受延迟的场景。设备型号、系统、温度、电量、冷／热启动和端到端采集到显示延迟仍需补齐，不能直接作为跨设备验收。

## 7. 数据、隐私和异常处理

- 原始音频留在原生内存，不写入应用数据；默认不上传音频。
- 字幕、模型偏好、主题和语料选择按现有功能分别处理；字幕只保留当前会话，偏好和模型完整性收据持久化。
- 模型下载需要网络；预置来源支持测速、断点、切源和完整性校验。模型准备完成后可以飞行模式运行。
- ML Kit 语言包由 Google SDK 下载和管理，不能被 App 替换下载源；这条旧级联路线不应被描述为完全不联网。
- Debug 诊断写入 `~/Downloads` 对应的 Android 公共 Downloads；Release mode 关闭诊断。诊断包含阶段、延迟、状态和资源统计，不包含音频、完整字幕或密钥。
- 内存不足、温度严重、麦克风被系统静音、播放投影撤销或模型缺失时，停止相关任务并保留可回看的英文／错误标记；不自动切换付费服务或未知模型。
- 翻译失败保留英文；超时、无效回复和过期代次不会覆盖后续字幕。结束回看允许受控重试。

## 8. 质量、性能与发布门槛

### 8.1 目标门槛

正式验收仍要求在指定设备和独立保留集上同时满足：

| 指标 | 目标 |
| --- | --- |
| 信息理解、术语、提供名称正确率 | 各至少 90% |
| 关键否定、数字和比较关系错误 | 0 |
| 稳定中文显示延迟 | P50 ≤ 3 s，P95 ≤ 6 s |
| 长句首条可读字幕 | 至少 90% ≤ 8 s |
| 热／冷模型准备 | P95 ≤ 3 s／≤ 8 s |
| 连续运行 | 3 次 60 分钟，无崩溃、ANR 或持续积压 |
| 静音／音乐负例 | 不产生虚构字幕 |
| 字幕一致性 | 重复、倒序、旧代次覆盖为 0 |

### 8.2 资源口径

旧 PRD 的 1.5 GiB 是早期优化目标，不能继续作为 Gemma E2B/E4B 的硬上线门槛。当前本机评测统一使用 systemd cgroup 实际内存限制，默认最多 6 GiB、swap 0；不使用 `ulimit -v`，不把 mmap 地址空间当作 RSS。手机端必须分别记录模型运行内存、系统内存压力、温度、电量和是否发生窗口替换，再决定设备级门槛。

### 8.3 当前发布判断

当前仍是开发评测版：E2B 已有可接受的手机体感，但金标 WER、实体质量、长稳、资源和多设备数据不足；E4B 不适合作为实时默认；Qwen3.5 和 TranslateGemma 不能作为当前替代路线。任何 release-mode APK 都不能据此标记为产品验收通过。

## 9. 评测与复现

固定本机路径：

- JDK：`~/Tools/java/eclipse-temurin-jdk17`
- LiteRT-LM 环境和模型：`~/Tools/litert`
- 音频、金标、日志：`~/Downloads/opencaption`

首次准备：

```bash
scripts/setup-gemma-eval
scripts/fetch-gemma-litert
```

标准实验应明确模型 SHA-256、LiteRT-LM 版本、任务、system profile、窗口／重叠、context、输出 token、MTP、cache、warmup、线程和 cgroup 限制。例如：

```bash
OPENCAPTION_MEMORY_MAX_MB=6144 scripts/run-gemma-eval \
  "$HOME/Downloads/opencaption/clip.wav" \
  --model "$HOME/Tools/litert/models/gemma-4-E2B-it.litertlm" \
  --speculative-decoding=true \
  --cache-mode=memory \
  --warmup=1 \
  --max-context-tokens=768
```

报告必须同时保留原始输出和金标对齐结果；`e2e_ok` 只代表协议字段完整，不代表语义正确。Android 日志分析要区分模型推理耗时、队列等待和真正的“语音结束到字幕显示”端到端延迟。

测试集要求沿用独立开发／保留划分，覆盖英语口音、噪声、术语、专名、否定、数字、静音和音乐；手机实录优先于干净音轨。当前尚未完成 3×60 分钟、保留集、飞行模式、温升／电量和多设备复测。

## 10. 发布、版本和文档规则

- `scripts/build-apk gemmaE2E` 生成 Debug 测试包；`OPENCAPTION_BUILD_MODE=release OPENCAPTION_DIAGNOSTICS=false scripts/build-apk gemmaE2E` 生成 Release mode 测试包。
- 两种包使用固定本地开发签名以便覆盖安装和保留应用私有模型；正式发布前必须替换签名并重新完成 LiteRT-LM 反射／原生绑定验证。
- Release 暂不启用 R8 和资源缩减；诊断面板、公共 Downloads 日志和评测计数只存在于 Debug／测试渠道。
- 每次默认模型、LiteRT-LM 版本、MTP／context、内存口径或用户可见能力变化，都要同时更新 README、本文和实施记录，并保留实验报告的限制说明。

## 11. 后续与风险

1. 首先完成 E2B Android GPU 的冷／热启动、端到端延迟、内存、温度、电量和 60 分钟稳定性记录。
2. 以 E2B 为默认继续做独立保留集质量；E4B 仅在质量收益足以抵消延迟和内存时保留。
3. 若要继续 TranslateGemma，必须先有 LiteRT-LM 可加载的官方 `.litertlm` 包，或明确增加受支持的 MediaPipe Web／Android GPU 路径；不能把 `.task` 文件当作 LiteRT-LM 模型。
4. Qwen 系列若再次评估必须先解决真实 cgroup 内存问题；在此之前不扩大模型或内存上限。
5. 继续完善第三方播放 App 兼容性、iPhone、字幕保存／导出和更多领域包，但不以这些工作替代当前主线验收。

## 12. 参考资料和术语

- [LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM)
- [Gemma 4 E2B LiteRT Community](https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm)
- [Gemma 4 E4B LiteRT Community](https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm)
- [Android AudioPlaybackCapture](https://developer.android.com/reference/android/media/AudioPlaybackCaptureConfiguration)
- [模型与加速探索报告](../evaluation/gemma4_acceleration_exploration.md)

| 术语 | 含义 |
| --- | --- |
| E2E | 端到端语音模型，Gemma 同时完成音频理解、转写和中文输出 |
| MTP / speculative decoding | LiteRT-LM 的多 token 预测／推测解码开关 |
| RTF | 推理耗时与音频时长的比值，小于 1 才有实时余量 |
| WER | 英文词错误率，只用于识别诊断，不等于中文语义准确率 |
| P50／P95 | 延迟分布的中位数和 95 分位数 |
| cgroup | Linux 实际资源控制；本项目用于限制评测进程内存并禁用 swap |
| 领域 profile | 通用或 CS2 术语选择；默认是通用，不自动注入整张词表 |

## 13. P2：同机直播和悬浮字幕的扩展

Gemma Android 路径已经实现了一个受限的本设备播放音频＋悬浮字幕实验入口，但它不等于支持所有直播 App。后续专项必须逐一验证音频共享策略、耳机／外放、横屏遮挡、锁屏、通知、DRM、30 分钟稳定性和用户停止操作。

其他直播 App 的适配、后台规则扩展、iOS 同机捕获和系统级悬浮能力仍保持 P2；未完成前不在产品首页宣称“支持斗鱼或所有直播 App”。

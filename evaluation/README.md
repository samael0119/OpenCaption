# 本机评测与历史记录

2026-10-14当前轮全部在本机完成，不连接/探测手机，不运行ADB，不把Android实机作为本轮依赖。下方早期实机命令和发布要求保留为历史，不能当本轮执行命令。完成批次不重跑；先读[执行检查点](../docs/v0.2.0执行检查点.md)。

当前成果见[晨间报告](../docs/v0.2.0晨间报告.md)和[关口复查](v020_acceptance_review_20261014.md)。完整版本仍未通过质量关口；此前模型资源3×60min不等于新的核心/widget联合3×60min。当前候选129 Dart/39 Kotlin/分析/APK/Web/签名已通过，不据此填写内容质量或屏幕延迟达标。

| 当前证据入口 | 能证明什么 | 不足或状态 |
| --- | --- | --- |
| [短输入候选](v020_short_input_20261014.md)、[词库治理](v020_corpus_governance_20261014.md) | 有限独立短答收益、条件/反例与加载回退机制 | 关键no/six及独立CS2术语正向质量仍未过 |
| [关联候选](v020_related_retrieval_20261014.md)、[上下文时效](v020_context_lifetime_20261014.md) | 一跳候选诊断、证据时效与防迟到污染 | 候选和短语义前文未接正常生成；不能用零召回/弃权冒充净收益 |
| [场景纠正与UI](v020_scene_correction_20261014.md) | 当前会话可选纠正、命名地图、预算优先、实际浅深交互 | 手动纠正不替代自动场景质量，截图不是实际字幕延迟 |
| [核心/widget联合预检](v020_joint_live_preflight_20261014.md) | 实际JVM核心/单模型/控制器/组件事件与资源链路 | 90s烟测已过，三份3600s在途；Android采集/调度/watchdog/真实屏幕不在该链路 |
| [独立参考来源](v020_reference_sources_20261014.md)、[六例对照冻结](v020_fleurs_pilot_20261014.md) | 来源/人工参考/PCM核验、输出前配置和评分规则 | 原12例准备不完整，六例12请求尚未推理；通用朗读不替代CS2赛事金标 |

顺序按检查点推进：在途模型运行时不构建；联合三份实际审计全部exit0/服务结束后才能启动已冻结六例有限控制，已有输出拒绝隐式重跑。运行请求数与资源日志不是开发token统计，也不是人工质量评分。

v0.2.0 的首轮 CPU 分段、提示容量与场景检索实验见 [S0 可行性验证](s0_feasibility_20261013.md)；Android 与正式质量验收仍待完成。

补充的 768/1024、别名与转会关系对照见 [context 与转会词库](s0_context_roster_20261013.md)。

最新的提示协议、实际时钟回放与场景恢复结果见 [协议与实时节奏验证](s0_protocol_live_20261013.md)；高级提示和自动场景仍有未通过的关口。

额度恢复后已完成 [本机续做验证](s0_local_followup_20261013.md)：严格静音适配、同模板术语对照、地图关系交集/检索和队列降速轨迹；发现全零音频的提示虚构，新增 frozen 条件纠正。本轮没有连接或探测手机，完整质量关口仍未通过。

已有真实比赛/采访音频与手机日志；当前 Gemma 主线质量、MTP 和 E2B/E4B 对比见 [Gemma 4 加速探索](gemma4_acceleration_exploration.md)。不要用单元测试或协议解析通过率替代质量验收。

历史三个诊断配置入口为`bash scripts/quality-round`，不是本次接续入口，不重跑已完成批次。仅本地读取音频，不上传；本轮模型使用明确6 GiB cgroup硬限制与swap0，4 GiB仅为历史压力对照。以下早期命令和发布门槛保留作历史参考，其中级联模型对比不再执行。

## Ubuntu 快速回放

Ubuntu 和 Android 都固定使用 `litert-community/gemma-4-E2B-it-litert-lm` 的同一个 `.litertlm` 部署包。Ubuntu 使用 LiteRT-LM Linux CPU，Android 使用 LiteRT-LM Android GPU/CPU；两端模型和协议一致，但 Android 主线使用 MTP、768 context、应用磁盘 cache，Ubuntu 的参数必须显式对齐后才可做严格延迟比较。Ubuntu 主要筛选音频分段、提示词和字幕质量，性能与温控仍需 Android 实机验收。

首次准备 CPU 环境并下载模型（约 2.58 GB）。LiteRT-LM 环境和模型分别放在 `/home/hyh/Tools/litert/litert-venv`、`/home/hyh/Tools/litert/models`，不占用仓库目录：

```bash
scripts/setup-gemma-eval
scripts/fetch-gemma-litert
scripts/run-gemma-eval evaluation/private/interview.wav --limit-windows 3
```

下面描述早期固定窗回放器：ffmpeg转16k单声道，5秒窗/500ms重叠、1024 context、128输出、逐段串行记录。它不能作为当前Android候选逻辑或新联合验收的配置；当前候选为因果停顿/5秒兜底、无重叠、768 context。各实验以自己的冻结清单/实际参数为准，不把离线看未来的边界或旧重叠策略当实时改善。

只检查解码和分段、不下载或加载模型：

```bash
/home/hyh/Tools/litert/litert-venv/bin/python evaluation/gemma_replay.py evaluation/private/interview.wav --prepare-only
```

`scripts/run-gemma-eval` 默认用 systemd cgroup 把实际内存硬限制为 6144 MiB：5376 MiB 开始节流，6144 MiB 强制停止，并禁止该进程使用 swap。不能创建 cgroup 时脚本直接失败，不会无上限运行。可用 `OPENCAPTION_MEMORY_MAX_MB=4096` 或更低值做压力对照。保持逐段串行，不要同时运行 Android 构建或另一份模型；先用 `--threads 2 --limit-windows 1` 冒烟。

分析 Android 日志时使用同一口径：

```bash
python3 evaluation/android_log_metrics.py ~/Downloads/opencaption/opencaption_*.log.txt
```

脚本会分别输出模型准备耗时、严格零 PCM 跳过数、推理成功 / 格式失败、超时、待处理替换、队列等待 P50/P95、推理 RTF/P50/P95、原生堆峰值和热状态。`e2e_ok` 只表示协议字段完整，不代表英文或中文语义正确。

## 目标素材与拆分（尚未全部具备）

准备授权使用的 30 段采访（约 45 分钟、至少 10 位说话人），按场次和说话人隔离为 20 段开发集、10 段保留集，另备 5 分钟静音 / 音乐 / 观众声。素材和人工字幕放在忽略版本控制的 `evaluation/private/`；结果放在 `evaluation/results/`。先用人工英文评翻译，再测 ASR 和完整声学链路。保留集不用于调参。

每段登记来源和授权、场次、说话人、时长、划分、人工英文、参考中文、术语 / 名称、关键否定 / 数字。按语义单元人工标注原话结束时间，不用模型窗口结束时间代替。

## 每次运行登记

记录设备型号、系统、APK 版本、引擎提交、模型 SHA-256、翻译模式、线程数、冷 / 热启动、亮度、环境温度、初始电量和网络。对比 small.en / base.en、ML Kit / Qwen、CPU 2 / 4 线程。离线测试在模型齐全后开启飞行模式。

逐句记录语义单元 ID、原话结束时间、首条中文展示时间、成功 / 失败 / 遗漏、重复或乱序、理解 / 术语 / 名称判定及关键错误。报告成功覆盖率与全部失败，延迟仅对成功句统计并明确分母；长句首条延迟单独记录。现有应用诊断中的 ASR 耗时是单次推理耗时，不能代表端到端字幕延迟。

## PRD 发布门槛

理解 / 术语 / 名称分别 ≥90%，关键否定和数字错误为 0；中文延迟 P50 ≤3 秒、P95 ≤6 秒；≥90% 长句首条 ≤8 秒；热准备 P95 ≤3 秒、冷准备 ≤8 秒；重复乱序 0；静音 / 音乐虚构字幕 0。至少 3 次 60 分钟，无崩溃、ANR 或持续积压。

内存 1.5 GB 和离线耗电 ≤20 个百分点 / 小时为初始预算，超预算须单独评审。固定亮度 50%、室温且不充电。收集 `adb shell dumpsys meminfo dev.opencaption.opencaption`、温度、电量与故障记录，避免在默认日志中保存字幕或 Key。

外部翻译另测 150 ms 额外 RTT、1% 丢包、10 秒断连；不能以外部模式成绩代替离线验收。当前没有自动计算最终验收结论的工具，人工记录完成前不得填写“通过”。

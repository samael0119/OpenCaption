# 实机评测

已有真实比赛/采访音频与手机日志；当前 Gemma 主线质量迭代见 [第四轮指标与实验](round4_quality.md)。不要用单元测试或协议解析通过率替代质量验收。

快速重复本轮三个诊断配置：`bash scripts/quality-round`。仅本地读取音频，不上传；每次模型运行沿用 4 GiB 硬限制。以下早期发布门槛保留作历史参考，其中级联模型对比不再执行。

## Ubuntu 快速回放

Ubuntu 和 Android 都固定使用 `litert-community/gemma-4-E2B-it-litert-lm` 的同一个 `.litertlm` 部署包。Ubuntu 使用 LiteRT-LM Linux CPU，Android 使用 LiteRT-LM Android GPU/CPU；模型与协议一致，但硬件后端不同，所以 Ubuntu 可快速筛选音频分段、提示词和字幕质量，性能与温控仍需 Android 实机验收。

首次准备 CPU 环境并下载模型（约 2.58 GB）。LiteRT-LM 环境和模型分别放在 `/home/hyh/Tools/litert/litert-venv`、`/home/hyh/Tools/litert/models`，不占用仓库目录：

```bash
scripts/setup-gemma-eval
scripts/fetch-gemma-litert
scripts/run-gemma-eval evaluation/private/interview.wav --limit-windows 3
```

回放器先用 ffmpeg 转为 16 kHz 单声道 PCM，再按 Android 当前逻辑切成 5 秒窗口、重叠 500 ms，逐段串行推理；不会同时驻留第二个模型，也不会建立并行推理队列。此参数来自真实 CS2 音频的 3 秒 / 5 秒本地对比：5 秒窗减少了断句并降低提交频率。上下文限定为模型原生支持的最小 1024-token prefill，默认仅生成 128 个 token，并关闭 thinking。每个窗口立即写一行 JSONL 到 `evaluation/results/`，即使某段失败也会继续，便于比较原始输出、解析结果、延迟和峰值常驻内存。

只检查解码和分段、不下载或加载模型：

```bash
/home/hyh/Tools/litert/litert-venv/bin/python evaluation/gemma_replay.py evaluation/private/interview.wav --prepare-only
```

`scripts/run-gemma-eval` 默认用 systemd cgroup 把实际内存硬限制为 4096 MiB：3584 MiB 开始节流，4096 MiB 强制停止，并禁止该进程使用 swap。不能创建 cgroup 时脚本直接失败，不会无上限运行。可用 `OPENCAPTION_MEMORY_MAX_MB=3584` 进一步收紧。保持逐段串行，不要同时运行 Android 构建或另一份模型；先用 `--threads 2 --limit-windows 1` 冒烟。

分析 Android 日志时使用同一口径：

```bash
python3 evaluation/android_log_metrics.py ~/Downloads/opencaption/opencaption_*.log.txt
```

脚本会分别输出模型准备耗时、严格零 PCM 跳过数、推理成功 / 格式失败、超时、待处理替换、队列等待 P50/P95、推理 RTF/P50/P95、原生堆峰值和热状态。`e2e_ok` 只表示协议字段完整，不代表英文或中文语义正确。

## 素材与拆分

准备授权使用的 30 段采访（约 45 分钟、至少 10 位说话人），按场次和说话人隔离为 20 段开发集、10 段保留集，另备 5 分钟静音 / 音乐 / 观众声。素材和人工字幕放在忽略版本控制的 `evaluation/private/`；结果放在 `evaluation/results/`。先用人工英文评翻译，再测 ASR 和完整声学链路。保留集不用于调参。

每段登记来源和授权、场次、说话人、时长、划分、人工英文、参考中文、术语 / 名称、关键否定 / 数字。按语义单元人工标注原话结束时间，不用模型窗口结束时间代替。

## 每次运行登记

记录设备型号、系统、APK 版本、引擎提交、模型 SHA-256、翻译模式、线程数、冷 / 热启动、亮度、环境温度、初始电量和网络。对比 small.en / base.en、ML Kit / Qwen、CPU 2 / 4 线程。离线测试在模型齐全后开启飞行模式。

逐句记录语义单元 ID、原话结束时间、首条中文展示时间、成功 / 失败 / 遗漏、重复或乱序、理解 / 术语 / 名称判定及关键错误。报告成功覆盖率与全部失败，延迟仅对成功句统计并明确分母；长句首条延迟单独记录。现有应用诊断中的 ASR 耗时是单次推理耗时，不能代表端到端字幕延迟。

## PRD 发布门槛

理解 / 术语 / 名称分别 ≥90%，关键否定和数字错误为 0；中文延迟 P50 ≤3 秒、P95 ≤6 秒；≥90% 长句首条 ≤8 秒；热准备 P95 ≤3 秒、冷准备 ≤8 秒；重复乱序 0；静音 / 音乐虚构字幕 0。至少 3 次 60 分钟，无崩溃、ANR 或持续积压。

内存 1.5 GB 和离线耗电 ≤20 个百分点 / 小时为初始预算，超预算须单独评审。固定亮度 50%、室温且不充电。收集 `adb shell dumpsys meminfo dev.opencaption.opencaption`、温度、电量与故障记录，避免在默认日志中保存字幕或 Key。

外部翻译另测 150 ms 额外 RTT、1% 丢包、10 秒断连；不能以外部模式成绩代替离线验收。当前没有自动计算最终验收结论的工具，人工记录完成前不得填写“通过”。

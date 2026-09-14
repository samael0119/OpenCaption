# Gemma 4 E4B 推理加速方案探索

> 本文是方案探索记录，不属于优化轮次（roundN）。

## 结论

- 在当前 CPU 环境、LiteRT-LM 0.17、相同的 6 GiB cgroup 内存上限下，开启 MTP（Python API `enable_speculative_decoding=True`；CLI 为 `--speculative-decoding=true`，兼容别名为 `--enable-speculative-decoding=true`）相对关闭 MTP，平均窗口推理延迟从 **7.657 s 降到 5.541 s**，约 **1.38x**，P95 从 10.576 s 降到 7.044 s；金标质量完全一致。
- 将 context 上限从 1024 降到 768 后，MTP 平均延迟进一步降到 **5.311 s**，比 1024 再快约 **4.1%**，本次金标上 WER、实体召回、格式结果均无变化。768 可作为下一步手机 GPU 测试的首选边界；这只能说明当前样本无损，不能宣称对所有音频都无损。
- 当前 E4B LiteRT-LM 模型/runtime 使用 512 context 会触发 `DYNAMIC_UPDATE_SLICE` shape/allocate 错误，MTP 开关与否都一样失败，因此暂不采用 512。
- 4 GiB 下 MTP smoke test 明显受到内存压力拖慢；放宽到 6 GiB 后稳定运行。MTP + 1024 的进程峰值 RSS 约 4.02 GiB，所以 6 GiB 是更稳妥的实验上限，但不能据此保证任意设备只需 4 GiB 物理内存。
- `scripts/run-gemma-eval` 的默认 `MemoryMax` 已放宽为 6 GiB；需要复现 4 GiB 对照时设置 `OPENCAPTION_MEMORY_MAX_MB=4096`。

## 实验条件

- 模型：`gemma-4-E4B-it.litertlm`，LiteRT Community 版，SHA-256：`0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0`。
- LiteRT-LM：0.17。
- 音频：`~/Downloads/opencaption/clip.wav`；金标：`~/Downloads/opencaption/clip_gold_bilingual.srt`。
- 5 秒窗口、0 overlap、4 CPU threads、最大输出 128 tokens，共 24 个窗口。
- 对照实验统一使用 `cache memory`、1 个 warmup 窗口；warmup 不计入延迟，但同一个窗口随后重新计入完整质量评估。
- 内存由 systemd cgroup 控制：`MemoryMax=6G`、`MemorySwapMax=0`。4 GiB 仅用于单窗口压力 smoke test及已有基线。

## 指标对比

| 配置 | 平均窗口延迟 | P50 | P95 | RTF | 峰值 RSS | WER（排除不确定 cue） |
|---|---:|---:|---:|---:|---:|---:|
| 已有基线：4 GiB，默认 MTP，disk cache，无 warmup | 13.951 s | 12.898 s | 18.404 s | 2.790 | 3.25 GiB | 22.36% |
| 6 GiB，MTP off，memory cache + warmup，context 1024 | 7.657 s | 7.173 s | 10.576 s | 1.531 | 3.59 GiB | 22.36% |
| 6 GiB，MTP on，memory cache + warmup，context 1024 | 5.541 s | 5.244 s | 7.044 s | 1.108 | 3.93 GiB | 22.36% |
| 6 GiB，MTP on，memory cache + warmup，context 768 | 5.311 s | 5.081 s | 6.673 s | 1.062 | 3.85 GiB | 22.36% |

所有可完成配置都得到相同的 24/24 字幕窗口，bilingual window rate 为 1.0，语言及格式审计无警告。完整 WER 为 21.87%；排除金标中标记为不确定的 cue 25 后为 22.36%。实体对齐召回均为 2/20（10%）。因此当前样本没有观察到 MTP 或 768 context 引入质量回退。

## E2B 复核

E2B 使用同一份音频、金标、窗口、4 线程、128 输出、6 GiB cgroup、memory cache 和 1 个 warmup 复测：

| 配置 | 平均窗口延迟 | P50 | P95 | RTF | 峰值 RSS | 双语窗口率 | WER（排除不确定 cue） |
|---|---:|---:|---:|---:|---:|---:|---:|
| 已有 round8 基线 | 3.354 s | 3.208 s | 4.636 s | 0.671 | 1.90 GiB | 95.83% | 29.90% |
| 6 GiB，MTP off，memory cache + warmup，context 1024 | 3.174 s | 3.079 s | 4.318 s | 0.635 | 1.96 GiB | 95.83% | 29.90% |
| 6 GiB，MTP on，memory cache + warmup，context 1024 | 2.988 s | 2.969 s | 3.991 s | 0.598 | 2.19 GiB | 95.83% | 29.90% |
| 6 GiB，MTP on，memory cache + warmup，context 768 | 2.862 s | 2.772 s | 3.895 s | 0.572 | 2.15 GiB | 95.83% | 29.90% |

在同一套新条件下，E2B 开启 MTP 平均约快 **5.9%**，768 相对 1024 再快约 **4.2%**；WER、实体召回（2/20）和唯一格式无效窗口均保持不变。收益小于 E4B，但方向稳定，故 E2B 也采用 MTP + 768。

## Android 与本机参数对齐

已在 Gemma Android flavor 接入 LiteRT-LM 0.17 的 `ExperimentalFlags.enableSpeculativeDecoding` 和 `EngineConfig.maxNumTokens`：E2B/E4B 均启用 MTP、`maxNumTokens=768`，`maxOutputToken=128` 保持不变；GPU 初始化失败时的 CPU fallback 也使用同一组参数。Android 音频 CPU 线程由原先固定最多 2 线程改为跟随设置值，默认 4，与本机评测一致。

仍有两项有意保留的差异：

- Android 主模型优先 GPU，这是本轮唯一的后端差异；GPU 与音频编码共存时，Android 使用应用可写的磁盘 cache 路径。LiteRT-LM CLI 的 `cache memory` 是 CPU-only 模式，不能直接移植到 Android GPU，因此不能强行改成 `:memory`。
- 本机金标回放使用 CS2 baseline system prompt；应用默认 `CorpusProfile.none` 时使用通用 interview system prompt，这是产品通用化设计，不是 MTP/KV 参数差异。要做严格的手机金标复现，应选择 CS2 profile，或另行让本机回放使用通用 profile。

应用实时路径没有额外 dummy inference warmup，因为这会增加开始录音前的等待；本报告的 warmup 仅用于离线延迟测量。

## 512 context 边界

MTP on/off 两次测试都在 warmup 阶段失败，错误核心为：

```text
DYNAMIC_UPDATE_SLICE ... SizeOfDimension(update, i) <= SizeOfDimension(operand, i)
Failed to allocate tensors
```

这是当前 E4B LiteRT artifact/runtime 的 shape 兼容边界，不是 MTP 单独导致的内存不足；本轮不将 512 作为候选配置。

## 对下一步的建议

1. 手机 GPU 首先测试 **MTP on + context 768 + 应用磁盘 cache**，记录首次窗口和稳定窗口两组延迟；再用 context 1024 做质量/延迟对照。Android GPU 不使用 CPU-only 的 `cache memory`，实时路径也不插入 dummy warmup。
2. MTP 在本机 CPU 上的净收益约 1.38x；官方移动 GPU 的加速幅度不能由 CPU 实验外推，是否接近官方宣称的 GPU 上限需要在手机实测。
3. 当前 APK 已加入 Gemma 4 E4B 模型目录，Android 端已对 E2B/E4B 接入 MTP/768；手机实测时先确认日志中的 `model_backend=gpu`、`speculative_decoding=true` 和 `max_context_tokens=768`，再记录 GPU decode 延迟、峰值内存、温度及队列替换情况。

## 结果文件

- 基线：`evaluation/results/explore-gemma-e4b-clip.jsonl`
- MTP off：`evaluation/results/explore-gemma-e4b-no-mtp-memory-warmup-1024-full.jsonl`
- MTP on / 1024：`evaluation/results/explore-gemma-e4b-mtp-memory-warmup-1024-full.jsonl`
- MTP on / 768：`evaluation/results/explore-gemma-e4b-mtp-memory-warmup-768-full.jsonl`
- E2B MTP off / 1024：`evaluation/results/explore-gemma-e2b-no-mtp-memory-warmup-1024-full.jsonl`
- E2B MTP on / 1024：`evaluation/results/explore-gemma-e2b-mtp-memory-warmup-1024-full.jsonl`
- E2B MTP on / 768：`evaluation/results/explore-gemma-e2b-mtp-memory-warmup-768-full.jsonl`
- 质量评分：`evaluation/results/explore-gemma-e4b-acceleration-score.json`
- E2B 质量评分：`evaluation/results/explore-gemma-e2b-acceleration-score.json`
- 延迟与输出审计：`evaluation/results/explore-gemma-e4b-acceleration-audit.json`
- E2B 延迟与输出审计：`evaluation/results/explore-gemma-e2b-acceleration-audit.json`

模型来源：[Gemma 4 E4B LiteRT-LM（LiteRT Community）](https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm)。

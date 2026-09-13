# 第七轮：暂停恢复、输出边界与同款解析

本轮继续只维护 Gemma E2E，不恢复 Qwen 或级联路线。目标是先消除“暂停/结束后仍长时间占住唯一推理槽”和“模型输出被当作字幕显示”的工程性问题，再用 `clip.wav` 检查输出预算是否是当前速度瓶颈。

## 代码改动

- `CaptionEngine.pause()` 现在会识别当前 epoch 的活动/待处理 E2E 任务：立即取消活动会话、移除待处理窗口、停止接受迟到结果，并记录 `e2e_pause_cancel_requested`。有 E2E 任务时还抑制收音线程的尾段提交；没有 E2E 任务时保留原有尾段行为。这样 Dart 的 `pause → drain` 不再被一个陈旧 E2E 任务无条件拖到看门狗。
- E2E 看门狗固定为 15 秒；Gemma 会话和单次发送均显式 `ThinkingConfig(false, 0)`、`maxOutputToken=128`。不启动第二个模型、不扩大队列。
- Android 与 Ubuntu 解析器统一：只接受可识别的英文/中文两行；兼容运行时偶发的无标签中文第二行；拒绝 JSON、代码围栏、`<think>`/`<analysis>` 和 `Analysis:`/`Reasoning:`/`Explanation:` 前缀。字幕页只接收解析后的字段，不显示原始结构化输出。
- `audit_realtime.py` 对串行 JSONL 的可选实时字段安全降级，不再因缺少 `end_to_output_ms` 使整份报告失败。

## 本地可复现实验

环境保持上一轮口径：LiteRT-LM CPU、4 线程、`MemoryMax=4096 MiB`、禁用 swap；模型为 `/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm`；输入 `/home/hyh/Downloads/opencaption/clip.wav`（约 120 秒）；5 秒窗口、0 重叠、双语 prompt。128-token 结果是上一轮的 `round6-clip-baseline.jsonl`，256-token 结果为 `round7-clip-256.jsonl`，只有输出预算改变。

| 指标 | 128 tokens | 256 tokens | 结论 |
|---|---:|---:|---|
| 窗口 / 引擎错误 | 24 / 0 | 24 / 0 | 无异常 |
| Android 同款解析有效 | 24/24 | 24/24 | 输出内容逐窗口完全相同 |
| 英文 WER（排除尾部不完整 cue） | 25.06% | 25.06% | 无质量收益 |
| 已知实体对齐召回 | 10.0% | 10.0% | 专名仍是瓶颈 |
| 平均推理 | 3.487 s | 3.452 s | 单次复测波动，不能归因 |
| 推理 P50 | 3.234 s | 3.337 s | 无稳定改善 |
| 推理 P95 | 4.328 s | 4.414 s | 更大预算没有收益 |
| 峰值 RSS | 1,876.6 MiB | 1,923.0 MiB | 256 更占内存 |
| 总耗时 | 88.974 s | 84.624 s | 同机单次差异，不作性能结论 |

256-token 的逐窗口 `(status, English, Chinese)` 摘要与 128-token 完全一致（SHA-256：`e54e9e3d4b2cc5763e51945dba5335fad5534a8789d36cb158753274c4df2536`），因此当前不应继续增加生成预算；128 仍是手机默认安全上限。

## 验证结果

- Python 评测：20 个测试通过。
- Flutter：36 个测试通过；静态分析仅有既存的 3 条 `curly_braces_in_flow_control_structures` 信息（`lib/core/corpus.dart`），不是本轮错误。
- Android `:app:testGemmaE2EDebugUnitTest`：17 个测试通过（AudioBuffer 2、EnergySegmenter 4、E2eProtocol 11）。
- Android `:app:compileGemmaE2EDebugKotlin`：JDK 17 + 项目 SDK 36 编译成功。

## APK

已用 `/home/hyh/Tools/java/eclipse-temurin-jdk17` 构建 Gemma E2E debug APK，并通过固定开发证书校验，签名未变化，可覆盖安装而不会触发模型目录重下载：

`build/app/outputs/flutter-apk/app-gemmae2e-debug.apk`

文件大小约 194 MiB，SHA-256：`1be5262839e650e50d6ef253a747e9bcd17b24f4ee6ce53cc60c06600abbdf50`。

## 下一次真机验证

请用本 APK 分别做一次前台麦克风和后台系统音频：开始后运行约 20 秒再暂停/结束，再重新开始。重点从日志检查：

1. 出现 `e2e_pause_cancel_requested` 后，`asr_drain_complete` 是否在数秒内出现；
2. `e2e_timeout` 的 `limit_ms` 是否为 15000，是否还有 `e2e_queue_replaced` 长时间累积；
3. 播放采集无源时是否出现 `segment_skip ... reason=e2e_exact_zero`，且低电平人声不会被跳过；
4. 30 分钟内 `e2e_resources` 的 native heap、thermal、推理 P95 与有效双语段数是否稳定。

本轮没有声学模型或术语库质量提升；金标上的 WER/实体指标不变，下一阶段应继续针对英文专名、比赛口音与音频清晰度做受控输入实验，而不是再放宽输出长度。

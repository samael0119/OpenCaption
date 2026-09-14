# 方案探索：Qwen 内存复核与 TranslateGemma-4B-IT 可行性

日期：2026-09-14。所有推理均限定在本机、离线音频 / 本地结果和 LiteRT 相关运行时范围内；没有使用 llama.cpp 或第三方模型包。

## 结论

1. Qwen3.5-0.8B 按此前金标评测使用的 CPU 命令和真实 cgroup 限制复核，仍在约 6 GiB 内存上限处被内核以 `CONSTRAINT_MEMCG` OOM 杀掉，没有生成可评分结果。Qwen 系列暂不作为下一步方向。
2. 官方 `litert-community/TranslateGemma-4B-IT` 下载包不是 LiteRT-LM 的 `.litertlm` 部署包，而是面向 MediaPipe Web LLM Inference API 的 `.task` flatbuffer。LiteRT-LM 0.17 不能打开它；官方仓库也没有提供 `.litertlm` 变体。
3. 官方 Web 探针可以进入模型加载阶段，但在本机没有完成一次可回调的翻译。加载阶段进程 RSS 合计约 5.5 GiB，受限复测使用 6 GiB `memory.max`、`memory.swap.max=0`，最终没有得到有效输出。因此本次探索不能给 TranslateGemma 计算金标翻译准确率、WER、P50/P95 或 RTF；不能把“无结果”当成质量差或质量好。

## Qwen 内存复核

命令关键参数与金标回放保持一致：LiteRT-LM 0.17、CPU、4 线程、`--cache no`、关闭 thinking、`--max-num-tokens 128`、贪心解码，并通过 systemd cgroup 限制实际内存、禁用 swap。

内核日志记录：

```text
oom-kill: constraint=CONSTRAINT_MEMCG
oom_memcg=.../run-r617d389333b442c88ddce163a9921093.scope
task=litert-lm
total-vm=7411168kB
anon-rss=6276908kB
file-rss=740416kB
```

结论是运行时内存问题已经可复现，不再继续尝试更大的内存或 Qwen 尺寸。

## TranslateGemma 文件与兼容性

下载位置：`/home/hyh/Tools/litert/models/translategemma-4b-it-int8-web.task`

| 项目 | 值 |
|---|---|
| 来源 | `litert-community/TranslateGemma-4B-IT` |
| 文件大小 | 3,896,377,344 bytes（约 3.63 GiB） |
| SHA-256 | `a70d505455cef5aebb2bdb43e379323a1b36bb5a05e1a99dde1fdab37947ec0e` |
| 文件头 | `TFL3`（LiteRT/TFLite flatbuffer） |
| LiteRT-LM 0.17 | 失败：`Invalid magic number ... TFL3` / `Unable to open zip archive` |

直接查询官方仓库文件列表只得到 `translategemma-4b-it-int8-web.task`、`configuration.json`、`README.md` 和 `.gitattributes`，没有官方 `.litertlm` 包。官方说明见 [TranslateGemma LiteRT Community 模型页](https://huggingface.co/litert-community/TranslateGemma-4B-IT) 和 [官方 ModelScope 仓库](https://modelscope.cn/models/litert-community/TranslateGemma-4B-IT)。

## 官方 Web 路径冒烟

使用官方 `@mediapipe/tasks-genai` Web API、Chrome headless、SwiftShader，并将 Chrome 实际父 cgroup 设置为 `MemoryMax=6G`、`MemorySwapMax=0` 后导航到模型页。页面进入模型初始化但没有产生翻译回调；在未正确覆盖 Chrome 子 cgroup 的第一次探针中，GPU 子进程 RSS 约 4.3 GiB，Chrome 相关进程 RSS 合计约 5.5 GiB。正确施加父 cgroup 限制后的复测也未完成推理。

这与官方 README 给出的 Web 资源量级一致：约 4.5 GB GPU memory、0.79 GB CPU memory、3.9 GB model size，且官方性能数据来自 Chrome + Apple M4 Max，不代表本机性能。[官方 MediaPipe LLM Inference 文档](https://ai.google.dev/edge/mediapipe/solutions/genai/llm_inference)

当前隔离的 Python MediaPipe 1.0.1 环境也没有 `mediapipe.tasks.python.genai` 的 LLM 推理运行时；没有把它混入共享 LiteRT-LM 环境，也没有转用第三方 `.litertlm` 文件。

## 与 Gemma 4 E2B 对比

当前可复现的 Gemma E2B 对照是 `/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm`、LiteRT-LM 0.17 CPU 4 线程、4 GiB cgroup、`clip.wav` 120 秒、5 秒无重叠窗口：

| 指标 | Gemma 4 E2B round8 | TranslateGemma 4B 本次探索 |
|---|---:|---:|
| 运行格式 | `.litertlm`，可直接由 LiteRT-LM 加载 | `.task`，LiteRT-LM 不兼容 |
| 窗口 / 有效双语窗口 | 24 / 23 | 未进入音频批量评测 |
| 英文 WER（排除金标第 25、29 条） | 29.87% | 无样本 |
| 推理 P50 | 3,208 ms | 无样本 |
| 推理 P95 | 4,636 ms | 无样本 |
| 推理 RTF | 0.671 | 无样本 |
| 峰值 RSS | 1,943.0 MiB | Web 加载阶段 RSS 合计约 5.5 GiB，非可比推理峰值 |
| cgroup / swap | 4096 MiB / 0 | 6144 MiB / 0（浏览器实际父 cgroup） |

Gemma 的完整金标评分和逐窗口结果保留在 `evaluation/results/round8-clip-score-exclude25-29.json`、`evaluation/results/round8-clip-audit.json`。TranslateGemma 没有完成推理，所以本次探索没有翻译准确率或延迟排名。

## 下一步建议

暂不把 Qwen 或当前 TranslateGemma Web 包纳入下一轮模型选择。若要继续测 TranslateGemma，需要满足至少一个条件：`litert-community` 发布可供 LiteRT-LM 0.17/后续版本加载的 `.litertlm` 包，或项目明确增加受支持的 MediaPipe Web/Android GPU 测试路径。仅凭当前 `.task` 文件不能与本项目的 LiteRT-LM CPU 金标结果做公平比较。

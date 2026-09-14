# 方案探索：Gemma 4 E4B 与 E2B 对比

日期：2026-09-14。该记录属于模型方案探索，不属于 `roundN` 优化轮次。

## 测试口径

两款模型均使用 `litert-community` LiteRT-LM 包、LiteRT-LM 0.17、CPU 4 线程、同一 `/home/hyh/Downloads/opencaption/clip.wav`（约 120 秒）、5 秒窗口、0 重叠、双语 baseline prompt、1024 context、128 max output tokens；每次只驻留一个模型。命令入口是 [scripts/run-gemma-eval](/home/hyh/Projects/opencaption/scripts/run-gemma-eval:1)，E4B 使用 `--model /home/hyh/Tools/litert/models/gemma-4-E4B-it.litertlm`。

E4B 使用 `MemoryMax=4096MiB`、`MemorySwapMax=0`，实际 cgroup 峰值约 3.51GiB，没有 OOM；TranslateGemma `.task` 已按上一项探索结论删除。

官方仓库确认 E4B 提供可供 LiteRT-LM 使用的 `.litertlm` 文件：[Gemma 4 E4B LiteRT Community 模型页](https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm)。

## 结果

| 指标 | Gemma 4 E2B | Gemma 4 E4B | E4B 相对 E2B |
|---|---:|---:|---:|
| 24 个窗口成功 / 错误 | 23 subtitle，1 invalid / 0 | 24 subtitle，0 / 0 | 格式完整度更好 |
| 双语窗口率 | 95.83% | 100% | +4.17 个百分点 |
| 英文 WER（排除金标第 25、29 条） | 29.87% | 22.28% | 降低 7.59 个百分点，约 25.4% 相对下降 |
| 英文实体对齐召回 | 10%（2/20） | 10%（2/20） | 无改善 |
| 推理 P50 | 3,208 ms | 12,898 ms | 4.02 倍 |
| 推理 P95 | 4,636 ms | 18,404 ms | 3.97 倍 |
| 推理 RTF | 0.671 | 2.790 | 4.16 倍，已不能实时 |
| 全部回放耗时 | 81.7 s | 338.0 s | 4.14 倍 |
| 峰值进程 RSS | 1,943.0 MiB | 3,328.5 MiB | +1,385.5 MiB |
| cgroup | 4 GiB / swap 0 | 4 GiB / swap 0 | E4B 更接近硬上限 |

WER 是交付英文的词错误率，包含切窗 / 解析影响，不是中文翻译准确率；中文语义目前没有自动评分器。

## 中文输出抽查

E4B 的双语格式和窗口连续性优于 E2B，但中文语义仍没有达到可用标准，不能因为英文 WER 改善就直接升级：

- 第一段 E4B 把 `donk` / `him` 识别为 `Dako` / `Z`，并将 `headshot` 译成“头球”；金标是“donk 一枪爆头收掉了他”。
- 第六段仍把 `Scout` 译成“侦察兵”，没有稳定使用比赛语境中的“鸟狙”；地图、选手名也有混淆。
- 后半段仍出现 `Zershian`、`Zontix`、`Beredas` 等专名错误，实体召回与 E2B 相同为 2/20。
- E4B 只是比 E2B 少了一次格式无效窗口，不能据此认定中文理解或术语质量有明显提升。

## 评测文件

- 原始 E4B 回放：[explore-gemma-e4b-clip.jsonl](/home/hyh/Projects/opencaption/evaluation/results/explore-gemma-e4b-clip.jsonl)
- E2B / E4B 金标评分：[explore-gemma-e2b-e4b-score.json](/home/hyh/Projects/opencaption/evaluation/results/explore-gemma-e2b-e4b-score.json)
- E2B / E4B 质量审计：[explore-gemma-e2b-e4b-audit.json](/home/hyh/Projects/opencaption/evaluation/results/explore-gemma-e2b-e4b-audit.json)

## 判断

E4B 的英文识别质量确实优于 E2B，但代价是约 4 倍延迟、约 1.4GiB 额外 RSS，并且专名 / 中文语义没有改善。在当前 CPU 和 4GiB 内存预算下，E4B 不适合作为默认模型；若后续目标优先是英文识别准确率、且可以接受非实时或改用更强硬件，才值得继续做独立方案评估。

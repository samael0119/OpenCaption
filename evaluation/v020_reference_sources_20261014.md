# 独立参考来源资格审查与有限准备

2026-10-14 13:41，北京时间。本包不增加模型或修改在途联合长稳的冻结源，不构建、不连接手机、不上传用户音频。

## 本机与赛事候选

本机4段赛事/访谈录音与唯一双语SRT均已用于S0，不能重新标为独立保留集。本次限定检索并核对发布方原文：

| 候选 | 发布方证据 | 本轮用途 |
|---|---|---|
| [CS-lol](https://github.com/junj1ehx/CS-lol) | 明确使用YouTube自动ASR字幕，发布方也注明字幕许可不确定 | 不作人工参考，不运行其下载脚本 |
| [OpenCS2](https://huggingface.co/datasets/blanchon/opencs2_dataset/blob/main/README.md) | 记录玩家视角游戏声音与游戏状态 | 卡片所述内容不提供本轮所需的人工解说/中译对齐，不下载大型视频库 |
| [2015赛事语料研究](https://aclanthology.org/W15-0810/) | 描述作者人工转录2014年一场47分钟CSGO解说 | 已检查出版页/论文，未取得可用对齐音频/文本下载或中文参考；不声称全网无此数据，也不把论文样句合成为语音金标 |

本次不再重复同候选搜索；检索文字及判定记录source_qualification.json。独立CS2术语、转会/历史、切图、双队与人工中译质量关口仍缺足够材料。

## 可补充的通用中英参考

[FLEURS论文](https://arxiv.org/html/2205.12446)说明语音由真人录制并另有人校验，文本沿用人工翻译的FLORES平行句，按共享句子ID对应。[Google发布库](https://huggingface.co/datasets/google/fleurs)固定revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`，FLEURS CC BY4.0；底层[FLORES文本](https://huggingface.co/datasets/facebook/flores)为CC BY-SA4.0。保留来源/署名/原始参考，仅本机使用。

取得官方英文/简体中文test.tsv（647/945行）和README/API元数据。原旧fleurs.py路径404，官方当前文件树确实不含该脚本；保留失败，按文件树取得真实TSV，没有执行远程脚本或使用第三方镜像。元数据CSV中部分长句的规范化/字符字段合并，最初固定列索引读取报错保留记录；使用CSV正确处理引号/最后两列声长与性别，选例仍要求完整7列，不据输出改参考。

在任何音频读取和模型输出前，按英文(id,filename)排序，冻结前12个不同ID、1–5s、可唯一配到中文参考的完整记录（52.74s）。不把不同ID当不同说话人；预训练污染未知。这是通用朗读，不是CS2或自然解说。

单次流式归档下载上限128MiB；实际读取134215680字节后达到上限停止，原12例**没有全部取得**。只找到6例，缺1679/1737/1747/1755/1770/1817。保留失败/prefix SHA/原12例计划，不换例或扩大下载上限。完整归档hash与gzip末端完整性未验证，不能把prefix SHA当全档校验。

已对这6例做本机格式/来源核验：1700/1750/1776/1778/1791/1792，共27.24s。原始16k单声道float32 PCM；转为产品所用16-bit PCM，不裁剪、不调增益，帧数和官方样本数逐项相同。英文/中文参考与冻结ID一致，原始文件/转换WAV/PCM及归档前缀SHA再次核对全部一致；`partial_integrity.json`明确plan_complete=false、available_cases_verified=6、inference_started=false。

512MiB/swap0/CPU25%/180s准备，失败后仅本地转换/核验（512MiB/swap0/CPU25%/120s），没有再次下载或模型调用。下载准备实际13:33:16–13:33:31，与run1同时存在；资源长稳的主机背景并非严格隔离环境，后续耗时只作描述，不作跨组因果收益。

## 下一包与限制

目前只有6例通用人工参考的可用输入，原12例实验准备仍不完整。本包只完成来源/可用性审查，不预写中文质量、术语净收益或正式第二轮通过。六例若用于后续有限控制，必须另在输出前冻结配对配置/指标并明确分母6；不能改变正式CS2≥20%净收益或地图/队伍覆盖等门槛，不用字符差异代理代替语义质量。

先完成当前3份真实时钟核心/widget长稳：读service及完整test/model/ui/summary，失败即停，不重启已完成批次。运行时冻结的129依赖/92产品源不改；只有源码和测试证据对应，才能沿用129 Dart/39 Kotlin开发候选。新来源审查不触发发布，也不暂停自动化。

文件：`evaluation/results/v020-independent/fleurs_preflight/` 下repo_metadata/publisher_readme、metadata_manifest、原control_plan、preparation_failure/log、archive_prefix、original/audio、partial_audio_manifest、partial_integrity、source_qualification。`evaluation/v020_prepare_fleurs_control.py`是有界准备脚本，发现既有prefix即拒绝隐式重跑。全部原始失败与未完成状态保留。

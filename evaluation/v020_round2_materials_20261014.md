# 第二轮：独立控制素材冻结与在途实验

2026-10-14 03:10，北京时间。四段原有本机音频全部曾用于S0，不能改称独立保留集；仅主clip有人工双语SRT，其他旧模型日志不当金标。

本次新增公开素材在模型输出出现前冻结：

- 语音：[Hugging Face 官方测试组织的 LibriSpeech 小样本](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy/tree/5be9148)，固定修订5be9148，73行。选ID排序后首12条完整时长1–5秒的语音，共43.31秒，**只有说话人1272**。参考英文来自发布数据，而非本轮模型转录；没有独立中文金标，也不能确认是否进入Gemma预训练。上游 [OpenSLR12](https://www.openslr.org/12/) 标注CC BY4.0；该镜像的英文参考与音频用于控制回归，不冒充CS2保留场次。
- 音乐：[Chopin Piano Sonata No.2 第三乐章来源页](https://commons.wikimedia.org/wiki/File:Frederic_Chopin_Piano_Sonata_No.2_in_B_flat_minor_Op35_-_III_Marche_Funebre.ogg)标注CC0。取10/30/60/120秒起的4段5秒非零钢琴录音作无语音控制。
- 首4条原声衰减18/30dB得到8个合成弱声用例，并与真实钢琴录音按名义10dB SNR得到4个合成混音。**合成衰减不是天然弱声录音，合成混音不增加独立场次数**。

共28例。源文件/转换SHA256、非零样本与RMS、英文参考、选择方法、pyarrow26.0.0均在 `evaluation/results/v020-independent/frozen_cases.json`；原始来源清单 `source_inventory.json`，转换程序 `evaluation/v020_prepare_independent.py`。准备过程512MiB/swap0/180s，不运行语音模型，不上传用户音频。

同一真实Kotlin产品提示/解析器，对28例做无提示与CS2基础提示的配对（顺序交替）；4个音乐窗口另覆盖English/Chinese/auto_zh，合计68请求。计分限于完整短语音英文WER、两种提示对协议/无语音的影响、衰减/混音回归及服务耗时。未提供CS2实体、中文金标、独立比赛或充分场景证据，**不能以这个批次宣称术语≥20%收益、地图/战队≥95%、覆盖≥80%、自然弱声或中文延迟关口通过**。

在途日志 `evaluation/results/v020-independent/controls.jsonl`；完成后 `controls_summary.json`。Java桥接 `evaluation/V020ProtocolBridge.java` 调用编译后的产品 E2eProtocol；Python驱动 `evaluation/v020_runtime_validation.py`。不重跑已开始的批次；若异常，先保留完整日志审查原因。

对照完成后，本机单模型串行执行3次60分钟真实时钟资源测试，固定每5秒提交已知≤5秒素材，每次模型6GiB/swap0/75min timeout。完整日志 `stability_1.jsonl`、`stability_2.jsonl`、`stability_3.jsonl`。这些是Linux模型资源测试，**不含真实产品采集队列、自动场景闭环或Android ANR/显示验收**。输入复用上述素材仅用于资源，不当质量泛化。整版三轮退出条件保持不变。

后台服务 `opencaption-v020-runtime.service`；外层4h15m期限，模型各自scope限6GiB且flock串行，无构建与推理重叠。入口 `scripts/run-v020-overnight-runtime` 检查已有完成标记后接续，未完成文件不自动覆盖或盲目重试。

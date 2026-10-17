# 第二轮独立控制首批结果

2026-10-14 03:17，北京时间。68次模型请求完成；模型均通过实际产品Kotlin提示/解析器，模型768context/128输出，单份CPU驻留、6GiB/swap0/900s。素材/分母限制见 [冻结清单](v020_round2_materials_20261014.md)。

| 条件 | 无提示 | CS2基础提示 | 限制 |
|---|---:|---:|---|
| 12条原声，111参考词 | 12/12双语；WER13.51% | 12/12双语；WER13.51% | 仅1名说话人、43.31s；无中文金标 |
| 8条合成衰减，86参考词 | 8/8双语；WER16.28% | 8/8双语；WER16.28% | 非天然弱声录音 |
| 4条混音，43参考词 | 4/4双语；WER18.60% | 4/4双语；WER18.60% | 合成10dB混音，不能增加独立场次数 |
| 4段非零纯音乐 | 3/4 NONE，1段虚构字幕 | 4/4 NONE | 零虚构关口未通过，不能以仅有提示组通过宣称安全 |

原声处理中位数无提示2506.96ms、基础提示2489.23ms；混音2446.01/2560.86ms。不是UI首显，也不构成稳定中文延迟门槛。基础域提示不等于实际相关术语或自动场景检索，本批次不证明术语净收益。

全部音乐任务控制20次，非NONE如下（原始输出是模型结果而非参考）：

- piano-30 / bilingual / subtitle："English: I'm not sure what you mean.\nChinese: 我不确定你是什么意思。"
- piano-30 / english / invalid：''
- piano-120 / english / invalid：''
- piano-30 / auto_zh / subtitle：'Original: 呃\nChinese: 呃'
- piano-120 / auto_zh / subtitle：'Original: 哎呀\nChinese: 哎呀'

完整日志 `evaluation/results/v020-independent/controls.jsonl`（含元数据、68请求和完成标记），统计 `controls_summary.json`。不删除失败，不放宽判定；继续查非零音乐虚构、纯数字/纯ID协议及真实术语/场景效果。3次60分钟Linux模型资源测试按既定顺序已启动，第一轮运行中，尚无完成或联合产品验收结论。

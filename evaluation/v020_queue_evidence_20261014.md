# 产品队列覆盖证据补充

2026-10-14 05:00，北京时间。后台三次长稳继续串行，未启动新模型或构建；本包产品Kotlin改动等待既有post任务执行。

已有 `E2eQueueReplayTest` 本来就回放完整约120秒轨迹，并在前30秒额外注入每请求4秒服务延迟，不是只回放30秒。本次补足的是可复核的逐区间结果及人工字幕时间单元统计，避免只有总丢弃秒数而无法定位漏句。

实际产品 `E2eAudioQueue` 回放测试新增每段TSV：策略、是否降速、已服务/替换/超龄、音频始末、最早提交、虚拟开始/完成。额外检查服务串行、开始年龄不超5秒、瞬时降速后40秒以后的窗口恢复服务，以及停顿策略丢弃量不高于固定窗。本测试是已有S0服务时间的虚拟时钟回放，合并请求成本按原成本求和；不伪装成新推理、实时负载或UI延迟。

新 `evaluation/v020_product_queue_summary.py` 直接读取实际Kotlin测试的JUnit XML，只有指定产品测试成功且4配置逐区间数据齐全才评分。用已有人工双语SRT的29个时间单元计算完全/部分具备服务机会的单元、边界跨窗和丢弃时间；不复制字幕文本，不把“音频交给模型”当成“字幕正确”。旧日志、失败测试、缺段/重段及超出录音的参考均拒绝。毫秒端点保留已有回放的亚毫秒截尾限制，PCM样本精确所有权由原分段测试独立检查。

统计器4项Python保护测试已通过：`evaluation/results/v020-independent/queue_summary_tests.log`。Kotlin新增检查和原始TSV **尚未运行**；Dart62/Kotlin29及03:10APK仍是此前验证事实。本包没有新 `product_queue_summary.json`。

后续主post任务完成Kotlin阶段后，在确认阶段成功/源快照对应后执行：

```sh
python3 evaluation/v020_product_queue_summary.py --xml build/app/test-results/testGemmaE2EDebugUnitTest/TEST-dev.opencaption.opencaption.E2eQueueReplayTest.xml
```

分析为轻量读取，不加载模型；若原Kotlin任务失败先修真实失败，不重跑长稳或控制。输出 `evaluation/results/v020-independent/product_queue_summary.json`，同时比较正常/降速的音频及完整参考单元资格。结果不能关闭独立质量或联合实际延迟关口。

本包也做了一次有界公开赛事材料检索：

- [CS-lol发布仓库](https://github.com/junj1ehx/CS-lol)说明描述字幕来自YouTube自动ASR，字幕许可也不确定；不作为人工金标。
- [GameStory官方任务页](https://multimediaeval.org/mediaeval2019/gamestory/index.html)描述赛事解说音视频及同步/回放检测参考，本次未取得可直接使用的逐词/中文人工参考和明确音频使用条件。
- [EgoCS-400K官方项目页](https://egocs-400k.github.io/)描述回放生成的游戏视频/动作/场景文字，页面数据入口显示待发布；不是赛事解说人工转录。
- [2015赛事语料论文](https://aclanthology.org/W15-0810.pdf)报告47分钟人工转录并取得解说员许可；本次公开论文入口未取得可下载语料及可沿用的材料授权。

这些是有限检索结果，不宣称所有公开赛事数据均不可用。没有下载不明权限材料、联系作者、上传用户音频或把自动字幕冒充参考。独立CS2/中文、转会/历史及切图的质量净收益仍有材料缺口，不无限重复检索同一批来源。

## 06:33实际产品Kotlin回放结果

指定ARM64离线依赖后Kotlin35项全部通过；统计器成功读取本次JUnit XML，product_queue_summary.json已生成。原始逐区间TSV保留在build/app/test-results/testGemmaE2EDebugUnitTest/TEST-dev.opencaption.opencaption.E2eQueueReplayTest.xml的system-out。

| 策略/虚拟负载 | 丢弃音频秒 | 完全具备服务资格的参考单元 | 最大开始年龄ms |
|---|---:|---:|---:|
| 固定5秒/正常 | 0 | 29/29 | 2799 |
| 停顿/正常 | 0 | 29/29 | 1403 |
| 固定5秒/前30秒每服务额外4秒 | 10 | 23/29 | 3405 |
| 停顿/同一降速 | 5 | 27/29 | 4257 |

完整区间合计120013ms，样本精确所有权和毫秒截尾限制同前。停顿方案的音频及完整参考单元资格均不低于基线，瞬时降速后40秒以后的窗口全部恢复服务、没有后台模型或无界排队；开始年龄均<=5秒。降速仍存在5秒明确缺口，不把保留最新策略写成零遗漏。

这些是实际产品队列的虚拟时钟回放和人工字幕时间边界资格；未执行新模型内容/真正系统降速/展示链路计时，不能称中文成功覆盖27/29或分段质量/延迟关口通过。独立质量及实际联合长稳仍需证据。新APK正在原流水线构建，尚未签名成功，不使用此测试推断Android运行表现。

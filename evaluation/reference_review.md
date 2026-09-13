# clip.wav 参考译文审校（非标准答案）

来源：用户提供 Downloads/clip_trans.txt；比赛信息为 Spirit vs MOUZ、Dust2。
未逐句人工听校，也没有时间戳。以下只做基于文字和上下文的修订；原文件保持不变。

| 英文片段 | 建议中文 | 备注 |
|---|---|---|
| donk will find the headshot | donk 果然一枪爆头。 | 不必译为“找到爆头机会” |
| exposed to a killer | 这一露头，就撞上了杀神。 | 与前句连读；and explodes 可能是重复听辨，待核 |
| tied at 15 frags | 都是 15 杀，并列队内第一。 | tN1R、sh1ro 的归属按用户对照，待听校 |
| with it comes open space | 这一枪也打开了推进空间。 | 指战术空间 |
| bomb spotted in that duel | 那次对枪还看到了雷包的位置。 | 保留“被看到”的信息 |
| a scout versus sh1ro | 不过，是一把鸟狙对上 sh1ro。 | 不能反转持枪者 |
| if the cat play goes well | 如果 A 小这波进攻顺利…… | 原 cat plate 疑似误识别 |
| come wide with confidence | 他就能放心地大拉出来。 | |
| misses the timing on that challenge | 他错过了这次出手的时机。 | |
| expecting to not get cleared | 他在赌对方不会搜这个位置。 | 非“被清理” |
| if there's any chance at taking the site | 想拿下包点，他就必须现在行动。 | 接前句 |
| lets this expire, allows Spirit in the lead | 他最终缩了回去，让时间耗尽，Spirit 因此取得领先。 | |
| you've got numbers on Spirit | 毕竟面对 Spirit，他们有人数优势。 | 主语仍须听校 |
| I'm tilted | 我心态崩了。 | |
| Dust2 clearly is his problem | 显然，他的问题就是 Dust2。 | |
| nice clean shots out of zont1x | zont1x 这几枪干净利落。 | |
| top mid on and off | sh1ro 不时在中路远点露头。 | |
| donk in the tunnels with Berettas | donk 拿双枪顶在 B 通里。 | 原中文漏了武器 |
| just pressing MOUZ | 持续给 MOUZ 施压。 | 战队名不能译作鼠标 |

需回听：and explodes、xertioN eventually gonna get it、site plays already got the job、near fast flank。这些英文可能不准确，暂不用于逐字评分。

# 首轮参数结果

同一 120 秒录音，2 CPU 线程、500 ms 重叠、无当场提示；均受 4 GiB cgroup 上限约束。

| 窗长 | 窗口数 | 平均推理 | 提交间隔 | 格式拒绝 |
|---|---:|---:|---:|---:|
| 3 秒 | 48 | 3.06 秒 | 2.5 秒 | 14 |
| 5 秒 | 27 | 3.80 秒 | 4.5 秒 | 6 |
| 8 秒 | 16 | 5.80 秒 | 7.5 秒 | 4 |

5 秒连续回放五遍：135 窗、510 秒处理时间、30 个格式拒绝、0 推理异常、峰值 RSS 1979.8 MiB。这里只验证离线串行推理；不包含麦克风、实时队列替换、显示延迟。重复同一素材也不能证明多场次泛化。

平均推理低于提交间隔仅表示平均吞吐有余量。5 秒窗开头语音的字幕可能要等约 5+3.8 秒，尚不满足快速比赛解说要求。后续优先比较线程数、短窗增量更新与限长输出，并模拟实时到达/队列丢段。没有时间对齐人工参考前，不报告准确率。

## 实时节奏风险：离线耗时驱动的 FIFO 模拟

使用 `python3 evaluation/summarize_replay.py <jsonl...>` 可复算。假定窗口结束即到达、单个推理任务串行、普通无限 FIFO，不包含初始化、音频预处理、UI，也不代表 Android 实际队列行为。

| 窗长 | 推理 P95 | 最大排队等待 | 窗口起点至输出平均时间 |
|---|---:|---:|---:|
| 3 秒 | 3.55 秒 | 27.64 秒 | 26.25 秒 |
| 5 秒 | 5.10 秒 | 1.55 秒 | 8.88 秒 |
| 8 秒 | 7.65 秒 | 0.15 秒 | 13.78 秒 |

因此不能直接通过缩短窗口获得低延迟。优先方向是保留 5 秒作为基线，先提升推理吞吐和输出协议稳定性；后续验证限长中文、英语先显示/中文补齐，以及有界队列。在持续过载时，“不丢任何解说”和“始终低延迟”不能同时保证，必须统计丢段率，不能用跳过旧段掩盖问题。

另一次 4 线程加当场提示试跑：平均推理 3.15 秒、P95 4.25 秒、27 段中仅 16 段通过当前格式解析、峰值 RSS 1972.1 MiB。它同时改变了线程与提示，不能据此归因；提示也未解决 donk → doko、headshot 误译。此配置暂不作为产品默认值。

本轮产物是部分参考审校、离线分段测试和 FIFO 模拟，不是完整对齐金标，也尚未验证手机实时队列/丢段或改善后的准确率。

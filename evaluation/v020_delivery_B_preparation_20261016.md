# 包B开发筛选准备：54次请求上界冻结，尚未启动Gemma

2026-10-16。仅完成当前核心新编译、8个VAD规划扫描及文件审计，没有创建Gemma Engine/模型常驻。主账仍639，本交付周期新增Gemma请求0。当前周剩33%/5h58%，用户允许使用剩余周额度，ACTIVE。

| 项目 | 结果 |
|---|---|
| 输入 | 既有canonical clip前120.000秒，4个预声明30秒开发片段；每段VAD/队列/控制器重置 |
| 固定5秒边界数 | 6 / 6 / 6 / 6，共24 |
| 当前600ms停顿边界数 | 7 / 7 / 8 / 8，共30 |
| 按片段交替AB/BA的8批请求上界 | 6、7、7、6、6、8、8、6，合计54；每批≤10 |
| 当前源/输入/类校验 | 55项全部一致；所有边界连续无重叠、无遗漏 |
| 参考资格 | 29条ASR辅助SRT代理，不是独立人工金标；正式语义结束计时未核验 |
| 人工回放边界影响 | 第7/15/21条参考跨30秒重置边界，全部保留标签，不删例；canonical尾218采样点未播放（13.625ms） |
| 产品变化与收益 | 默认产品未改；未测质量或真实模型显示时延，不宣称收益 |

## 输入与来源更正

旧clip_gold_alignment_notes.txt指出SRT起点来自AccurateScribe自动转录，辅助直播逐字稿及专名校对也不能直接证明独立人工语义标注。故本周期明确修正旧“human bilingual SRT”的资格称谓，旧文件/原评分/历史报告留档不改。本次reference_proxy.json绑定SRT与说明原SHA，所有29条和不确定边界保留。这个开发集不能成为独立确认集。

原V020JointCaptureBridge.java将浮点以Math.round(*32768)写WAV；这不是当前backend的*32767截断。新准备器从当前backend精确提取方法到V020DeliveryBInput，以capture /32768f→prepareShort→当前WAV写入路径服务两臂。不采用第10轮被否决的无损候选，不把输入校准计作停顿收益。

## 已准备的真实核心

当前AudioBuffer、E2eAudioQueue/Segmenter、SileroBoundaryVad、E2eAudioInput、E2eHintPolicy、E2eProtocol和E2ePreservedNames已从源重新编译，新Java capture/protocol和Kotlin输入写入器同一class目录。没有混用旧产品classes。两臂都逐20ms因果观察VAD，固定臂不使用概率提前提交以隔离边界策略；这不是模拟完整旧v0.1。30秒片段不循环，精确480000采样点，5秒/600ms阈值未扫描。

4段/8臂各独立许可批，额度检查等待发生在独立片段之外，避免在采集中暂停却不记录延迟。8次VAD扫描不是Gemma请求或语义样本；最多54个实际生成请求才是待执行包预算，属于总400以内，不额外加预算。队列合并/过滤/缺口可能减少实际请求，完整音频区间审计仍须保留。

准备和审计均512MiB/swap0、分别120/60秒，实际exit0，无Gemma推理，未声称峰值/OOM连续采样通过。源/输入准备结束后无运行中的VAD/Java任务。

## 下一步与启动保护

下一包只实现并冻结真实单份Gemma→新capture/protocol→非阻塞SSE/实际控制器→虚拟显示帧记录的运行入口，以及同6GiB/swap0的模型/JVM/服务器/Xvfb/Chromium资源边界。模型完成可释放worker，不等待UI呈现ACK；异步提示反馈须记录实际时序。Python-BEGIN与Java-CLOCK上下界、浏览器往返偏移区间均保留。

准备清单不覆盖尚未编写的runner，必须另冻结runner_manifest、依赖、批许可/恢复保护、模型指纹、提示配置及零模型传输预检后才能启动。不得调用旧R11<=60周used门槛helper，也不得把8批一次全部许可；每批前后新鲜额度，至多一次模型驻留/零答案重试，既有started记录防隐式重跑。先开发筛选，独立确认/正式质量/稳定中文P95仍不可验收，不跳做长稳。

文件：results/v020-delivery/B/{prepare_manifest,preparation_audit,compile,reference_proxy}.json、classes/classpath/names、V020DeliveryBCapture.java/V020DeliveryBProtocol.java/V020DeliveryBInput.kt、4片段wav和8个plan.log、prepare.log。实现evaluation/v020_delivery_B_prepare.py，方案docs/v0.2.0交付包B开发筛选冻结_20261016.md。

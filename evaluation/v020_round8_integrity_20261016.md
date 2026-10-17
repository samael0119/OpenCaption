# 第8轮输出完整性：P0与一个兼容性候选结果

2026-10-16，sol/high执行。本包完成零模型审计及一个有界候选的负面验证；没有可保留的修复，回astra审定新的机制，不把P0假称完整轮，也不增加连续失败完整轮计数。总实际模型请求仍501，新增0。自动化ACTIVE。

## 旧输出上界

五份旧日志原SHA全部核对，1156适用行（147旧开发请求+1009旧长稳结果），454个不同rawSHA；这不是1156独立音频/语义样本。当前产品协议与保留名称依赖新编译，全部1156结果逐字段等于第2轮修复后回放：940字幕、216NoSpeech、0invalid。动态历史名称未重建，两次均为空名称集合。

1150行bilingual、6行english。实际多组标签双语匹配0，精确重复配对0；所以没有观察到“lastOrNull丢掉前一组正确内容”。不能推论未来绝不发生，也不能用合成探针证明真实质量收益。

256行有未匹配前言，148不同raw，确定性分类为：246条与所选英文逐词空白归一后完全相同、8条与所选英中对完全相同、1条前言“[NONE]”、1条英文前言Aware/所选Awareness不同而真值未确认。254次重复前言省略没有可证明新增内容。剩下两条不自动算内容丢失/幻觉，不重新评分制造收益。无后缀独立异常，额外标签模式扫描0（仅有限模式，不保证所有可能标签）。

## 候选与拒绝原因

最初将真实window957前言[NONE]+完整字幕判断为协议污染，尝试在完整纯NONE规则后增加整段[NONE]混合拒绝。候选回放1156中1155保持、1字幕变invalid：字幕940→939、NoSpeech216不变。它减少交付，不能称修复幻觉或提高中文正确率。

当前已有原生测试silencePreambleDoesNotEraseACompleteSpeechPair明确保护这种前言兼容，包括window957的原形。候选JUnit20项通过19项、失败1项；因此先前“确定缺陷”的判断撤回，候选否决。未修改旧测试来通过，也未增加第二候选。14结构探针通过候选自己的状态预期，但不能抵消真实兼容性回归；其中unknown-label/Note等保持现有接受行为，不以探针自动扩大修复范围。

只撤回本次产品与测试改动后，协议源码SHA等于P0、原测试SHA等于第2轮冻结；重新编译恢复的源码并运行原JUnit19/19通过。93产品文件与scene-denial旧完整源码快照逐个哈希一致，没有新APK构建必要。候选manifest/类/失败日志保留，代表历史失败源码，不能当作当前产品清单；rejected-E2eProtocol.kt保留候选确切源码SHA。候选audit.log中的“protocol_rejection_fix_only”是当时待核验假设，最终以verdict.json否决结论为准。

## 验证范围及接续

P0/候选/恢复编译和审计均systemd显式512MiB/swap0、每阶段60秒timeout，未加载模型、没有推理重试；候选编译阶段因JUnit失败非零，失败保留，随后回放只是测变更范围而非通过门槛。恢复阶段exit0。没有Android设备、ADB、上传或发布。

没有新内容语义/术语/地图队伍/音乐护栏或真实E2E收益。普通Codex包后周剩72%、5h58%，未到40%周止损。当前第8轮仍需方向审定；保持ACTIVE继续有依据方向，不按这一个候选或包结束自动暂停。

路径：results/v020-integrity8/manifest.json、compile.json、rows.jsonl、anomalies.jsonl、summary.json、mechanism_probes.jsonl、run.log；candidate1/manifest.json、compile.json、compile_tests.log、audit.log、rows.jsonl、probes.jsonl、summary.json、rejected-E2eProtocol.kt；verdict.json、restored/compile.json、restored_tests.log、restored_product_snapshot.json。源码：V020Integrity8.kt、v020_integrity8.py、v020_integrity8_candidate.py、v020_integrity8_finalize.py；入口scripts/run-v020-integrity8-P0。

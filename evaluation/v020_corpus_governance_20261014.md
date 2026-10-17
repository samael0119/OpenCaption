# 高频词库条件治理与加载恢复

2026-10-14 08:48，北京时间。没有新增模型推理，未宣称独立音频质量通过。

## 24条语义/条件审查

以已有内置词库和原纠正案例为基础，AI辅助核对24条高频/高风险词义，参考[BLAST自有术语说明](https://blast.tv/article/key-terms-for-cs2-communication)和[完美世界官方历史词典](https://www.csgo.com.cn/tips/teaching/20161209/198250.shtml)。保留项目已有译法，用新建的原始构造正反例检查机制；它不是人工独立双语音频金标，也不是本次用户完成了逐条人工审核。

审核覆盖force-buy/save/trade/Scout/frozen，以及eco/lurker/anchor/default/execute/stack/dry peek/jiggle peek/spam/lit/tag/pick/utility/anti-flash/game sense/meta/bait/rotate/entry fragger。原始词条仍529条，只有原有5条非空wrong_targets；其他19条保持提示建议，不把avoid/alternatives无条件转成自动替换。rotate的CT“回防”、bait的正常“诱饵”、角色/首杀等保留语义差异，不做宽泛人名、数字、否定替换。

具体改善：

- `hint_sources/hint_exclude`用于本次近期自动提示和手动上下文中的词条映射：重复save file、utility bill、spam email、pick up等不会注入保枪/道具/混/抓人的错误词义。用户上下文本身作为数据保留。
- 5条既有硬纠正增加/收紧英文适用与排除；save须有武器/回合相关短语。`correction_target_exclude`检查整条中文中的普通意义，出现保存文件、交易平台、账户冻结等时保守跳过整条对应规则；支持中文词间空白。宁可保留部分误译，也不改另一分句的正常词义。
- 条件进入去重身份，不因英文/中文相同而让不同谓词静默覆盖。加载时检查类型、数量≤32、单项≤160、英文谓词有效字符；非空自动纠正需显式适用短语，空hint/scene允许源列表拒绝，不默默变成全关闭。
- Pack版本base0.1.2/live0.2.4；原选手身份/阵容快照/关系不改，新增审核注明AI辅助范围。两个文件分别约60/151KiB，均低于现有256KiB上限。

## Default两条路径的实际失败与修复

第一轮审查定点发现Default战术与Default包位的多个译法使战术提示弃权，失败日志corpus_policy_targeted_failed_default.log保留。用“play default/default setup”等战术短语和“plant default/default plant”等点位短语分开提示条件，不放宽多义弃权。

随后真实词包场景回归还发现：即使提示被区分，场景投票仍把战略default当Mirage/Ancient点位，导致后续Lobby+Vent无法确认Nuke。`default_scene_before_fix.log`实际Expected Nuke/Actual null。新`scene_sources/scene_exclude`独立约束正向证据；显式地图否定仍在约束之前处理，不阻止安全撤销。修复后34项场景/词库定点通过。

这是构造连续文本验证，不是独立赛事准确率/覆盖或译文净收益。选择词库默认辅助正常启用，不能用全部弃权通过。

## 词库损坏不再阻断通用字幕

此前CorpusIndex.load异常会让整个初始化失败。新的加载路径在缺失/格式错误时使用空词库、明确提示“词库暂不可用，已切换到通用字幕”，当前有效领域/辅助回到通用；用户请求的库与显式辅助关闭偏好仍存，修复资源后自动恢复。运行中的会话不允许重载，避免清空正在使用的证据。数据异常回退有明确说明，不能把回退当健康库默认关闭或版本验收通过。

3项本机恢复测试覆盖缺失与无效规则、持久偏好/修复、显式退出和运行中禁止重载。测试通道全部模拟，不使用手机、真实采集或外部密钥。

## 当前验证与构建范围

- 第一包定点23项通过；恢复专项3项通过；编译测试缺FlutterError导入失败保留日志并只续失败专项，不重跑模型。
- 第一包完整Dart98、Kotlin39、分析/APK/Web/V2签名全部通过，源码冻结记录corpus_review_source_snapshot.json；该候选未包含随后Default场景修复，已归档artifacts/candidate-corpus-review-before-scene-0832.apk。
- Default正向场景修复34项定点通过；完整Dart99项、静态分析/APK/Web/V2签名全部通过，exec53882退出0。corpus_scene_integrity.json核对85源文件无变更，8套Kotlin39项零失败/错误且原生源码与上次验证一致，不重复执行。corpus_scene_pipeline.jsonl与各阶段完整日志保留。
- 原07:48候选3ebb2ac8...也已归档candidate-before-corpus-review-0748.apk；旧日志和失败证据不覆盖。全部6GiB/swap0/timeout/单锁，模型无驻留，不连接/探测手机，不发布。

最新APK223531296字节，SHA256 `cd4dcbbde1bec7b1ba34740ae906cf1902c97d41bf28c13aab6ad6d5ef173302`；corpus_scene_apk_snapshot.json保存完整来源。仍为0.1.0+2的未发布开发候选。390×780深色实际浏览器预览无可见横向溢出，暂停→继续语义反馈通过；截图results/v020-ui/corpus-scene-dark-390.png。仅健康词包/模拟字幕视觉检查，坏资源恢复由专项机制测试覆盖，未冒充真实采集/坏资源屏幕验收。

独立赛事/中文、词库净收益、音乐虚构/关键漏词等整体门槛保持未通过/未测，自动化ACTIVE。fixture中expected只是机制输出，不是语义质量金标；未激活硬纠正的条目保留原译文，不把它标为正确译文。

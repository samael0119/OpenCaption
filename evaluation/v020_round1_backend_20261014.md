# v0.2.0 第一轮开发包：分段、协议、队列与词库关系

2026-10-14 00:41（北京时间）。本报告是第一轮的已完成子包，三轮总体未完成。没有连接、探测手机或执行 ADB。

## 实际代码

- Gemma 采集接入 Silero v6.2.1 ONNX CPU 单线程边界定位，600ms 停顿优先、5s 最大跨度；VAD 不可用时固定 5s 回退。每个样本只属于一个提交片段；短答与任意非空收尾保留。VAD 不负责删除音频，原有精确全零预过滤保留，不丢非零弱声。
- 严格双语 NONE 两项适配及条件输出模板接入原生产品；混合语言/sentinel、解释性文本仍拒绝，不补造缺失英文。格式适配不能保证非零音乐不虚构。
- 一个在途和一个待处理片段，相邻短片段总长≤5s 可合并；保留最早提交时间。候选待处理年龄上限 5s（提交到开始推理，**不是从片段起点计龄**），替换/过期/取消/解析失败显式缺口。继续使用原有 15s 推理 watchdog。
- 词库去重保留领域、类别、地图/战队 context、preserve、纠正来源/排除/目标条件；仅同义且同条件条目合并别名及来源。新增按已知地图筛选报点的接口，尚未接入自动场景状态；不把快照阵容宣称为当前事实。
- VAD 资产 2.3MiB，SHA256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`，带官方 MIT 许可证与来源。Android ORT 1.22.0 已下载并成功编译。

## 本机验证

1. GemmaE2E Debug Kotlin 单测 **27/27**（包括新分段/队列6项、协议14项及真实队列轨迹回放1项），无失败；日志 `evaluation/results/v020-kotlin-queue.log`，XML `build/app/test-results/testGemmaE2EDebugUnitTest/`。取消缺口小修尚需在下一次构建回归。
2. 词库 **12/12**：含同译名多图不丢关系、别名不跨图串用、不同纠正条件不被高优先级条目覆盖、Scout/frozen 正反例。日志 `evaluation/results/v020-corpus-first.log`。
3. **真实产品 Kotlin SileroBoundaryVad** 用 Linux ORT 1.22.0 跑已缓存 120.014s PCM；512 新样本概率及采集320样本调用，与原 Python 缓存最大偏差均 <1e-6（输出打印为0）。26窗，其中5个停顿边界；1920218采样点连续、无重复/遗漏，尾片段保留。20ms适配调用6001次，处理488.274ms，RTF0.004068，初始化232.594ms，峰值RSS107372KiB，swap0。**只是独立 VAD/Linux JVM，不含 Gemma 并发、Android JNI或展示性能**。
   - 内存 cgroup：High448MiB / Max512MiB / Swap0，timeout120s，Java堆128MiB；先完成编译再加载模型。
   - 源码 `evaluation/V020VadProbe.java`，入口 `scripts/run-v020-vad-test`，日志 `evaluation/results/v020-vad-jvm.log`；依赖 `evaluation/results/onnxruntime-1.22.0.jar`，已有缓存 PCM/VAD 概率。
4. **实际 E2eAudioQueue** 回放已测 CPU 服务时间，虚拟时钟，不运行模型。正常固定25窗、停顿26窗均0丢弃；前30s每请求额外注入4s后，固定丢10s、停顿丢5s，之后恢复；每个提交区间均进入已处理或明确缺口，无未记账音频。5s候选年龄相较旧2.5s实验不直接形成质量比较。该轨迹没有触发合并；另有单测验证合并样本所有权。若未来触发合并，回放按原窗服务时间相加作保守估算，不冒充合并服务实测。
   - 可复现服务数据（无音频/字幕内容）`android/app/src/test/resources/s0_service_trace.tsv`。

## 未通过 / 尚未覆盖

降速仍丢5s，**不能称覆盖验收通过**，下一包需要提交频率/负载控制实测与明确策略。静音音乐虚构、独立弱声/短答准确性、术语≥20%净收益、自动场景充分证据覆盖与历史转会、字幕UI、APK预览、3×60min长稳尚未完成。26窗口源自开发素材，不是独立泛化集。尚无Android实际运行结论。

构建前修复本机生成文件 `android/local.properties` 和 `.flutter-plugins-dependencies` 中旧小写路径；不改用户业务配置，不执行pub网络升级。开发模型 usage/token 实际计量不可获得，标未知；账户额度百分比不当作token消耗。

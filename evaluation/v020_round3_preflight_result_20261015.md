# 第3轮配置可比性预检结果

配置表达及当前依赖层预检通过，可准备候选1；尚未创建模型Engine，运行兼容性和质量收益仍未测试。候选尝试0，新增模型请求0，不能将本包计作第3完整轮结束。

| 核对项 | 结果 |
| --- | --- |
| 本机官方Python SDK | litert-lm 0.17.0；27个相关SDK源码/二进制/元数据文件SHA保存 |
| 自动基线 | enable_speculative_decoding=None；公开SDK定义为使用模型默认值，实际生效状态未知 |
| 候选调用 | 显式False通过正式C API设置关闭，配置层可独立于max_num_tokens表达 |
| 不变配置 | E2B同一模型SHA、context768、输出128、模型CPU4/音频CPU4、top_k1/temperature0、双语任务、同提示/原PCM |
| 当前依赖 | 100项目文件、57个协议类/stdlib条目与41原始输入核验；旧manifest未改 |
| 新本机桥接 | 新编译Java桥接绑定已验证且源匹配的after-fixed类；双语提示与上轮完全一致 |
| 协议探针 | 纯重复NONE→NoSpeech、NONE前缀后完整字幕→Subtitle、混合字段→Invalid，3/3符合预期 |
| 安全保护 | 5测试通过；防止关闭MTP时同时改context/采样，区分None与False，保留暂停/完整轮保护 |
| 资源 | 同锁、512MiB上限/swap0/60秒，exit0；memory.high触发507次，max/OOM/OOMKill0 |

当前Kotlin产品E2B显式启用推测解码，并把关闭分支关联到默认context；后续若试关闭，不得照搬这个关联而同时取消768。Python SDK的两个设置分别在独立条件下调用正式setter，因此可以在调用配置层保持768。该结论来自已安装SDK源码，不能替代真实Engine初始化、实际开关状态或ASR对照。

只读取公开Engine/AbstractEngine配置和正式调用路径，不猜内部API、不读取用户音频上传。初次对dataclass自动生成__init__做inspect.getsource失败，已改读公开类定义；此探索失败没有Engine或音频请求，记录在report.json。

下一包按既有第3轮方案冻结候选1的41配对/最多82请求、分层AB/BA与最多3次串行加载。新入口使用第3轮/完整轮次保护、当前桥接及本包依赖SHA；不能调用旧G1或round2 helper误触停机，不改变词表/输入增益/上下文/模板。首先实际初始化自动基线和显式关闭引擎时再验证运行配置；初始化故障须单列为工程问题，不虚构质量失败或额外试答案。

证据：results/v020-round3/preflight/{report.json,preflight.log,safety_tests.log,classpath.txt,bridge,sdk_engine_constructor.py.txt,sdk_abstract_engine.py.txt}。未修改产品源码、未构建新APK、未启动推理。自动化继续ACTIVE，完整无整体收益轮数仍2，重置尝试/使用0。

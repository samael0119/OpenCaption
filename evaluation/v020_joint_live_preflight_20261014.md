# 本机真实时钟联合验证预检

2026-10-14 12:53，北京时间。新链路不是旧模型资源3×60min的重复运行。当前90s烟测在途，不能预写通过。

## 已冻结的链路

38段既有音频（旧CS2开发切片10段＋先前公开控制28段）按固定顺序串接，每段后加入1s精确零，形成197.436s循环。人工重组的边界和重复输入仅验证资源/事件，不构成独立语义切分、中文质量、CS2净收益或音乐准确性分母。

JVM以真实20ms时钟推进连续PCM，调用现有产品SileroBoundaryVad、AudioBuffer、E2eSegmenter、E2eAudioQueue；串行pump等待真实模型与Dart/widget确认时采集继续。产品E2eAudioInput补齐、E2eHintPolicy周期提示、E2eProtocol含已有打包保留名称路径实际调用。精确全零检查在本机适配层采用相同条件，未运行完整CaptionEngine/Android AudioRecord、Handler或watchdog，不称Android性能。

唯一Python E2B常驻，768 context/128 output/4threads，实际核心模板和当时Dart提示，不从参考标签生成模型提示。Dart实际SessionController更新场景、术语/提示与ledger；OpenCaptionApp在390×780测试表面逐事件pump并检查异常/控制存在。这里是widget测试表面，不能冒称实际屏幕首显或移动端持续性能。

原始模型输出、实际提示、验证窗、源/模型样本数、真实队列等待、每段offer/合并/缺口/NoSpeech/invalid与widget交付均落盘。音频所有权审计分别检查原始分段和最终服务/过滤/缺口的完整分区，防止用隐去丢段宣称通过。

## 执行与资源

- 冻结joint_live_manifest.json：125源/类/音频依赖指纹、模型SHA、playlist及动作/配置；模型校验流式读取避免额外大块驻留。Java适配器512MiB/swap0/120s编译已exit0；Dart专项analyze无问题；两项区间审计测试通过，原始日志保存。
- 烟测90s真实时钟；前30s的服务固定增加4000ms。10s地图、20s双队、30s恢复自动、45s取消词库、60s重新选库；只改变公开控制器状态，不伪装模型推断。
- 运行脚本run-v020-joint-live用同一model.lock，整个Flutter/JVM/模型scope MemoryHigh5376MiB、MemoryMax6144MiB、swap0、timeout4500s。Dart编译完成后才启动Python模型，运行中不构建；每秒记录整个scope内存/swap/OOM事件。
- smoke exec80292正在运行，joint_live_smoke_{model,ui}.jsonl和test/stderr完整保留。不得覆盖失败或隐式重跑。烟测完整且审计通过后才启动run1/run2/run3，各3600s；缺口/内容失败照实保留，稳定性不替代质量关口。

## 验收边界

本包首先检验多进程适配、实时采集与忙时队列、提示实际来源、场景纠错/切库、controller/组件和整组资源；即使3份全部完成也只能说明已覆盖的本机核心与widget链路。OS原生采集、Android悬浮、真实屏幕呈现与独立自然长语义材料仍未测。音乐虚构、原no/six、独立赛事/中文及自动场景质量不能据长稳次数消除。

## 12:59 烟测真实失败与适配修复

首烟测模型完成21次、90s采集，但Dart只收到38/90活动事件，CAPEND及最终完成未交付，test日志失败。原因是Python的redirect_stdout为进程全局，在推理期间把另一线程的采集JSON发往stderr；不是产品VAD/队列停止。测试异常退出后日志订阅仍向关闭的sink写入，产生二次StreamSink错误并挂起；专属scope已停止、原始model/ui/stderr/test及初始manifest全部保留。不得把模型complete或scope停止返回0当测试通过。汇总器已明确检查成功test日志、所有事件逐项传输，以及音频区间完整性。

修复将协议输出绑定原stdout，退出时先断开提示入口、取消stderr订阅再关sink；另增加实际字幕文本在widget树中的呈现检查。smoke_fixed为同90s/动作/延迟的单次修复确认，独立文件，不覆盖首轮。初始审核已明确拒绝；6项所有权/丢事件/不完整/组件异常/OOM审计测试通过。32秒快照模型与Dart32/32活动一致，10/20/30秒动作按时执行；仍在途，不提前通过。

## 13:13 离线复现与最终确认

第二次smoke_fixed传输32/32活动一致，但第4条字幕断言失败后清理挂起，专属scope已停止、4模型结果/3组件结果及不完整UI保留。离线缓存复现排除了产品丢字幕：测试只pump两帧，滚动动画还在进行；等待5秒以内fake时钟settle后，4/4实际字幕源/译可见，scroll分别与0/32/157/318末端一致。最初离线matcher错误、错误方向/目标导致的No element及最后通过日志均保留。未改产品UI，未把fake动画时间当屏幕延迟。

退出清理将外部stream订阅/完成future建在真实异步zone，stderr按块同步落盘，清理有10秒上限，先关闭提示引用，错误先写harness_failure。第三个独立smoke_verified仅用于最终适配确认，90s/原动作/原延迟，240s全程timeout；前两次不覆盖。源码包括129依赖文件（与产品Dart129测试数是不同概念）。最新专项分析有1处缓存测试if大括号info待模型结束后做样式修复；6审计测试通过，不能据此预写最终烟测或静态分析通过。

run-v020-joint-series已准备但尚未启动，只在smoke_verified完整test与model/ui区间/事件/资源审计实际通过后运行3份3600秒，并逐包追加检查点；不自动重启失败批次。

## 13:16 最终烟测实际完成，三份长稳启动

smoke_verified exec84537已正常退出0，101秒含模型装载/关闭和widget工作；test All tests passed。实际采集90016ms/4500个20ms帧，最大时钟迟到273.96ms，模型与Dart活动90/90逐项一致；22次实际请求/组件往返（19字幕、3NoSpeech、0invalid），28次分段、1次合并，固定降速造成5次明确队列缺口共18120ms。分段与最终服务/缺口音频分区全部覆盖，无重复或年龄超限、widget异常、swap或观察OOMKill。整个scope峰值3960537088字节（约3.69GiB）。完整summary与audit日志保留。该结果不证明字幕内容正确，也不表示正常负载无丢段。

源/类/输入/model指纹和实际输出/提示已保存，初始及fixed不完整manifest、verified烟测manifest均单独留档。最后缓存测试大括号仅样式修复，定点analyze无问题，未重复已完成模型烟测；92个产品源与129/39候选仍一致。joint_live_pre_series_integrity.json记录沿用边界。

已启动opencaption-v020-joint-series.service：编排512MiB/swap0/4h，依次调用run1/run2/run3（每份真实3600s、同锁6GiB/swap0/4500s）；run1正常，run2前60s固定+4000ms并有纠正/切库动作，run3正常服务含动作。任何测试/区间/事件/资源审计失败立即停止、不隐式重跑；各份结束追加执行检查点。当前只是启动，不提前写3份通过。后续先读服务、joint_live_series.jsonl与各model/ui/test/summary，模型运行时不构建，不修改冻结源。

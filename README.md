# OpenCaption

本地优先的 Android 英语→简中实时字幕应用。Flutter 界面，Kotlin 收音与任务调度，Gemma E2E（LiteRT-LM）或级联引擎处理语音。无需独立后端；可选用户自配文本翻译服务，默认不上传音频、不保存字幕。

当前为开发评测版，尚未通过小米 15 的离线质量、延迟和长时间运行门槛，不能作为已验收产品。

## 开发

当前工具链：Flutter 3.47.2 / Dart 3.13.2、JDK 17、Android SDK 36、NDK 28.2.13676358、CMake 3.22.1。Android 最低 API 28，目前只构建 arm64-v8a。

`scripts/flutterw` 使用项目下 `.tools/flutter`、`.tools/android-sdk`，并隔离 Pub / Gradle 缓存。若使用自行安装的 Flutter，可将下列命令中的 `scripts/flutterw` 换成 `flutter`，并自行配置 Android SDK 和 JDK。封装脚本默认使用 Flutter 中国镜像，可通过 `PUB_HOSTED_URL` 和 `FLUTTER_STORAGE_BASE_URL` 覆盖。

```bash
export OPENCAPTION_JAVA_HOME=/path/to/jdk17
python3 scripts/fetch_native.py
scripts/flutterw pub get
scripts/flutterw test --concurrency=1
scripts/flutterw analyze --no-pub lib test pigeons
scripts/build-apk cascade
scripts/build-apk gemmaE2E
scripts/build-apk qwenE2E
# 正式包：固定签名、隐藏评测指标和诊断日志
OPENCAPTION_BUILD_MODE=release OPENCAPTION_DIAGNOSTICS=false scripts/build-apk gemmaE2E
```

首次构建需要下载依赖；原生源码固定在 `native.lock.json`，模型不会随构建下载或打包。APK 输出到 `build/app/outputs/flutter-apk/`。`scripts/build-apk` 默认生成带诊断指标的 debug 测试包；设置 `OPENCAPTION_BUILD_MODE=release OPENCAPTION_DIAGNOSTICS=false` 可生成正式包。脚本会校验固定证书指纹，防止签名变化造成无法覆盖安装、丢失应用私有模型。请串行执行测试与构建；仓库按当前开发机内存配置限制 Gradle／原生最多 8 worker 和 1.5 GB Gradle 堆。

依赖就绪后可用 `scripts/check.sh` 串行跑 Dart 检查；`scripts/check.sh --android` 还会构建 APK 并执行 Kotlin 单元测试。

修改 `pigeons/engine.dart` 后重新生成桥接：

```bash
PUB_CACHE="$PWD/.pub-cache" .tools/flutter/bin/dart --suppress-analytics run pigeon --input pigeons/engine.dart
```

## 实机试用

1. 安装测试 APK，进入模型管理，直接下载所选模型。Gemma E2E 优先使用魔搭国内源；失败时保留断点并切换备用源，也可手动导入与清单大小、SHA-256 一致的文件。
2. 离线翻译可在 Qwen2.5-0.5B Q4_K_M 与 Qwen3.5-0.8B Q4_0 间切换评测；NLLB-200 distilled 600M 已列为候选，但当前 llama.cpp 尚不支持其 encoder-decoder 推理。ML Kit 语言包由 Google SDK 自行下载，应用无法替换其下载源。Whisper 默认 small.en Q5_1，base.en Q5_1 用作速度对照。
3. 返回首页，授予麦克风权限后开始。首次模型齐全后可开启飞行模式测试离线流程。应用需保持前台；离开前台会暂停，返回后手动继续。
4. 设置中的术语库默认为“通用（无术语库）”，CS2 比赛再选择 CS2。E2E 可选打开动态术语提示：仅从最近约 1 分钟内重复或高优先级的已确认英文中选最多 6 条，预算固定，不会把整库发送给模型。
5. 设置可调整悬浮字幕背景不透明度和字幕文字颜色（原文默认黄、译文默认绿，也可选白／青等）。模型无法可靠翻译时显示“译文暂不可用”，网络或推理超时显示“译文生成超时”，两者均可在回看页重试。
6. 可选外部翻译在设置中配置地址、模型和 Key。默认 HTTPS；局域网明文 HTTP 须主动开启。连接测试会发送固定测试文本；会话启用时提示发送当前句、有限历史、术语与名称。计费由服务提供方决定。

仅测试评测包会在 Android 公共 `Downloads` 目录创建 `opencaption_yyyyMMddHHmmss.log`。正式包不创建诊断文件；测试日志逐行刷新，包含模型加载和音频初始化阶段，不包含录音、字幕内容、API Key 或完整模型路径。若进程闪退，请提供时间最新的日志；严重 native 崩溃可能只能留下最后进入的阶段，完整 native 堆栈仍需 `adb logcat`。

字幕仅在当前会话回看；返回首页并确认清除后不保留。Key 使用系统安全存储，默认诊断不记录音频、字幕或密钥。当前 release 构建仍使用开发签名，禁止当作正式发布包分发。

## 文档

- [产品需求](docs/实时字幕_PRD.md)
- [开发计划](docs/开发计划.md)
- [实施记录与已知限制](docs/实施记录.md)
- [实机评测记录要求](evaluation/README.md)
- [第七轮 Gemma E2E 指标与 APK](evaluation/round7_results.md)

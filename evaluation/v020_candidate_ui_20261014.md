# 最新候选构建与界面复核

2026-10-14 06:47，北京时间。Dart88/Kotlin35及静态分析均已通过；新APK40.7秒成功构建，JDK PATH导致签名工具退出的问题已修复，从签名阶段续做而未重建APK。APK签名V2验证成功，证书SHA256仍d557c1e4045d0b4dd710803f118da1cf61193fd76ce1348d824c64f8e486c07a。

APK build/app/outputs/flutter-apk/app-gemmae2e-debug.apk，223526333字节，SHA256 fc636443889a86742d121cc7048fe418117fc4988adacbceccfa09bbfe5f9238。版本仍0.1.0+2，为v0.2开发候选，未安装/发布。post_apk_snapshot.json与源快照/各阶段日志可复核；后续修复仅评测传输/接续代码，产品源与此APK一致。

最新Flutter Web预览成功构建（40.3s，JS路径；wasm dry-run及未使用Cupertino字体提示不是此次构建失败）。延续此前impeccable设计复核，使用真实Flutter页面再次核对390×780浅/深色、长双语字幕完整换行、最新字幕强调、底部按钮和暂停→继续状态。未见溢出，语义树为字幕文本/明确按钮。默认视口已恢复，不继续反复视觉抛光。320宽/36号字幕/系统1.5字号与四任务模式由最新widget回归覆盖；Android原生悬浮的触摸/移动没有实机验证，不作为此本机轮次设备依赖。

截图 evaluation/results/v020-ui/candidate-dark-390.jpg / candidate-light-390.jpg；此前320大字/1280等截图保留。IAB标签3保留为交付预览，http://127.0.0.1:8074/?theme=dark。服务opencaption-v020-ui-preview仅回环/128MiB/swap0，约06:35启动，3小时自动退出（约09:35）；模拟字幕明确标注，不采集音频、不运行模型。

主验证和耳语服务均已退出，仅此静态预览服务保留。资源完成、构建和界面通过不等于独立质量通过；非零音乐、真实耳语模型质量及真实赛事金标门槛仍未通过/未测。完整情况见晨间报告，08:00仍需据届时最新状态刷新。

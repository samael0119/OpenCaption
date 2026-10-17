# 包C结果：滚轮回看修复，非低延迟验收

包A实际浏览器滚轮失败，经新增PointerScrollEvent测试复现：追加字幕后位置从5770被拉至6779.77，漂移1009.77px。唯一产品候选在lib/main.dart保留触摸dragDetails路径，并对用户UserScrollNotification非idle方向停止跟随；程序自动animateTo不触发该用户方向逻辑。没有更改模型、PCM、分段、提示、词库或既有准确性修复，0新模型请求。

当前6项UI测试、145项全部Flutter测试通过；lib/test静态分析0问题，impeccable检测[]。修复前失败日志、首次修复后测试末端extent断言失败均留档：后者为懒布局在动画中修正估算长度，保持原位置断言不变后以“继续跟随/偏移增加/回看按钮消失”验证产品行为，不追加其他UI修复。首次全套因既有诊断要求新报告路径被拒绝，指定C新报告后全通过。根分析包含历史noise1孤立Dart源快照4错误，原档未改，不能报告根分析通过。

隔离Web构建39.4秒exit0。一次headful Chromium/Xvfb复核12项：11过/0失败/1隐藏页未暴露未测；实际滚轮后新字幕保持在屏外通过，停止后不再交付、乱序绑定、长内容判定等均通过。已查看桌面暗色/窄屏浅色/回看截图，中文可读、控制按钮可达，保留原布局/配色；未追加美化。字体仍仅本机隔离预览Noto环境，不代表Android字体验收。C浏览器缓存事件0模型，不能拿C截图当B真实模型端到端。

同一93文件范围另冻source_snapshot.json，较旧scene-denial只lib/main.dart与test/caption_ui_test.dart变化。39个Web产物另冻web_manifest.json；旧manifest不改。未重建Android APK，现有SHA3499da90ae8514182755863a8f0710fd44140b2a0b1ae1bbb04e586b27ad5dbc仍为修复前版本，不能冒充当前源构建。未做包D签名/联合长稳，因为主要收益未达，本包只保留UI工程候选。

进程：C浏览器exit0，回环预览服务完成后主动SIGTERM/exit143；精确进程检查已无本任务模型/浏览器/服务。资源上限：测试3–4GiB、Web构建4GiB、预览服务512MiB与浏览器2GiB各swap0且明确timeout。资源未连续采峰，不额外声称这些C阶段内存峰值已验收。

原始证据：results/v020-delivery/C/{before_test,after_ui_test,after_ui_test_refined,full_flutter_test,full_flutter_test_with_report,analyze,analyze_current_lib_test,web_build,browser,server}.log、browser_checks.json、browser_rows.json、visible_telemetry.jsonl、3张截图、scene_chain_regression.json、our_product_patch.diff。旧A失败与全部原评分不改。

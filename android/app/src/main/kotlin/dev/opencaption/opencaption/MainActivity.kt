package dev.opencaption.opencaption

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import android.content.pm.PackageManager
import android.view.WindowManager
import io.flutter.plugin.common.MethodChannel
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.SystemClock
import android.net.Uri
import android.provider.Settings

class MainActivity : FlutterActivity() {
    var foreground = false
        private set
    private var captions: CaptionEngine? = null
    private var playbackResult: MethodChannel.Result? = null
    var playbackSelected = false
        private set
    var captionTask = "bilingual"
        private set
    @Volatile var captionStyle = CaptionStyle.Options()
        private set
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        runCatching {
            assets.open("flutter_assets/assets/corpora/cs2_player_nicknames.json")
                .bufferedReader().use { CaptionStyle.loadFromJson(it.readText()) }
        }
        val messenger = flutterEngine.dartExecutor.binaryMessenger
        captions = CaptionEngine(this, EngineEvents(messenger))
        EngineHost.setUp(messenger, captions)
        PlaybackCaptionService.stopped = { code -> if (playbackSelected) captions?.interrupt(code) }
        val playbackChannel = MethodChannel(messenger, "dev.opencaption/playback")
        PlaybackCaptionService.onFontSizeChanged = { sp ->
            runOnUiThread {
                runCatching {
                    playbackChannel.invokeMethod("overlayFontSizeChanged", mapOf("value" to sp.toDouble()))
                }
            }
        }
        playbackChannel.setMethodCallHandler { call, result ->
            when (call.method) {
                "captionStyle" -> {
                    val style = call.argument<String>("style")
                    val nicknames = call.argument<Boolean>("nicknames")
                    if (style !in CaptionStyle.styles || nicknames == null) {
                        result.error("invalid_caption_style", "未知翻译风格", null)
                    } else {
                        captionStyle = CaptionStyle.Options(style!!, nicknames)
                        result.success(null)
                    }
                }
                "task" -> {
                    val task=call.argument<String>("task")
                    if (task !in setOf("bilingual", "english", "chinese", "auto_zh")) result.error("invalid_task", "未知字幕任务", null)
                    else { captionTask=task!!; result.success(null) }
                }
                "startupTiming" -> {
                    captions?.trace("startup_verify_ms=${call.argument<Number>("verifyMs")} task=$captionTask")
                    result.success(null)
                }
                "captionTiming" -> {
                    if (BuildConfig.DIAGNOSTICS_ENABLED) {
                        val epoch = call.argument<Number>("epoch")?.toLong()
                        val window = call.argument<Number>("window")?.toLong()
                        val stage = call.argument<String>("stage")
                        if (epoch != null && window != null && (stage == "controller" || stage == "flutter_paint")) {
                            captions?.trace("e2e_${stage}_timing epoch=$epoch window=$window " +
                                "elapsed_ms=${SystemClock.elapsedRealtime()} work_us=${call.argument<Number>("workUs")} " +
                                "source=${call.argument<Boolean>("source")} translation=${call.argument<Boolean>("translation")}")
                        }
                    }
                    result.success(null)
                }
                "start" -> {
                    if (Build.VERSION.SDK_INT < 29) { result.error("unsupported", "本设备音频采集需要 Android 10 或以上", null) }
                    else if (PlaybackCaptionService.active) { playbackSelected=true; result.success(null) }
                    else if (playbackResult != null) result.error("pending", "请先完成系统授权", null)
                    else if (!Settings.canDrawOverlays(this)) {
                        startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
                        result.error("overlay_permission", "请允许悬浮窗，返回后重新开始字幕", null)
                    } else {
                        playbackResult=result
                        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 703)
                        } else requestProjection()
                    }
                }
                "microphone" -> { playbackSelected=false; stopPlayback(); result.success(null) }
                "subtitle" -> {
                    val lines = call.argument<List<*>>("lines")
                    if (lines != null) {
                        val epoch = if (BuildConfig.DIAGNOSTICS_ENABLED) call.argument<Number>("epoch")?.toLong() else null
                        val window = if (epoch != null) call.argument<Number>("window")?.toLong() else null
                        val onDraw: ((Long) -> Unit)? = if (epoch != null && window != null) {
                            val source = call.argument<Boolean>("source") == true
                            val translation = call.argument<Boolean>("translation") == true
                            if (source || translation) { at ->
                                captions?.trace("e2e_overlay_draw_timing epoch=$epoch window=$window " +
                                    "elapsed_ms=$at source=$source translation=$translation")
                            } else null
                        } else null
                        PlaybackCaptionService.instance?.update(lines, onDraw)
                    } else {
                        PlaybackCaptionService.instance?.update(call.argument<String>("text").orEmpty())
                    }
                    result.success(null)
                }
                "opacity" -> {
                    val value = call.argument<Number>("value")?.toFloat() ?: 0.86f
                    PlaybackCaptionService.requestedOpacity = value.coerceIn(0.2f, 1f)
                    PlaybackCaptionService.instance?.setBackgroundOpacity(value)
                    result.success(null)
                }
                "fontSize" -> {
                    val sp = (call.argument<Number>("value")?.toFloat() ?: 20f).coerceIn(14f, 36f)
                    val explicit = call.argument<Boolean>("explicit") != false
                    if (explicit) {
                        PlaybackCaptionService.saveFontSize(this, sp)
                        PlaybackCaptionService.instance?.setFontSize(sp)
                    } else {
                        PlaybackCaptionService.requestedFontSize = sp
                    }
                    result.success(null)
                }
                "getOverlayFontSize" -> {
                    result.success(PlaybackCaptionService.savedFontSize(this)?.toDouble())
                }
                "colors" -> {
                    val source = call.argument<Number>("sourceArgb")?.toInt()
                        ?: Color.rgb(255, 224, 130)
                    val translation = call.argument<Number>("translationArgb")?.toInt()
                        ?: Color.rgb(165, 214, 167)
                    // Flutter can configure colors before the foreground service
                    // has been created. Persist the request at the companion
                    // level so showOverlay() applies it to the first frame.
                    PlaybackCaptionService.requestedSourceSubtitleColor = source
                    PlaybackCaptionService.requestedTranslationSubtitleColor = translation
                    PlaybackCaptionService.instance?.setSubtitleColors(source, translation)
                    result.success(null)
                }
                "color" -> {
                    val argb = call.argument<Number>("argb")?.toInt()
                        ?: Color.rgb(255, 224, 130)
                    PlaybackCaptionService.requestedSourceSubtitleColor = argb
                    PlaybackCaptionService.requestedTranslationSubtitleColor = argb
                    PlaybackCaptionService.instance?.setSubtitleColor(argb)
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
        MethodChannel(messenger, "dev.opencaption/power").setMethodCallHandler { call, result ->
            if (call.method != "setKeepScreenOn") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            if (call.argument<Boolean>("enabled") == true) {
                window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            } else {
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            result.success(null)
        }
    }
    override fun onPause() {
        foreground = false
        captions?.lifecycle("pause")
        super.onPause()
    }
    override fun onStop() {
        captions?.lifecycle("stop")
        if (!PlaybackCaptionService.active) captions?.interrupt("app_background")
        super.onStop()
    }
    override fun onResume() {
        super.onResume()
        foreground = true
        captions?.lifecycle("resume")
    }
    override fun onTrimMemory(level: Int) {
        if (level == android.content.ComponentCallbacks2.TRIM_MEMORY_RUNNING_CRITICAL) captions?.interrupt("memory_pressure")
        super.onTrimMemory(level)
    }
    fun stopPlayback() { stopService(Intent(this, PlaybackCaptionService::class.java)) }
    private fun requestProjection() {
        if (playbackResult == null) return
        try {
            val manager = getSystemService(MediaProjectionManager::class.java)
            val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
            } else {
                manager.createScreenCaptureIntent()
            }
            startActivityForResult(intent, 702)
        } catch (error: Exception) {
            playbackResult?.error("projection_unavailable", error.message, null); playbackResult=null
        }
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 702) return
        val result=playbackResult ?: return
        if (resultCode != Activity.RESULT_OK || data == null) {
            playbackResult=null; result.error("projection_denied", "未授权本设备音频采集", null); return
        }
        PlaybackCaptionService.ready = { failure ->
            playbackResult=null
            if (failure == null) { playbackSelected=true; result.success(null) }
            else result.error("projection_failed", failure, null)
        }
        try {
            startForegroundService(Intent(this, PlaybackCaptionService::class.java).putExtra("data", data))
        } catch (error: Exception) {
            PlaybackCaptionService.ready=null; playbackResult=null
            result.error("projection_failed", error.message, null)
        }
    }
    override fun onDestroy() {
        playbackResult?.error("activity_destroyed", "页面已关闭，请重新授权", null); playbackResult=null
        PlaybackCaptionService.ready=null; PlaybackCaptionService.stopped=null; PlaybackCaptionService.onFontSizeChanged=null
        stopPlayback(); captions?.destroy(); super.onDestroy()
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 701) captions?.permissionResult(grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED)
        if (requestCode == 703) requestProjection()
    }
}

package dev.opencaption.opencaption

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import android.provider.Settings
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.*
import android.widget.*

/** Audio-only projection. No VirtualDisplay, video encoder or second model. */
class PlaybackCaptionService : Service() {
    companion object {
        @Volatile var instance: PlaybackCaptionService? = null
            private set
        var ready: ((String?) -> Unit)? = null
        var stopped: ((String) -> Unit)? = null
        @Volatile var requestedOpacity = 0.86f
        @Volatile var requestedSourceSubtitleColor = Color.rgb(255, 224, 130)
        @Volatile var requestedTranslationSubtitleColor = Color.rgb(165, 214, 167)
        val active get() = instance?.projection != null
    }
    private data class OverlayLine(val kind: String, val text: String)
    var projection: MediaProjection? = null
        private set
    private var root: LinearLayout? = null
    private var subtitle: TextView? = null
    @Volatile private var panelOpacity = 0.86f
    @Volatile private var sourceSubtitleColor = Color.rgb(255, 224, 130)
    @Volatile private var translationSubtitleColor = Color.rgb(165, 214, 167)
    @Volatile private var lastLines: List<OverlayLine> = emptyList()
    private var stoppedNormally = false
    private val handler = Handler(Looper.getMainLooper())
    private val clearSubtitle = Runnable {
        lastLines = emptyList()
        subtitle?.text = "等待新的字幕…"
    }
    override fun onBind(intent: Intent?) = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") {
            stopped?.invoke("playback_stopped"); stopSelf(); return START_NOT_STICKY
        }
        if (projection != null) return START_NOT_STICKY
        try {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel("captions", "后台字幕", NotificationManager.IMPORTANCE_LOW))
            val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val stop = PendingIntent.getService(this, 1, Intent(this, PlaybackCaptionService::class.java).setAction("stop"), PendingIntent.FLAG_IMMUTABLE)
            val notification = Notification.Builder(this, "captions")
                .setSmallIcon(android.R.drawable.ic_btn_speak_now).setContentTitle("OpenCaption · 本设备音频字幕")
                .setContentText("正在采集允许共享的播放音频；点此返回，或停止采集")
                .setContentIntent(open).setOngoing(true).addAction(android.R.drawable.ic_media_pause, "停止", stop).build()
            if (Build.VERSION.SDK_INT >= 29) startForeground(42, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
            else startForeground(42, notification)
            val data = @Suppress("DEPRECATION") (intent?.getParcelableExtra<Intent>("data"))
            checkNotNull(data) { "授权已失效，请重新开始" }
            projection = getSystemService(MediaProjectionManager::class.java).getMediaProjection(Activity.RESULT_OK, data)
            projection!!.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    if (!stoppedNormally) stopped?.invoke("playback_projection_revoked")
                    stopSelf()
                }
            }, handler)
            instance = this
            showOverlay()
            ready?.invoke(null); ready = null
        } catch (error: Exception) {
            ready?.invoke(error.message ?: "无法启动本设备音频采集"); ready = null
            stopSelf()
        }
        return START_NOT_STICKY
    }
    private fun showOverlay() {
        check(Settings.canDrawOverlays(this)) { "请允许显示悬浮窗" }
        panelOpacity = requestedOpacity
        sourceSubtitleColor = requestedSourceSubtitleColor
        translationSubtitleColor = requestedTranslationSubtitleColor
        val wm = getSystemService(WindowManager::class.java)
        val dp = resources.displayMetrics.density
        val width = minOf((340 * dp).toInt(), resources.displayMetrics.widthPixels - (24 * dp).toInt())
        val params = WindowManager.LayoutParams(width, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT).apply { gravity = Gravity.TOP or Gravity.START; x = (12*dp).toInt(); y = (100*dp).toInt() }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(12, 8, 12, 12); setBackgroundColor(panelColor())
        }
        val bar = LinearLayout(this)
        val drag = TextView(this).apply { text = "字幕 · 拖动移动"; setTextColor(-1); textSize = 12f; setPadding(8, 12, 8, 12) }
        bar.addView(drag, LinearLayout.LayoutParams(0, -2, 1f))
        var size = 18f
        fun button(label: String, action: () -> Unit) = Button(this).apply {
            text = label; textSize = 12f; minWidth = 0; minimumWidth = 0; setPadding(4, 0, 4, 0)
            setOnClickListener { action() }
            bar.addView(this, LinearLayout.LayoutParams((44*dp).toInt(), (36*dp).toInt()))
        }
        button("−") { size = (size - 2).coerceAtLeast(12f); subtitle?.textSize = size }
        button("＋") { size = (size + 2).coerceAtMost(30f); subtitle?.textSize = size }
        button("停") { stopped?.invoke("playback_stopped"); stopSelf() }
        var startX = 0; var startY = 0; var touchX = 0f; var touchY = 0f
        drag.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> { startX=params.x; startY=params.y; touchX=event.rawX; touchY=event.rawY }
                MotionEvent.ACTION_MOVE -> {
                    params.x=(startX+event.rawX-touchX).toInt().coerceIn(0, maxOf(0, resources.displayMetrics.widthPixels-width))
                    params.y=(startY+event.rawY-touchY).toInt().coerceIn(0, maxOf(0, resources.displayMetrics.heightPixels-panel.height))
                    runCatching { wm.updateViewLayout(panel, params) }
                }
            }; true
        }
        subtitle = TextView(this).apply { text="等待播放音频…"; textSize=size; setTextColor(sourceSubtitleColor); maxLines=8 }
        panel.addView(bar); panel.addView(subtitle)
        root = panel; wm.addView(panel, params)
    }
    fun setBackgroundOpacity(value: Float) {
        panelOpacity = value.coerceIn(0.2f, 1f)
        requestedOpacity = panelOpacity
        handler.post { root?.setBackgroundColor(panelColor()) }
    }
    fun setSubtitleColors(sourceArgb: Int, translationArgb: Int) {
        sourceSubtitleColor = sourceArgb
        translationSubtitleColor = translationArgb
        requestedSourceSubtitleColor = sourceArgb
        requestedTranslationSubtitleColor = translationArgb
        handler.post { subtitle?.text = render(lastLines) }
    }
    /** Compatibility for an older Flutter side that only supplied one color. */
    fun setSubtitleColor(argb: Int) = setSubtitleColors(argb, argb)
    private fun panelColor(): Int =
        ((panelOpacity * 255f).toInt().coerceIn(0, 255) shl 24) or 0x00101010
    fun update(text: String) = update(listOf(OverlayLine("plain", text)))
    fun update(lines: List<*>) {
        val parsed = lines.mapNotNull { value ->
            val map = value as? Map<*, *> ?: return@mapNotNull null
            val text = map["text"]?.toString()?.trim().orEmpty()
            if (text.isEmpty()) return@mapNotNull null
            OverlayLine(map["kind"]?.toString().orEmpty(), text)
        }
        handler.removeCallbacks(clearSubtitle)
        lastLines = parsed
        subtitle?.text = render(parsed)
        handler.postDelayed(clearSubtitle, 15000)
    }
    private fun render(lines: List<OverlayLine>): CharSequence {
        val output = SpannableStringBuilder()
        lines.forEachIndexed { index, line ->
            if (index > 0) output.append('\n')
            val start = output.length
            output.append(line.text.take(600))
            val color = when (line.kind.lowercase()) {
                "error" -> Color.rgb(239, 83, 80)
                "translation" -> translationSubtitleColor
                "source" -> sourceSubtitleColor
                else -> sourceSubtitleColor
            }
            output.setSpan(
                ForegroundColorSpan(color),
                start,
                output.length,
                Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
            )
        }
        return output
    }
    override fun onTaskRemoved(rootIntent: Intent?) {
        stopped?.invoke("playback_stopped"); stopSelf()
    }
    override fun onDestroy() {
        if (!stoppedNormally && instance === this) stopped?.invoke("playback_stopped")
        stoppedNormally = true
        if (instance === this) instance = null
        handler.removeCallbacksAndMessages(null)
        root?.let { runCatching { getSystemService(WindowManager::class.java).removeView(it) } }; root=null
        projection?.stop(); projection=null
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}

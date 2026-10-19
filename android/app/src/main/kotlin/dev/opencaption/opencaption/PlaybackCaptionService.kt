package dev.opencaption.opencaption

import android.app.*
import android.content.Intent
import android.content.res.Configuration
import android.content.res.ColorStateList
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import android.provider.Settings
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
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
    private var controls: LinearLayout? = null
    private var controlViews: List<View> = emptyList()
    private var overlayParams: WindowManager.LayoutParams? = null
    private var overlaySpec: OverlayGeometry.Spec? = null
    private var viewportWidth = 0
    private var viewportHeight = 0
    private var verticalAnchor = OverlayGeometry.BottomAnchor(0)
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
    private fun viewport(): Pair<Int, Int> {
        val wm = getSystemService(WindowManager::class.java)
        if (Build.VERSION.SDK_INT >= 30) {
            val metrics = wm.maximumWindowMetrics
            // Match WindowManager's visible-inset frame. Hidden video-player bars
            // must not continue reserving space at the bottom of the display.
            val insets = metrics.windowInsets.getInsets(
                WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            return OverlayGeometry.usableSize(metrics.bounds.width(), metrics.bounds.height(),
                insets.left, insets.top, insets.right, insets.bottom)
        }
        return resources.displayMetrics.widthPixels to resources.displayMetrics.heightPixels
    }
    private fun surface() = GradientDrawable().apply {
        cornerRadius = 12 * resources.displayMetrics.density
        setColor(panelColor())
    }
    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        handler.post { relayoutOverlay() }
    }
    private fun relayoutOverlay(onlyIfViewportChanged: Boolean = false) {
        val panel = root ?: return
        val params = overlayParams ?: return
        val (width, height) = viewport()
        if (onlyIfViewportChanged && width == viewportWidth && height == viewportHeight) return
        val spec = OverlayGeometry.measure(width, height, resources.displayMetrics.density)
        params.x = OverlayGeometry.rotatedX(params.x, viewportWidth, params.width, width, spec.width)
        viewportWidth = width; viewportHeight = height; overlaySpec = spec
        params.width = spec.width
        params.y = verticalAnchor.y(height, panel.height)
        panel.requestLayout()
        runCatching { getSystemService(WindowManager::class.java).updateViewLayout(panel, params) }
        panel.post {
            if (root !== panel) return@post
            params.y = verticalAnchor.y(viewportHeight, panel.height)
            runCatching { getSystemService(WindowManager::class.java).updateViewLayout(panel, params) }
        }
    }
    private fun showOverlay() {
        check(Settings.canDrawOverlays(this)) { "请允许显示悬浮窗" }
        panelOpacity = requestedOpacity
        sourceSubtitleColor = requestedSourceSubtitleColor
        translationSubtitleColor = requestedTranslationSubtitleColor
        val wm = getSystemService(WindowManager::class.java)
        val dp = resources.displayMetrics.density
        val (width, height) = viewport()
        viewportWidth = width; viewportHeight = height
        val spec = OverlayGeometry.measure(width, height, dp)
        overlaySpec = spec
        verticalAnchor = OverlayGeometry.BottomAnchor(spec.margin)
        val params = WindowManager.LayoutParams(spec.width, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT).apply {
            gravity = Gravity.TOP or Gravity.START
            if (Build.VERSION.SDK_INT >= 30) {
                setFitInsetsTypes(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                setFitInsetsIgnoringVisibility(false)
            }
            x = (width - spec.width) / 2
            y = verticalAnchor.y(height, spec.target + (16*dp).toInt())
        }
        overlayParams = params
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((12*dp).toInt(), (8*dp).toInt(), (12*dp).toInt(), (8*dp).toInt())
            background = surface()
        }
        val body = FrameLayout(this)
        var size = 20f
        fun affordance(view: View, description: String, action: (() -> Unit)? = null): View {
            view.contentDescription = description; view.tooltipText = description
            view.isFocusable = true; view.isClickable = true
            view.background = RippleDrawable(ColorStateList.valueOf(0x33FFFFFF), null,
                GradientDrawable().apply { cornerRadius=8*dp; setColor(Color.WHITE) })
            if (action != null) view.setOnClickListener { action() }
            return view
        }
        val drag = affordance(ImageView(this).apply {
            setImageResource(R.drawable.ic_overlay_drag_handle); scaleType = ImageView.ScaleType.CENTER
        }, "拖动移动悬浮字幕")
        val stop = affordance(ImageView(this).apply {
            setImageResource(R.drawable.ic_overlay_stop); scaleType = ImageView.ScaleType.CENTER
        }, "停止采集并关闭字幕") { stopped?.invoke("playback_stopped"); stopSelf() }
        fun sizeButton(label: String, description: String, delta: Int) = affordance(TextView(this).apply {
            text = label; textSize = 13f; gravity = Gravity.CENTER; includeFontPadding = false
            setTextColor(Color.WHITE); setTypeface(typeface, android.graphics.Typeface.BOLD)
        }, description) { size = (size + delta).coerceIn(14f, 36f); subtitle?.textSize = size }
        controlViews = listOf(drag, sizeButton("A−", "缩小字幕", -2), sizeButton("A+", "放大字幕", 2), stop)
        controls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.END; visibility = View.GONE
            controlViews.forEachIndexed { index, view ->
                addView(view, LinearLayout.LayoutParams(spec.target, spec.target).apply {
                    leftMargin = if (index > 0) spec.gap else 0
                })
            }
        }
        var expanded = false
        val settings = affordance(ImageView(this).apply {
            setImageResource(R.drawable.ic_overlay_settings); scaleType = ImageView.ScaleType.CENTER
            imageAlpha = 184
        }, "字幕设置") as ImageView
        settings.setOnClickListener {
            expanded = !expanded
            controls?.visibility = if (expanded) View.VISIBLE else View.GONE
            settings.imageAlpha = if (expanded) 255 else 184
            settings.contentDescription = if (expanded) "收起字幕设置" else "字幕设置"
            settings.tooltipText = settings.contentDescription
        }
        var startX = 0; var startY = 0; var touchX = 0f; var touchY = 0f
        drag.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> { startX=params.x; startY=params.y; touchX=event.rawX; touchY=event.rawY }
                MotionEvent.ACTION_MOVE -> {
                    params.x = OverlayGeometry.clamp((startX+event.rawX-touchX).toInt(), viewportWidth, params.width)
                    params.y = verticalAnchor.dragTo((startY+event.rawY-touchY).toInt(), viewportHeight, panel.height)
                    runCatching { wm.updateViewLayout(panel, params) }
                }
                MotionEvent.ACTION_UP -> view.performClick()
            }; true
        }
        subtitle = TextView(this).apply {
            text="等待播放音频…"; textSize=size; setTextColor(sourceSubtitleColor)
            setLineSpacing(3*dp, 1.1f); includeFontPadding=false
            gravity = Gravity.CENTER_HORIZONTAL
            textAlignment = View.TEXT_ALIGNMENT_CENTER
        }
        val content = object : ScrollView(this) {
            override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
                val maximum = overlaySpec?.captionMaxHeight ?: (viewportHeight*.45).toInt()
                super.onMeasure(widthMeasureSpec, MeasureSpec.makeMeasureSpec(maximum, MeasureSpec.AT_MOST))
            }
        }.apply {
            isFillViewport=false
            setPadding(spec.contentInset, 0, spec.contentInset, 0)
            addView(subtitle, FrameLayout.LayoutParams(-1, -2))
        }
        body.addView(content, FrameLayout.LayoutParams(-1, -2))
        body.addView(settings, FrameLayout.LayoutParams(spec.target, spec.target, Gravity.END or Gravity.CENTER_VERTICAL))
        panel.addView(body, LinearLayout.LayoutParams(-1, -2))
        panel.addView(controls, LinearLayout.LayoutParams(-1, -2).apply { topMargin=(4*dp).toInt() })
        root = panel
        panel.setOnApplyWindowInsetsListener { _, insets ->
            // Entering/leaving immersive playback can change the usable bottom
            // without a rotation or other Configuration change.
            handler.post { if (root === panel) relayoutOverlay(onlyIfViewportChanged = true) }
            insets
        }
        panel.addOnLayoutChangeListener { _, _, top, _, bottom, _, oldTop, _, oldBottom ->
            val oldHeight = oldBottom-oldTop
            val newHeight = bottom-top
            if (oldHeight > 0 && newHeight != oldHeight) {
                params.y = verticalAnchor.y(viewportHeight, newHeight)
                runCatching { wm.updateViewLayout(panel, params) }
            }
        }
        wm.addView(panel, params)
        panel.post {
            if (root !== panel) return@post
            params.y = verticalAnchor.y(viewportHeight, panel.height)
            runCatching { wm.updateViewLayout(panel, params) }
        }
    }
    fun setBackgroundOpacity(value: Float) {
        panelOpacity = value.coerceIn(0.2f, 1f)
        requestedOpacity = panelOpacity
        handler.post {
            (root?.background as? GradientDrawable)?.setColor(panelColor())
        }
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
        (subtitle?.parent as? ScrollView)?.scrollTo(0, 0)
        handler.postDelayed(clearSubtitle, 15000)
    }
    private fun render(lines: List<OverlayLine>): CharSequence {
        val output = SpannableStringBuilder()
        val bilingual = lines.any { it.kind == "translation" }
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
            if (bilingual && line.kind == "source") {
                output.setSpan(RelativeSizeSpan(.78f), start, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            } else if (line.kind == "translation") {
                output.setSpan(StyleSpan(android.graphics.Typeface.BOLD), start, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
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
        controls=null; controlViews=emptyList(); overlayParams=null; overlaySpec=null
        projection?.stop(); projection=null
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}

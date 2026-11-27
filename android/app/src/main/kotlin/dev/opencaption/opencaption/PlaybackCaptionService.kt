package dev.opencaption.opencaption

import android.app.*
import android.content.Intent
import android.content.res.Configuration
import android.content.res.ColorStateList
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.Canvas
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
        private const val PREFS_NAME = "opencaption_overlay"
        private const val KEY_FONT_SIZE = "overlay_font_size"
        private const val KEY_CHINESE_ONLY = "overlay_chinese_only"
        private const val KEY_ROLLING_HISTORY = "overlay_rolling_history"
        @Volatile var instance: PlaybackCaptionService? = null
            private set
        var ready: ((String?) -> Unit)? = null
        var stopped: ((String) -> Unit)? = null
        var onFontSizeChanged: ((Float) -> Unit)? = null
        @Volatile var requestedOpacity = 0.86f
        @Volatile var requestedFontSize: Float? = null
        @Volatile var requestedSourceSubtitleColor = Color.rgb(255, 224, 130)
        @Volatile var requestedTranslationSubtitleColor = Color.rgb(165, 214, 167)
        val active get() = instance?.projection != null

        fun savedFontSize(context: android.content.Context): Float? {
            val prefs = context.getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            return if (prefs.contains(KEY_FONT_SIZE)) {
                prefs.getFloat(KEY_FONT_SIZE, 20f).coerceIn(14f, 36f)
            } else null
        }

        fun saveFontSize(context: android.content.Context, sp: Float) {
            val clamped = sp.coerceIn(14f, 36f)
            requestedFontSize = clamped
            context.getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                .edit()
                .putFloat(KEY_FONT_SIZE, clamped)
                .apply()
        }
    }
    private data class OverlayLine(val kind: String, val text: String)
    private inner class SubtitleView : TextView(this@PlaybackCaptionService) {
        var afterDraw: ((Long) -> Unit)? = null
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val callback = afterDraw ?: return
            afterDraw = null
            val at = SystemClock.elapsedRealtime()
            handler.post { callback(at) }
        }
    }
    var projection: MediaProjection? = null
        private set
    private var root: LinearLayout? = null
    private var subtitle: SubtitleView? = null
    private var controls: LinearLayout? = null
    private var controlViews: List<View> = emptyList()
    private var overlayParams: WindowManager.LayoutParams? = null
    private var overlaySpec: OverlayGeometry.Spec? = null
    private var viewportWidth = 0
    private var viewportHeight = 0
    private var verticalAnchor = OverlayGeometry.BottomAnchor(0)
    @Volatile private var panelOpacity = 0.86f
    @Volatile private var overlayFontSize = 20f
    @Volatile private var sourceSubtitleColor = Color.rgb(255, 224, 130)
    @Volatile private var translationSubtitleColor = Color.rgb(165, 214, 167)
    @Volatile private var lastLines: List<OverlayLine> = emptyList()
    @Volatile private var previousCaptionText: String = ""
    @Volatile private var chineseOnlyOverlay = false
    @Volatile private var rollingHistoryEnabled = true
    private var lastShownAtMs = 0L
    private var currentMinHoldMs = 0L
    private var pendingLines: List<OverlayLine>? = null
    private var pendingOnDraw: ((Long) -> Unit)? = null
    private var controlsExpanded = false
    private var stoppedNormally = false
    private val handler = Handler(Looper.getMainLooper())
    private val fadeOnSilence = Runnable {
        root?.animate()?.alpha(0.32f)?.setDuration(350L)?.start()
    }
    private val collapseControls = Runnable {
        setControlsVisible(false)
    }
    private val flushPendingCaption = Runnable {
        val next = pendingLines ?: return@Runnable
        val callback = pendingOnDraw
        pendingLines = null
        pendingOnDraw = null
        applyCaptionNow(next, callback)
    }
    private var settingsButton: ImageView? = null
    private fun setControlsVisible(visible: Boolean) {
        controlsExpanded = visible
        controls?.visibility = if (visible) View.VISIBLE else View.GONE
        settingsButton?.imageAlpha = if (visible) 255 else 150
        settingsButton?.contentDescription = if (visible) "收起字幕设置" else "字幕设置"
        settingsButton?.tooltipText = settingsButton?.contentDescription
        handler.removeCallbacks(collapseControls)
        if (visible) handler.postDelayed(collapseControls, 4500L)
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
        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        overlayFontSize = (
            if (prefs.contains(KEY_FONT_SIZE)) prefs.getFloat(KEY_FONT_SIZE, 20f)
            else (requestedFontSize ?: 20f)
        ).coerceIn(14f, 36f)
        chineseOnlyOverlay = prefs.getBoolean(KEY_CHINESE_ONLY, false)
        rollingHistoryEnabled = prefs.getBoolean(KEY_ROLLING_HISTORY, true)
        fun affordance(view: View, description: String, action: (() -> Unit)? = null): View {
            view.contentDescription = description; view.tooltipText = description
            view.isFocusable = true; view.isClickable = true
            view.background = RippleDrawable(ColorStateList.valueOf(0x33FFFFFF), null,
                GradientDrawable().apply { cornerRadius=8*dp; setColor(Color.WHITE) })
            if (action != null) view.setOnClickListener { action() }
            return view
        }
        val stop = affordance(ImageView(this).apply {
            setImageResource(R.drawable.ic_overlay_stop); scaleType = ImageView.ScaleType.CENTER
        }, "停止采集并关闭字幕") { stopped?.invoke("playback_stopped"); stopSelf() }
        fun chipButton(initialLabel: String, description: String, onClick: (TextView) -> Unit): TextView {
            lateinit var tv: TextView
            tv = TextView(this).apply {
                text = initialLabel; textSize = 12f; gravity = Gravity.CENTER; includeFontPadding = false
                setTextColor(Color.WHITE); setTypeface(typeface, android.graphics.Typeface.BOLD)
            }
            affordance(tv, description) {
                onClick(tv)
                if (controlsExpanded) {
                    handler.removeCallbacks(collapseControls)
                    handler.postDelayed(collapseControls, 4500L)
                }
            }
            return tv
        }
        val langToggle = chipButton(if (chineseOnlyOverlay) "仅中" else "双语", "切换双语或仅中文") { tv ->
            chineseOnlyOverlay = !chineseOnlyOverlay
            prefs.edit().putBoolean(KEY_CHINESE_ONLY, chineseOnlyOverlay).apply()
            tv.text = if (chineseOnlyOverlay) "仅中" else "双语"
            subtitle?.text = render(lastLines)
        }
        val historyToggle = chipButton(if (rollingHistoryEnabled) "2行" else "1行", "切换双条滚动或单条") { tv ->
            rollingHistoryEnabled = !rollingHistoryEnabled
            prefs.edit().putBoolean(KEY_ROLLING_HISTORY, rollingHistoryEnabled).apply()
            tv.text = if (rollingHistoryEnabled) "2行" else "1行"
            subtitle?.text = render(lastLines)
        }
        fun sizeButton(label: String, description: String, delta: Int) = chipButton(label, description) {
            overlayFontSize = (overlayFontSize + delta).coerceIn(14f, 36f)
            subtitle?.textSize = overlayFontSize
            saveFontSize(this, overlayFontSize)
            onFontSizeChanged?.invoke(overlayFontSize)
        }
        controlViews = listOf(langToggle, historyToggle, sizeButton("A−", "缩小字幕", -2), sizeButton("A+", "放大字幕", 2), stop)
        controls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.END; visibility = View.GONE
            controlViews.forEachIndexed { index, view ->
                addView(view, LinearLayout.LayoutParams(spec.target, spec.target).apply {
                    leftMargin = if (index > 0) spec.gap else 0
                })
            }
        }
        val settings = affordance(ImageView(this).apply {
            setImageResource(R.drawable.ic_overlay_settings); scaleType = ImageView.ScaleType.CENTER
            imageAlpha = 150
        }, "字幕设置") as ImageView
        settingsButton = settings
        settings.setOnClickListener { setControlsVisible(!controlsExpanded) }
        val touchSlop = (8 * dp).toInt()
        var startX = 0; var startY = 0; var touchX = 0f; var touchY = 0f; var dragging = false
        val panelTouchListener = View.OnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x; startY = params.y
                    touchX = event.rawX; touchY = event.rawY
                    dragging = false
                    root?.animate()?.cancel()
                    root?.alpha = 1.0f
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - touchX
                    val dy = event.rawY - touchY
                    if (!dragging && (dx * dx + dy * dy) > touchSlop * touchSlop) dragging = true
                    if (dragging) {
                        params.x = OverlayGeometry.clamp((startX + dx).toInt(), viewportWidth, params.width)
                        params.y = verticalAnchor.dragTo((startY + dy).toInt(), viewportHeight, panel.height)
                        runCatching { wm.updateViewLayout(panel, params) }
                    }
                }
                MotionEvent.ACTION_UP -> {
                    if (!dragging) {
                        setControlsVisible(!controlsExpanded)
                        view.performClick()
                    }
                }
            }
            true
        }
        subtitle = SubtitleView().apply {
            text="等待播放音频…"; textSize=overlayFontSize; setTextColor(sourceSubtitleColor)
            setLineSpacing(3*dp, 1.15f); includeFontPadding=false
            gravity = Gravity.CENTER_HORIZONTAL
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            setOnTouchListener(panelTouchListener)
        }
        panel.setOnTouchListener(panelTouchListener)
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
    fun setFontSize(sp: Float) {
        val clamped = sp.coerceIn(14f, 36f)
        overlayFontSize = clamped
        saveFontSize(this, clamped)
        handler.post { subtitle?.textSize = clamped }
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
    fun update(lines: List<*>, onDraw: ((Long) -> Unit)? = null) {
        val parsed = lines.mapNotNull { value ->
            val map = value as? Map<*, *> ?: return@mapNotNull null
            val text = map["text"]?.toString()?.trim().orEmpty()
            if (text.isEmpty()) return@mapNotNull null
            OverlayLine(map["kind"]?.toString().orEmpty(), text)
        }
        if (parsed.isEmpty()) return
        val isRealCaption = parsed.any { it.kind == "translation" || it.kind == "source" }
        val hadRealCaption = lastLines.any { it.kind == "translation" || it.kind == "source" }
        val sameSourceUpgrade = isRealCaption && hadRealCaption &&
            parsed.firstOrNull { it.kind == "source" }?.text ==
            lastLines.firstOrNull { it.kind == "source" }?.text
        val now = SystemClock.elapsedRealtime()
        val elapsed = now - lastShownAtMs
        if (isRealCaption && hadRealCaption && !sameSourceUpgrade && elapsed < currentMinHoldMs) {
            // Keep only the freshest pending caption and show it as soon as the
            // current line's minimum reading window finishes (anti-flash pacing).
            pendingLines = parsed
            pendingOnDraw = onDraw
            handler.removeCallbacks(flushPendingCaption)
            handler.postDelayed(flushPendingCaption, (currentMinHoldMs - elapsed).coerceAtLeast(80L))
            return
        }
        handler.removeCallbacks(flushPendingCaption)
        pendingLines = null
        pendingOnDraw = null
        applyCaptionNow(parsed, onDraw)
    }
    private fun primaryCaptionText(lines: List<OverlayLine>): String {
        val translation = lines.firstOrNull { it.kind == "translation" }?.text.orEmpty()
        if (translation.isNotEmpty()) return translation
        return lines.firstOrNull { it.kind == "source" }?.text.orEmpty()
    }
    private fun applyCaptionNow(parsed: List<OverlayLine>, onDraw: ((Long) -> Unit)?) {
        val isRealCaption = parsed.any { it.kind == "translation" || it.kind == "source" }
        val hadRealCaption = lastLines.any { it.kind == "translation" || it.kind == "source" }
        val sameSourceUpgrade = isRealCaption && hadRealCaption &&
            parsed.firstOrNull { it.kind == "source" }?.text ==
            lastLines.firstOrNull { it.kind == "source" }?.text
        if (!isRealCaption) {
            previousCaptionText = ""
            currentMinHoldMs = 0L
        } else {
            if (hadRealCaption && !sameSourceUpgrade) {
                val prev = primaryCaptionText(lastLines)
                val curr = primaryCaptionText(parsed)
                if (prev.isNotEmpty() && prev != curr) {
                    previousCaptionText = prev
                }
            }
            val mainLen = primaryCaptionText(parsed).length
            currentMinHoldMs = (1400L + mainLen * 32L).coerceIn(1800L, 2600L)
            lastShownAtMs = SystemClock.elapsedRealtime()
        }
        handler.removeCallbacks(fadeOnSilence)
        root?.animate()?.cancel()
        root?.alpha = 1.0f
        lastLines = parsed
        subtitle?.afterDraw = onDraw.takeIf { parsed.isNotEmpty() }
        subtitle?.text = render(parsed)
        (subtitle?.parent as? ScrollView)?.scrollTo(0, 0)
        if (isRealCaption) {
            handler.postDelayed(fadeOnSilence, 12000L)
        }
    }
    private fun render(lines: List<OverlayLine>): CharSequence {
        val output = SpannableStringBuilder()
        val hasTranslation = lines.any { it.kind == "translation" }
        val displayLines = if (chineseOnlyOverlay && hasTranslation) {
            lines.filter { it.kind != "source" }
        } else {
            lines
        }
        if (rollingHistoryEnabled &&
            previousCaptionText.isNotEmpty() &&
            displayLines.any { it.kind == "translation" || it.kind == "source" }
        ) {
            val histStart = output.length
            output.append(previousCaptionText.take(120))
            output.setSpan(RelativeSizeSpan(0.76f), histStart, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            val dimmedColor = (0x99 shl 24) or (translationSubtitleColor and 0x00FFFFFF)
            output.setSpan(ForegroundColorSpan(dimmedColor), histStart, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            output.append('\n')
        }
        val bilingual = displayLines.any { it.kind == "translation" } && displayLines.any { it.kind == "source" }
        displayLines.forEachIndexed { index, line ->
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
                output.setSpan(RelativeSizeSpan(0.76f), start, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                val subtleSource = (0xCC shl 24) or (color and 0x00FFFFFF)
                output.setSpan(ForegroundColorSpan(subtleSource), start, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            } else {
                if (line.kind == "translation") {
                    output.setSpan(StyleSpan(android.graphics.Typeface.BOLD), start, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
                output.setSpan(ForegroundColorSpan(color), start, output.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
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

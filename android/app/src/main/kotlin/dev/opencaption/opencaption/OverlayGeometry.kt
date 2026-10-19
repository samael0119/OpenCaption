package dev.opencaption.opencaption

import kotlin.math.roundToInt

/** Pure layout policy shared by the native overlay and local layout checks. */
internal object OverlayGeometry {
    fun usableSize(width: Int, height: Int, left: Int, top: Int, right: Int, bottom: Int) =
        (width - left - right).coerceAtLeast(1) to (height - top - bottom).coerceAtLeast(1)

    data class Spec(
        val width: Int, val captionMaxHeight: Int,
        val target: Int, val gap: Int, val padding: Int, val margin: Int,
    ) {
        val toolbarWidth get() = target * 4 + gap * 3
        val contentInset get() = target + gap
    }
    fun measure(width: Int, height: Int, density: Float): Spec {
        require(width > 0 && height > 0 && density > 0 && density.isFinite())
        fun dp(value: Int) = (value * density).roundToInt().coerceAtLeast(1)
        val margin = dp(12)
        val available = (width - margin * 2).coerceAtLeast(1)
        val landscape = width > height
        val panelWidth = if (landscape) minOf((available * .90f).roundToInt(), dp(1000))
                         else minOf(available, dp(480))
        return Spec(panelWidth.coerceAtLeast(1),
            minOf(((height - margin * 2) * .45f).roundToInt(), dp(480)).coerceAtLeast(1),
            dp(48), dp(8), dp(4), margin)
    }
    fun clamp(value: Int, viewport: Int, panel: Int) = value.coerceIn(0, (viewport - panel).coerceAtLeast(0))
    fun bottomY(viewport: Int, panel: Int, gap: Int) = clamp(viewport - panel - gap, viewport, panel)
    fun bottomGap(viewport: Int, y: Int, panel: Int) = (viewport - y - panel).coerceAtLeast(0)
    /** User placement survives temporary growth/clamping; only a drag changes it. */
    class BottomAnchor(initialGap: Int) {
        private var gap = initialGap.coerceAtLeast(0)
        fun y(viewport: Int, panel: Int) = OverlayGeometry.bottomY(viewport, panel, gap)
        fun dragTo(desiredY: Int, viewport: Int, panel: Int): Int {
            val y = OverlayGeometry.clamp(desiredY, viewport, panel)
            gap = OverlayGeometry.bottomGap(viewport, y, panel)
            return y
        }
    }
    fun rotatedX(x: Int, oldViewport: Int, oldWidth: Int, viewport: Int, width: Int): Int {
        val oldRange = (oldViewport - oldWidth).coerceAtLeast(0)
        val fraction = if (oldRange == 0) .5f else x.toFloat() / oldRange
        return clamp((fraction.coerceIn(0f, 1f) * (viewport - width).coerceAtLeast(0)).roundToInt(), viewport, width)
    }
}

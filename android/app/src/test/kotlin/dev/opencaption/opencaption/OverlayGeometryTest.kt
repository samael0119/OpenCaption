package dev.opencaption.opencaption

import org.junit.Assert.*
import org.junit.Test

class OverlayGeometryTest {
    @Test fun landscapeUsesTheAvailableWidthInsteadOfTheOld340dpCap() {
        val s = OverlayGeometry.measure(890, 400, 1f)
        assertEquals(779, s.width)
        assertTrue(s.width - s.contentInset * 2 - 24 > 600)
        assertTrue(s.toolbarWidth < s.width - 24)
    }
    @Test fun portraitKeepsSymmetricRoomForAnIntegratedSettingsButton() {
        val s = OverlayGeometry.measure(390, 844, 1f)
        assertEquals(366, s.width)
        assertTrue(s.width - s.contentInset * 2 - 24 >= 220)
        assertTrue(s.toolbarWidth < s.width - 24)
    }
    @Test fun densityScalesDimensionsWithoutShrinkingTouchTargets() {
        val a = OverlayGeometry.measure(890, 400, 1f)
        val b = OverlayGeometry.measure(2670, 1200, 3f)
        assertTrue(kotlin.math.abs(a.width * 3 - b.width) <= 1)
        assertEquals(144, b.target)
        assertEquals(24, b.gap)
    }
    @Test fun shortLandscapeStillFitsAllControls() {
        val s = OverlayGeometry.measure(568, 240, 1f)
        assertTrue(s.target * 2 + 2 * s.margin + s.gap < 240)
        assertTrue(s.width < 568)
    }
    @Test fun rotationKeepsRelativeHorizontalPlacementAndClampsEdges() {
        assertEquals(56, OverlayGeometry.rotatedX(12, 390, 366, 890, 779))
        assertEquals(0, OverlayGeometry.clamp(-20, 400, 112))
        assertEquals(288, OverlayGeometry.clamp(900, 400, 112))
        assertEquals(0, OverlayGeometry.clamp(12, 100, 112))
    }
    @Test fun bottomAnchoringSurvivesHeightChangesAndSmallScreens() {
        assertEquals(276, OverlayGeometry.bottomY(400, 112, 12))
        assertEquals(208, OverlayGeometry.bottomY(400, 180, 12))
        assertEquals(0, OverlayGeometry.bottomY(100, 112, 12))
    }
    @Test fun hiddenSystemBarsDoNotLeaveAPhantomBottomStrip() {
        val visible = OverlayGeometry.usableSize(890, 400, 0, 24, 0, 24)
        val hidden = OverlayGeometry.usableSize(890, 400, 0, 0, 0, 0)
        assertEquals(352, visible.second)
        assertEquals(400, hidden.second)
        // Dragging below the bottom reaches exactly the current frame edge.
        for (height in listOf(visible.second, hidden.second)) {
            assertEquals(height, OverlayGeometry.clamp(1000, height, 112) + 112)
        }
    }
    @Test fun bottomDockSurvivesRotationAndSettingsExpansionWithoutReaddingMargin() {
        val gap = OverlayGeometry.bottomGap(844, 732, 112)
        assertEquals(0, gap)
        val landscapeY = OverlayGeometry.bottomY(400, 112, gap)
        assertEquals(400, landscapeY + 112)
        val expandedY = OverlayGeometry.clamp(landscapeY + 112 - 164, 400, 164)
        assertEquals(400, expandedY + 164)
        assertEquals(0, OverlayGeometry.bottomGap(400, expandedY, 164))
    }
    @Test fun changingVisibleBarsKeepsTheChosenBottomGapAndCutoutSafety() {
        val gap = OverlayGeometry.bottomGap(352, 220, 112)
        assertEquals(20, gap)
        assertEquals(268, OverlayGeometry.bottomY(400, 112, gap))
        val cutout = OverlayGeometry.usableSize(890, 400, 32, 0, 24, 0)
        assertEquals(834, cutout.first)
        assertEquals(400, cutout.second)
        assertEquals(1 to 1, OverlayGeometry.usableSize(10, 10, 20, 20, 20, 20))
    }
    @Test fun longCaptionClampedAtTopReturnsToTheManuallyChosenShortCaptionPosition() {
        val anchor = OverlayGeometry.BottomAnchor(12)
        assertEquals(20, anchor.dragTo(20, 400, 64))
        // The old incremental height adjustment returned y=56 instead of y=20.
        repeat(10) {
            assertEquals(0, anchor.y(400, 120))
            assertEquals(20, anchor.y(400, 64))
        }
    }
    @Test fun captionAndSettingsReflowsNeverOverwriteTheAnchorButNewDragsDo() {
        val anchor = OverlayGeometry.BottomAnchor(12)
        anchor.dragTo(290, 400, 64)
        repeat(10) {
            for (height in listOf(92, 144, 300, 64)) {
                anchor.y(400, height)
            }
            assertEquals(290, anchor.y(400, 64))
        }
        // Transient system bars or rotation clamp the view, not the saved choice.
        anchor.y(240, 220)
        assertEquals(290, anchor.y(400, 64))
        anchor.dragTo(1000, 400, 64)
        assertEquals(336, anchor.y(400, 64))
        assertEquals(308, anchor.y(400, 92))
        assertEquals(336, anchor.y(400, 64))
    }
}

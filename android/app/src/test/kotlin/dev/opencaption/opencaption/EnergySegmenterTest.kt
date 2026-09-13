package dev.opencaption.opencaption

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class EnergySegmenterTest {
    @Test fun continuousSpeechIsFinalizedBeforeTheAudioBufferWraps() {
        val segmenter = EnergySegmenter()
        var total = 0L
        var first: SpeechBoundary? = null
        repeat(220) {
            total += 512
            first = segmenter.update(total, maxOf(0, total - 160000), 512, 0.01).boundary ?: first
        }

        assertNotNull(first)
        val firstBoundary = requireNotNull(first)
        assertEquals("maximum", firstBoundary.reason)
        assertEquals(0L, firstBoundary.start)
        assertEquals(80384L, firstBoundary.end)

        total += 512
        val next = segmenter.update(total, 0, 512, 0.01)
        assertNull(next.boundary)

        repeat(218) {
            total += 512
            val boundary = segmenter.update(total, maxOf(0, total - 160000), 512, 0.01).boundary
            if (boundary != null) {
                assertEquals(firstBoundary.end, boundary.start)
                return
            }
        }
        throw AssertionError("second continuous segment was not finalized")
    }

    @Test fun silenceFinalizesAtTheLastVoicedSample() {
        val segmenter = EnergySegmenter(minimumSamples = 0)
        var total = 0L
        repeat(10) {
            total += 512
            assertNull(segmenter.update(total, 0, 512, 0.01).boundary)
        }
        var boundary: SpeechBoundary? = null
        repeat(19) {
            total += 512
            boundary = segmenter.update(total, 0, 512, 0.0).boundary ?: boundary
        }
        assertNotNull(boundary)
        val result = requireNotNull(boundary)
        assertEquals("silence", result.reason)
        assertEquals(0L, result.start)
        assertEquals(5120L, result.end)
    }

    @Test fun backgroundBelowThresholdDoesNotStartAnUtterance() {
        val segmenter = EnergySegmenter()
        assertNull(segmenter.update(512, 0, 512, 0.001).boundary)
    }

    @Test fun impulseTooShortForReliableAsrIsDiscarded() {
        val segmenter = EnergySegmenter()
        var total = 0L
        repeat(4) {
            total += 320
            segmenter.update(total, 0, 320, 0.02, true)
        }
        var boundary: SpeechBoundary? = null
        repeat(31) {
            total += 320
            boundary = segmenter.update(total, 0, 320, 0.0, false).boundary ?: boundary
        }
        assertNull(boundary)
    }
}

package dev.opencaption.opencaption

import org.junit.Assert.*
import org.junit.Test

class E2eAudioPolicyTest {
    @Test fun shortAnswerSubmitsAfterPauseAndRetainsEverySample() {
        val policy = E2eSegmenter()
        var boundary: E2eSegmenter.Boundary? = null
        for (tick in 1..40) boundary = policy.update(tick * 320L, if (tick <= 10) .9 else .1) ?: boundary
        assertEquals(E2eSegmenter.Boundary(0, 12800, "pause"), boundary)
        assertEquals(E2eSegmenter.Boundary(12800, 12819, "tail"), policy.flush(12819))
        assertNull(policy.flush(12819))
    }

    @Test fun uncertainOrWeakProbabilityNeverDiscardsAudioAndHardCapIsFiveSeconds() {
        for (probability in listOf(null, .1, Double.NaN)) {
            val policy = E2eSegmenter()
            var boundary: E2eSegmenter.Boundary? = null
            for (tick in 1..250) {
                val next = policy.update(tick * 320L, probability)
                if (tick < 250) assertNull(next)
                boundary = next ?: boundary
            }
            assertEquals(E2eSegmenter.Boundary(0, 80000, "maximum"), boundary)
        }
    }

    @Test fun manyMixedFramesRemainContinuousWithNoDuplicateOrMissingTail() {
        val policy = E2eSegmenter()
        val boundaries = mutableListOf<E2eSegmenter.Boundary>()
        var total = 0L
        repeat(2000) { tick ->
            total += if (tick == 1999) 117 else 320
            policy.update(total, if (tick % 100 < 35) .9 else .1)?.let(boundaries::add)
        }
        policy.flush(total)?.let(boundaries::add)
        assertEquals(0L, boundaries.first().start)
        assertEquals(total, boundaries.last().end)
        assertTrue(boundaries.all { it.end - it.start in 1..80000 })
        assertTrue(boundaries.zipWithNext().all { (a, b) -> a.end == b.start })
    }

    private fun chunk(id: Long, begin: Long, count: Int, at: Long = 0, epoch: Long = 1) =
        E2eAudioChunk(epoch, id, begin, begin + count / 16, FloatArray(count) { id.toFloat() }, at)

    @Test fun pendingShortChunksMergeWithoutTouchingActiveAudio() {
        val queue = E2eAudioQueue(); queue.reset(1)
        val first = chunk(1, 0, 16000)
        assertTrue(queue.offer(first).schedule)
        assertSame(first, queue.take(1, 0).chunk)
        assertFalse(queue.offer(chunk(2, 1000, 16000, 10)).schedule)
        val offered = queue.offer(chunk(3, 2000, 16000, 20))
        assertTrue(offered.merged); assertNull(offered.dropped)
        assertEquals(1, queue.pendingCount())
        assertTrue(queue.finish(1))
        val merged = queue.take(1, 30).chunk!!
        assertEquals(1000L, merged.startMs); assertEquals(3000L, merged.endMs)
        assertEquals(32000, merged.pcm.size)
        assertTrue(merged.pcm.take(16000).all { it == 2f })
        assertTrue(merged.pcm.drop(16000).all { it == 3f })
        assertFalse(queue.finish(1))
    }

    @Test fun overflowAndExpiryReturnTheCompleteDroppedInterval() {
        val queue = E2eAudioQueue(); queue.reset(1)
        val old = chunk(1, 0, 80000)
        queue.offer(old)
        val newest = chunk(2, 5000, 16000, 100)
        assertSame(old, queue.offer(newest).dropped)
        val expired = queue.take(1, 5101)
        assertNull(expired.chunk); assertSame(newest, expired.expired)
        assertFalse(queue.finish(1))
    }

    @Test fun oldEpochCannotTakeFinishOrClearANewSession() {
        val queue = E2eAudioQueue(); queue.reset(1)
        queue.offer(chunk(1, 0, 16000)); queue.take(1, 0)
        queue.reset(2)
        val latest = chunk(2, 0, 16000, epoch = 2)
        queue.offer(latest)
        assertFalse(queue.finish(1)); assertNull(queue.take(1, 0).chunk)
        assertNull(queue.clear(1)); assertSame(latest, queue.take(2, 0).chunk)
    }
}

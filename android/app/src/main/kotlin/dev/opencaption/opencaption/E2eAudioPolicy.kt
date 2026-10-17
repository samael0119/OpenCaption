package dev.opencaption.opencaption

/** Causal boundary locator; never classifies a PCM interval for deletion. */
class E2eSegmenter(private val silenceSamples: Long = 9600, private val maximumSamples: Long = 80000) {
    data class Boundary(val start: Long, val end: Long, val reason: String)
    private var start = 0L
    private var previous = 0L
    private var lastSpeech = 0L
    private var heard = false

    fun update(total: Long, probability: Double?): Boundary? {
        require(total >= previous && total - previous <= 320)
        previous = total
        val reliable = probability?.takeIf { it.isFinite() && it in 0.0..1.0 }
        if (reliable != null && reliable >= .5) { lastSpeech = total; heard = true }
        val reason = when {
            total - start >= maximumSamples -> "maximum"
            reliable != null && heard && total - lastSpeech >= silenceSamples -> "pause"
            else -> return null
        }
        return emit(total, reason)
    }

    fun flush(total: Long): Boundary? = if (total > start) emit(total, "tail") else null

    private fun emit(end: Long, reason: String): Boundary {
        check(end > start && end - start <= maximumSamples)
        return Boundary(start, end, reason).also { start = end; heard = false }
    }
}

data class E2eAudioChunk(val epoch: Long, val window: Long, val startMs: Long, val endMs: Long,
    val pcm: FloatArray, val submittedAt: Long)

/** One scheduled/running pump, one owned pending chunk; all drops explicit. */
class E2eAudioQueue(private val maxSamples: Int = 80000, private val maxAgeMs: Long = 5000) {
    data class Offer(val schedule: Boolean, val dropped: E2eAudioChunk?, val merged: Boolean)
    data class Take(val chunk: E2eAudioChunk?, val expired: E2eAudioChunk?)
    private var epoch = -1L
    private var pending: E2eAudioChunk? = null
    private var scheduled = false
    @Volatile var active = false
        private set

    @Synchronized fun reset(newEpoch: Long) { epoch = newEpoch; pending = null; scheduled = false; active = false }

    @Synchronized fun offer(chunk: E2eAudioChunk): Offer {
        require(chunk.pcm.isNotEmpty() && chunk.pcm.size <= maxSamples)
        if (chunk.epoch != epoch) return Offer(false, chunk, false)
        val old = pending
        val merge = old != null && old.endMs == chunk.startMs && old.pcm.size + chunk.pcm.size <= maxSamples
        pending = if (merge) {
            chunk.copy(startMs = old!!.startMs, pcm = old.pcm + chunk.pcm, submittedAt = old.submittedAt)
        } else chunk
        val schedule = !scheduled
        scheduled = true
        return Offer(schedule, if (merge) null else old, merge)
    }

    @Synchronized fun take(expectedEpoch: Long, now: Long): Take {
        if (expectedEpoch != epoch) return Take(null, null)
        val chunk = pending; pending = null
        if (chunk != null && now - chunk.submittedAt > maxAgeMs) return Take(null, chunk)
        active = chunk != null
        return Take(chunk, null)
    }

    @Synchronized fun finish(expectedEpoch: Long): Boolean {
        if (expectedEpoch != epoch) return false
        active = false
        if (pending != null) return true
        scheduled = false
        return false
    }

    @Synchronized fun clear(expectedEpoch: Long): E2eAudioChunk? {
        if (expectedEpoch != epoch) return null
        val old = pending; pending = null
        if (!active) scheduled = false
        return old
    }

    @Synchronized fun pendingCount(): Int = if (pending == null) 0 else 1
}

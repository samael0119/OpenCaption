package dev.opencaption.opencaption

data class SpeechBoundary(
    val start: Long,
    val end: Long,
    val reason: String,
)

data class SpeechUpdate(
    val speech: Boolean,
    val boundary: SpeechBoundary?,
)

/**
 * Turns frame-level energy decisions into bounded utterances.
 *
 * Broadcast commentary often has no 600 ms pause. The maximum duration keeps
 * such audio inside the rolling PCM buffer and guarantees regular final ASR
 * results. A forced split starts the next utterance at the following frame so
 * the same audio is not translated twice.
 */
class EnergySegmenter(
    private val threshold: Double = 0.0015,
    private val preRollSamples: Long = 4800,
    private val silenceSamples: Long = 9600,
    private val maximumSamples: Long = 80000,
    private val minimumSamples: Long = 12800,
) {
    private var start = -1L
    private var lastVoice = 0L
    private var skipPreRoll = false

    fun update(total: Long, oldest: Long, frameSamples: Int, rms: Double, speechOverride: Boolean? = null): SpeechUpdate {
        val speech = speechOverride ?: (rms >= threshold)
        if (speech) {
            lastVoice = total
            if (start < 0) {
                val preRoll = if (skipPreRoll) frameSamples.toLong() else preRollSamples
                start = maxOf(oldest, total - preRoll)
                skipPreRoll = false
            }
        }
        if (start < 0) return SpeechUpdate(speech, null)

        val silenceEnded = total - lastVoice >= silenceSamples
        val maximumReached = total - start >= maximumSamples
        if (!silenceEnded && !maximumReached) return SpeechUpdate(speech, null)

        val boundary = SpeechBoundary(
            start = start,
            end = if (silenceEnded) lastVoice else total,
            reason = if (silenceEnded) "silence" else "maximum",
        )
        start = -1L
        skipPreRoll = maximumReached
        return SpeechUpdate(speech, boundary.takeIf { it.end - it.start >= minimumSamples })
    }
}

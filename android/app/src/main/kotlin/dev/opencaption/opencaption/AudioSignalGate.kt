package dev.opencaption.opencaption

import kotlin.math.max

/**
 * A conservative 20 ms, mode-2-style gate for live venue audio.
 *
 * It uses the lower fifth of a rolling one-second window as the venue noise
 * floor and requires speech-like energy in four of the latest seven frames.
 * Unlike the old gate, sustained crowd/game audio can therefore raise the
 * threshold instead of being misclassified forever after one loud frame.
 */
class AudioSignalGate {
    private val decisions = ArrayDeque<Boolean>(7)
    private val recentEnergy = ArrayDeque<Double>(50)

    fun update(samples: FloatArray, rms: Double): Boolean {
        var crossings = 0
        for (i in 1 until samples.size) {
            if ((samples[i] >= 0) != (samples[i - 1] >= 0)) crossings++
        }
        val zeroCrossingRate = crossings.toDouble() / max(1, samples.size - 1)
        if (recentEnergy.size == 50) recentEnergy.removeFirst()
        recentEnergy.addLast(rms.coerceAtMost(0.08))
        val sorted = recentEnergy.sorted()
        val noiseFloor = sorted[(sorted.size * 0.20).toInt().coerceAtMost(sorted.lastIndex)]
        val threshold = max(0.006, noiseFloor * 2.4)
        val candidate = rms >= threshold && zeroCrossingRate in 0.005..0.42
        if (decisions.size == 7) decisions.removeFirst()
        decisions.addLast(candidate)
        return decisions.count { it } >= 4
    }

    fun reset() {
        decisions.clear()
        recentEnergy.clear()
    }
}

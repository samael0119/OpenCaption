package dev.opencaption.opencaption

/** Bounded PCM buffer. All positions are sample offsets at 16 kHz. */
class AudioBuffer(private val capacity: Int = 160000) {
    private val values = FloatArray(capacity)
    var total: Long = 0
        private set
    val oldest: Long get() = maxOf(0, total - capacity)
    fun append(samples: FloatArray) {
        for (sample in samples) { values[(total % capacity).toInt()] = sample; total++ }
    }
    fun slice(from: Long, until: Long = total): FloatArray {
        require(from >= oldest && until <= total && until >= from)
        return FloatArray((until - from).toInt()) { values[((from + it) % capacity).toInt()] }
    }
}

package dev.opencaption.opencaption

/** Model input only: retain capture ownership and timestamps for short audio. */
object E2eAudioInput {
    const val SHORT_INPUT_SAMPLES = 32000 // 2 seconds at 16 kHz

    fun prepareShort(samples: FloatArray): FloatArray {
        // Silence is still filtered by CaptionEngine before model inference.
        // Do not allocate extra input for empty/zero audio or longer windows.
        if (samples.isEmpty() || samples.size >= SHORT_INPUT_SAMPLES || samples.all { it == 0f }) {
            return samples
        }
        return FloatArray(SHORT_INPUT_SAMPLES).also { padded ->
            samples.copyInto(padded, destinationOffset = padded.size - samples.size)
        }
    }
}

package dev.opencaption.opencaption
import org.junit.Assert.*
import org.junit.Test

class AudioBufferTest {
    @Test fun keepsOnlyRecentSamplesWithAbsoluteOffsets() {
        val buffer = AudioBuffer(4)
        buffer.append(floatArrayOf(1f, 2f, 3f))
        buffer.append(floatArrayOf(4f, 5f, 6f))
        assertEquals(6L, buffer.total)
        assertEquals(2L, buffer.oldest)
        assertArrayEquals(floatArrayOf(3f, 4f, 5f, 6f), buffer.slice(2), 0f)
        assertArrayEquals(floatArrayOf(4f, 5f), buffer.slice(3, 5), 0f)
    }
    @Test(expected = IllegalArgumentException::class) fun rejectsOverwrittenRange() {
        val buffer = AudioBuffer(2)
        buffer.append(floatArrayOf(1f, 2f, 3f))
        buffer.slice(0)
    }
}

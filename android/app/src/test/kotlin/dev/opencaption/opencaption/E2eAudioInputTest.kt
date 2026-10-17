package dev.opencaption.opencaption

import org.junit.Assert.*
import org.junit.Test

class E2eAudioInputTest {
    @Test fun shortInputRetainsEveryOriginalSampleAtTheEnd() {
        val source = floatArrayOf(-1f, .5f, 0f, -.25f)
        val before = source.copyOf()
        val padded = E2eAudioInput.prepareShort(source)
        assertEquals(32000, padded.size)
        assertTrue(padded.take(padded.size - source.size).all { it == 0f })
        assertArrayEquals(before, padded.copyOfRange(padded.size - source.size, padded.size), 0f)
        assertArrayEquals(before, source, 0f)
    }

    @Test fun fullAndLongerInputKeepTheirIdentityAndLength() {
        for (size in listOf(32000, 80000)) {
            val source = FloatArray(size) { .1f }
            assertSame(source, E2eAudioInput.prepareShort(source))
        }
    }

    @Test fun silenceAndEmptyInputAreNotExpanded() {
        for (source in listOf(FloatArray(0), FloatArray(16000))) {
            assertSame(source, E2eAudioInput.prepareShort(source))
        }
    }

    @Test fun quietNonzeroSpeechIsPreservedWithoutNormalization() {
        val source = FloatArray(8000) { index -> if (index % 2 == 0) .000001f else -.000001f }
        val padded = E2eAudioInput.prepareShort(source)
        assertArrayEquals(source, padded.copyOfRange(24000, 32000), 0f)
        assertEquals(32000, padded.size)
    }
}

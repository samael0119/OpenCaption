package dev.opencaption.opencaption

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class OnnxAsrEngineTest {
    @Test
    fun detectsSenseVoiceAndParakeetDirectories() {
        val root = Files.createTempDirectory("onnx-asr-test").toFile()
        try {
            val svDir = File(root, "sv").apply { mkdirs() }
            File(svDir, "model.int8.onnx").writeBytes(byteArrayOf(1))
            assertTrue(OnnxAsrFactory.isOnnxAsrPath(svDir.path))

            val pkDir = File(root, "pk").apply { mkdirs() }
            File(pkDir, "encoder.int8.onnx").writeBytes(byteArrayOf(1))
            assertTrue(OnnxAsrFactory.isOnnxAsrPath(pkDir.path))

            val whisperFile = File(root, "ggml-small-q5_1.bin").apply { writeBytes(byteArrayOf(1)) }
            assertFalse(OnnxAsrFactory.isOnnxAsrPath(whisperFile.path))

            val emptyDir = File(root, "empty").apply { mkdirs() }
            assertFalse(OnnxAsrFactory.isOnnxAsrPath(emptyDir.path))
        } finally {
            root.deleteRecursively()
        }
    }
}

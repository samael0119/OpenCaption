package dev.opencaption.opencaption

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer

/** 512 newly arrived samples + 64 context, CPU/one thread. No future audio. */
class SileroBoundaryVad(model: ByteArray) : AutoCloseable {
    private val environment = OrtEnvironment.getEnvironment()
    private val session = OrtSession.SessionOptions().use { options ->
        options.setIntraOpNumThreads(1); options.setInterOpNumThreads(1)
        environment.createSession(model, options)
    }
    private val frame = FloatArray(576)
    private val state = FloatArray(256)
    private var filled = 0
    private var probability = 0.0

    fun reset() { frame.fill(0f); state.fill(0f); filled = 0; probability = 0.0 }

    fun observe(samples: FloatArray): Double {
        for (sample in samples) {
            frame[64 + filled++] = sample
            if (filled == 512) {
                OnnxTensor.createTensor(environment, FloatBuffer.wrap(frame), longArrayOf(1, 576)).use { input ->
                    OnnxTensor.createTensor(environment, FloatBuffer.wrap(state), longArrayOf(2, 1, 128)).use { memory ->
                        OnnxTensor.createTensor(environment, 16000L).use { rate ->
                            session.run(mapOf("input" to input, "state" to memory, "sr" to rate)).use { result ->
                                @Suppress("UNCHECKED_CAST")
                                val output = result[0].value as Array<FloatArray>
                                @Suppress("UNCHECKED_CAST")
                                val next = result[1].value as Array<Array<FloatArray>>
                                probability = output[0][0].toDouble()
                                next[0][0].copyInto(state, 0); next[1][0].copyInto(state, 128)
                            }
                        }
                    }
                }
                frame.copyInto(frame, 0, 512, 576)
                filled = 0
            }
        }
        return probability
    }

    override fun close() { session.close() }
}

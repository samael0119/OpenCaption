package dev.opencaption.opencaption

import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.ThinkingConfig
import java.nio.ByteBuffer
import java.nio.ByteOrder

object FlavorBackendFactory {
    fun create(activity: MainActivity): EndToEndBackend = GemmaBackend(activity)
}

private const val GEMMA_MAX_OUTPUT_TOKENS = 128
private const val GEMMA_MAX_CONTEXT_TOKENS = 768
private const val MAINLAND_SIMPLIFIED_RULE =
    "Use Mainland China Simplified Chinese (简体中文, zh-CN). " +
        "Do NOT output Traditional Chinese (繁體中文). "
private val hintUnsafeCharacters = Regex("[\\u0000-\\u001f\\u007f\\u200b-\\u200f\\u202a-\\u202e<>`{}]")
private val hintPromptInjection = Regex(
    "<\\s*/?\\s*(?:system|user|assistant|developer|think|analysis)\\s*>|" +
        "(?:ignore|disregard|forget)\\s+(?:all\\s+)?(?:the\\s+)?" +
        "(?:previous|prior|above|these)?\\s*(?:instructions?|rules?|prompts?)|" +
        "(?:system|developer|assistant|user)\\s*(?:message|prompt|instruction)\\s*[:：]|" +
        "(?:output|respond|answer)\\s+(?:only|as|in\\s+(?:json|xml|yaml))\\b|" +
        "(?:jailbreak|prompt\\s+injection)",
    RegexOption.IGNORE_CASE,
)

private fun sanitizeHints(value: String): String {
    val normalized = value
        .replace(hintUnsafeCharacters, " ")
        .replace(Regex("\\s+"), " ")
        .trim()
    if (normalized.isEmpty() || hintPromptInjection.containsMatchIn(normalized)) return ""
    return normalized.take(240).trimEnd()
}

private class GemmaBackend(private val activity: MainActivity) : EndToEndBackend {
    private var engine: Engine? = null
    private var runtime = "unloaded"
    private var hints = ""
    private var shortAudioInput = false
    override fun setHints(hints: String) { this.hints = sanitizeHints(hints) }
    @Volatile private var activeConversation: Conversation? = null

    @OptIn(ExperimentalApi::class)
    override fun load(modelPath: String, threadCount: Int) {
        close()
        val threads = threadCount.takeIf { it == 2 || it == 4 || it == 6 || it == 8 } ?: 4
        val audioThreads = threads
        val modelName = modelPath.substringAfterLast('/')
        // Only the E2B input shape was validated in the bounded short-audio
        // comparison; do not silently apply it to the separate E4B quality mode.
        shortAudioInput = modelName.contains("gemma-4-E2B", ignoreCase = true)
        val enableSpeculativeDecoding =
            modelName.contains("gemma-4-E2B", ignoreCase = true) ||
                modelName.contains("gemma-4-E4B", ignoreCase = true)
        val maxContextTokens = if (enableSpeculativeDecoding) GEMMA_MAX_CONTEXT_TOKENS else null
        // This is a process-wide experimental flag in LiteRT-LM 0.17. Set it
        // before Engine.initialize(), including the CPU fallback path, then
        // clear it so a later non-Gemma engine is not affected.
        ExperimentalFlags.enableSpeculativeDecoding = enableSpeculativeDecoding
        fun config(backend: Backend) = EngineConfig(
            modelPath = modelPath,
            backend = backend,
            audioBackend = Backend.CPU(threadCount = audioThreads),
            maxNumTokens = maxContextTokens,
            cacheDir = activity.cacheDir.path,
        )
        val gpu = Engine(config(Backend.GPU()))
        engine = try {
            gpu.initialize()
            runtime = "model_backend=gpu audio_backend=cpu audio_threads=$audioThreads fallback=false speculative_decoding=$enableSpeculativeDecoding max_context_tokens=${maxContextTokens ?: "default"} max_output_tokens=$GEMMA_MAX_OUTPUT_TOKENS thinking=false cache=disk"
            gpu
        } catch (gpuError: Exception) {
            // A failed accelerator may retain native buffers. Release it before
            // allocating a second copy of this multi-GB model on CPU. Do not
            // catch OutOfMemoryError and attempt another allocation.
            runCatching { gpu.close() }
            val cpuEngine = Engine(config(Backend.CPU(threadCount = threads)))
            try {
                cpuEngine.initialize()
                val detail = gpuError.message.orEmpty().replace(Regex("[\\r\\n]+"), " ").take(160)
                runtime = "model_backend=cpu model_threads=$threads audio_backend=cpu audio_threads=$audioThreads fallback=true speculative_decoding=$enableSpeculativeDecoding max_context_tokens=${maxContextTokens ?: "default"} max_output_tokens=$GEMMA_MAX_OUTPUT_TOKENS thinking=false cache=disk gpu_error=${gpuError.javaClass.simpleName}:$detail"
                cpuEngine
            } catch (cpuError: Exception) {
                runCatching { cpuEngine.close() }
                throw cpuError
            }
        } finally {
            ExperimentalFlags.enableSpeculativeDecoding = false
        }
    }

    override fun runtimeInfo(): String =
        "$runtime short_audio_floor_ms=${if (shortAudioInput) 2000 else 0}"

    override fun infer(samples: FloatArray): String {
        val task = activity.captionTask
        val config = ConversationConfig(
            systemInstruction = Contents.of(E2eProtocol.systemFor(task)),
            samplerConfig = SamplerConfig(topK = 1, topP = 1.0, temperature = 0.0),
            maxOutputToken = GEMMA_MAX_OUTPUT_TOKENS,
            thinkingConfig = ThinkingConfig(enableThinking = false, thinkingTokenBudget = 0),
        )
        return requireNotNull(engine).createConversation(config).use { conversation ->
            activeConversation = conversation
            try {
                conversation.sendMessage(
                    Contents.of(
                        // Gemma 4 expects audio after its text instruction.
                        Content.Text(E2eProtocol.requestFor(task, hints)),
                        Content.AudioBytes(wav(if (shortAudioInput) E2eAudioInput.prepareShort(samples) else samples)),
                    ),
                    extraContext = mapOf("enable_thinking" to false),
                    maxOutputToken = GEMMA_MAX_OUTPUT_TOKENS,
                    thinkingConfig = ThinkingConfig(enableThinking = false, thinkingTokenBudget = 0),
                ).contents.contents.filterIsInstance<Content.Text>().joinToString("") { it.text }
            } finally {
                activeConversation = null
            }
        }
    }

    override fun cancel() { activeConversation?.cancelProcess() }
    override fun close() { engine?.close(); engine = null; runtime = "unloaded"; shortAudioInput = false }

    private fun wav(samples: FloatArray): ByteArray {
        val out = ByteBuffer.allocate(44 + samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        fun ascii(value: String) = out.put(value.toByteArray(Charsets.US_ASCII))
        ascii("RIFF"); out.putInt(36 + samples.size * 2); ascii("WAVEfmt ")
        out.putInt(16); out.putShort(1); out.putShort(1); out.putInt(16000)
        out.putInt(32000); out.putShort(2); out.putShort(16); ascii("data")
        out.putInt(samples.size * 2)
        samples.forEach { out.putShort((it.coerceIn(-1f, 1f) * 32767).toInt().toShort()) }
        return out.array()
    }
}

package dev.opencaption.opencaption

interface EndToEndBackend : AutoCloseable {
    fun load(modelPath: String, threadCount: Int)
    fun runtimeInfo(): String = "unspecified"
    fun setHints(hints: String) {}
    fun setCaptionStyle(style: String) {}
    fun infer(samples: FloatArray, onSourcePreview: ((String) -> Unit)? = null): String
    fun cancel()
}

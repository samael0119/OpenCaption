package dev.opencaption.opencaption

object FlavorBackendFactory {
    fun create(activity: MainActivity): EndToEndBackend = object : EndToEndBackend {
        private val native = NativeEngine()
        override fun load(modelPath: String, threadCount: Int) = native.loadOmni(modelPath)
        override fun infer(samples: FloatArray): String = native.transcribeTranslateOmni(samples)
        override fun cancel() = native.setOmniCancelled(true)
        override fun close() = native.releaseOmni()
    }
}

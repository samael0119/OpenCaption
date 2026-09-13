package dev.opencaption.opencaption

class NativeEngine {
    companion object { init { System.loadLibrary("opencaption") } }
    external fun load(asrPath: String, vadPath: String, llmPath: String, threads: Int, logFd: Int)
    external fun transcribe(samples: FloatArray, hints: String): String
    external fun lastNoSpeechProbability(): Double
    external fun lastAverageTokenProbability(): Double
    external fun voiceProbability(samples: FloatArray): Double
    external fun resetVad()
    external fun translate(prompt: String): String
    external fun setCancelled(value: Boolean)
    external fun setTranslationCancelled(value: Boolean)
    external fun release()
    external fun loadOmni(modelPath: String)
    external fun transcribeTranslateOmni(samples: FloatArray): String
    external fun setOmniCancelled(value: Boolean)
    external fun releaseOmni()
}

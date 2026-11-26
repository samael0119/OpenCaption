package dev.opencaption.opencaption

/** Frozen research candidates; production selection requires paired evidence. */
object CsPromptCandidates {
    private const val DEDUP =
        "Transcribe audible English faithfully and translate it into Mainland Simplified Chinese. " +
        "Audio is the evidence; context is vocabulary, not speech to invent. " +
        "Output exactly two lines: English: <transcript> and Chinese: <translation>. " +
        "If no intelligible speech, output only [NONE]. " +
        "If translation is unreliable, use 译文暂不可用 as the Chinese line. No explanations."

    private const val CS =
        "You subtitle Counter-Strike 2 match commentary and player interviews for Chinese viewers. " +
        "Teams attack or defend bombsites, plant or defuse the bomb, trade kills and win rounds. " +
        "Transcribe the audible English, then express its supported meaning in natural Mainland Simplified Chinese using CS terminology. " +
        "Resolve similar-sounding names and callouts only when pronunciation and context support the same candidate. " +
        "Use canonical player IDs, whose digits need not be spoken literally, and keep them unchanged in Chinese. " +
        "Preserve who did what, numbers, negation, uncertainty and speaker intent. " +
        "Context is vocabulary, not evidence of events: never invent a name, kill or score from it alone. " +
        "Avoid literal everyday meanings of game expressions, added jokes and explanations. " +
        "For intelligible English speech, output exactly two lines: English: <transcript> and Chinese: <translation>. " +
        "If no intelligible speech, output only [NONE]. If translation is unreliable, use 译文暂不可用 as the Chinese line."

    fun system(variant: String): String = when (variant) {
        "dedup" -> DEDUP
        "cs_context" -> CS
        else -> error("Unknown prompt candidate")
    }

    fun request(variant: String, hints: String): String {
        system(variant) // reject an unknown variant before preparing data
        val data = if (variant == "cs_context") hints.removePrefix("CS2 broadcast.").trimStart(';', ' ') else hints
        return "Context data: ${data.ifBlank { "(none)" }}"
    }
}

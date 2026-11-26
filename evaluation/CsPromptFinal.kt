package dev.opencaption.opencaption

/** Rules and context in system; the sole task/output contract in user. */
object CsPromptFinal {
    const val SYSTEM =
        "Context: Counter-Strike 2 esports commentary or player interviews. Teams contest bombsites and rounds. " +
        "Interpret player IDs, callouts, weapons and score gaps in CS context. " +
        "Resolve similar-sounding words only when pronunciation and context both support them; use canonical IDs, whose digits need not be spoken literally. " +
        "Keep IDs unchanged in Chinese. Use natural Chinese esports phrasing while preserving actors, actions, numbers, negation, uncertainty and speaker attitude. " +
        "Context vocabulary does not prove who acted or what happened. Retain uncertainty instead of guessing. Add no facts, jokes or explanations."
    fun request(hints: String): String {
        val data = hints.removePrefix("CS2 broadcast.").trimStart(';', ' ')
        return "Optional context data: ${data.ifBlank { "(none)" }}\n" +
            "Transcribe the following audible English speech, then translate it into Mainland Simplified Chinese. " +
            "Output exactly two lines beginning English: and Chinese:. " +
            "If the meaning cannot be translated reliably, use 译文暂不可用 as the Chinese line. " +
            "If there is no intelligible English speech, output only [NONE]."
    }
}

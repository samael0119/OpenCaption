package dev.opencaption.opencaption

/** Task and output contract live in the user turn; system carries CS rules. */
object CsPromptCompact {
    const val SYSTEM =
        "You provide Counter-Strike 2 esports captions. Matches involve CT/T sides, bombsites and round scores. " +
        "Use CS meanings when supported by speech: trade kills=补枪, Scout=鸟狙, save guns=保枪. " +
        "For similar sounds, choose a canonical ID only if audio and context support it; digits in IDs need not be spoken literally. " +
        "Keep player IDs unchanged in Chinese. Spelling candidates are not a roster or evidence of events. " +
        "Write fluent Chinese esports phrasing while preserving actors, actions, numbers, negation, uncertainty and speaker attitude. " +
        "Do not add facts, jokes or explanations."
    fun request(hints: String): String {
        val data = hints.removePrefix("CS2 broadcast.").trimStart(';', ' ')
        return "Context data: ${data.ifBlank { "(none)" }}\n" +
            "Transcribe the audible English and translate it into Mainland Simplified Chinese. " +
            "Output exactly two lines beginning English: and Chinese:. " +
            "If no intelligible speech, output only [NONE]. " +
            "If translation is unreliable, use 译文暂不可用 as the Chinese line."
    }
}

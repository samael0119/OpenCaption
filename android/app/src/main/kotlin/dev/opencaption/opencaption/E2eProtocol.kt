package dev.opencaption.opencaption

/** Stable prompt and response parser shared by every Android E2E backend. */
object E2eProtocol {
    private const val MAINLAND_SIMPLIFIED_RULE =
        "Use Mainland China Simplified Chinese (简体中文, zh-CN). " +
            "Do NOT output Traditional Chinese (繁體中文)."

    fun promptFor(task: String): String = when (task) {
        "english" -> "Transcribe audible English speech. Output only the English transcription, without labels, translation or explanation. If no intelligible English speech, output only [NONE]."
        "chinese" -> "Transcribe audible Chinese speech. $MAINLAND_SIMPLIFIED_RULE Output only the Chinese transcription, without translation, romanization or explanation. If no intelligible Chinese speech, output only [NONE]."
        "auto_zh" -> "Identify the spoken language and transcribe the audible speech in its original language, then translate it into Chinese. $MAINLAND_SIMPLIFIED_RULE Output exactly two lines: Original: <transcription> and Chinese: <translation>. If the meaning cannot be translated reliably, use 译文暂不可用 as the Chinese line. If no intelligible speech, output only [NONE]."
        else -> PROMPT
    }

    fun parseFor(raw: String, task: String): Result {
        if (task == "bilingual") return parse(raw)
        val cleaned = controlToken.replace(raw.replace(promptFor(task), ""), "").trim()
        if (sentinel.matches(cleaned)) return Result.NoSpeech
        if (cleaned.isBlank() || structuredOrReasoning.containsMatchIn(cleaned) || reasoningLine.containsMatchIn(cleaned) || cleaned.contains("[NONE]", true)) return Result.Invalid("task_output_invalid")
        if (task == "english") {
            val text = englishLabel.replace(cleaned, "").trim()
            if (!latin.containsMatchIn(text) || han.containsMatchIn(text) || text.contains("Chinese:", true)) return Result.Invalid("english_only_invalid")
            return Result.Subtitle(text, "")
        }
        if (task == "chinese") {
            val text = chineseLabel.replace(cleaned, "").trim()
            if (!validChinese(text) || latin.containsMatchIn(text)) return Result.Invalid("chinese_only_invalid")
            return Result.Subtitle("", text)
        }
        val match = Regex("^Original\\s*[:：]\\s*(.+?)\\s*(?:\\r?\\n|\\s+and\\s+)(?:Chinese|中文)\\s*[:：]\\s*(.+)$", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL)).matchEntire(cleaned)
            ?: return Result.Invalid("auto_language_format")
        val original=match.groupValues[1].trim(); val chinese=match.groupValues[2].trim()
        if (!original.any { it.isLetter() } || !validChinese(chinese)) return Result.Invalid("auto_language_missing_fields")
        return Result.Subtitle(original, chinese)
    }
    const val PROMPT =
        "Transcribe the following speech segment in English, then translate it into Chinese. " +
            "Use Mainland China Simplified Chinese (简体中文, zh-CN). " +
            "Do NOT output Traditional Chinese (繁體中文). " +
        "Output exactly two lines beginning English: and Chinese:. " +
            "If the meaning cannot be translated reliably, use 译文暂不可用 as the Chinese line. " +
            "If there is no intelligible English speech, output only [NONE]."

    sealed interface Result {
        data class Subtitle(val english: String, val chinese: String) : Result
        data object NoSpeech : Result
        data class Invalid(val reason: String) : Result
    }

    private val controlToken = Regex("<\\|[^>]+\\|>|<(?:start|end)_of_turn>", RegexOption.IGNORE_CASE)
    private val sentinel = Regex("^(?:\\[NONE]|NO_SPEECH)[.!]?$", RegexOption.IGNORE_CASE)
    private val structuredOrReasoning = Regex(
        "<think|<analysis|```|^\\s*[{\\[]\\s*[\"']|^\\s*(?:analysis|reasoning|explanation)\\s*:",
        RegexOption.IGNORE_CASE,
    )
    private val reasoningLine = Regex(
        "^\\s*(?:analysis|reasoning|explanation)\\s*:",
        setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE),
    )
    private val latin = Regex("[A-Za-z]")
    private val han = Regex("[\\u3400-\\u9fff]")
    private val englishLabel = Regex("^(?:English|EN|Transcript|Transcription)\\s*[:：]\\s*", RegexOption.IGNORE_CASE)
    private val chineseLabel = Regex("^(?:(?:and|和)\\s*)?(?:Chinese|中文|ZH(?:-CN)?|Translation|翻译)\\s*[:：]\\s*", RegexOption.IGNORE_CASE)
    private val pair = Regex(
        "(?:^|[\\r\\n])\\s*(?:English|EN|Transcript|Transcription)\\s*[:：]\\s*(.+?)" +
            "\\s*(?:\\r?\\n|\\s+and\\s+)(?:and\\s+)?(?:Chinese|中文|ZH(?:-CN)?|Translation|翻译)" +
            "\\s*[:：]\\s*(.+?)(?=(?:[\\r\\n]+\\s*(?:English|EN|Transcript|Transcription)" +
            "\\s*[:：])|\\z)",
        setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
    )
    private val unlabeledEnglishPair = Regex(
        "^\\s*(.+?)\\s*[\\r\\n]+\\s*(?:and\\s+)?(?:Chinese|中文|ZH(?:-CN)?|Translation|翻译)" +
            "\\s*[:：]\\s*(.+?)\\s*\\z",
        setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
    )

    fun parse(raw: String): Result {
        if (raw.isBlank()) return Result.Invalid("blank")

        // Some model/runtime combinations echo the user prompt. Removing only
        // the exact prompt avoids interpreting its NO_SPEECH instruction as a
        // classification result.
        val cleaned = controlToken.replace(raw.replace(PROMPT, "", ignoreCase = true), "").trim()
        if (cleaned.isBlank()) return Result.Invalid("prompt_echo_only")
        if (sentinel.matches(cleaned)) return Result.NoSpeech
        if (structuredOrReasoning.containsMatchIn(cleaned) || reasoningLine.containsMatchIn(cleaned)) {
            return Result.Invalid("structured_or_reasoning_output")
        }

        val values = pair.findAll(cleaned).lastOrNull()?.groupValues
            ?: unlabeledEnglishPair.matchEntire(cleaned)?.groupValues
        val (english, chinese) = if (values != null) {
            tidy(values[1]) to tidy(values[2])
        } else {
            val lines = cleaned.lines().map(String::trim).filter(String::isNotBlank)
            if (lines.size != 2) return Result.Invalid("missing_bilingual_labels")
            val first = tidy(englishLabel.replace(lines[0], ""))
            val second = tidy(
                chineseLabel.replace(lines[1], "")
                    .replace(Regex("^(?:and\\s+|和\\s*[:：]\\s*)", RegexOption.IGNORE_CASE), ""),
            )
            if (!latin.containsMatchIn(first) || han.containsMatchIn(first)) {
                return Result.Invalid("missing_bilingual_labels")
            }
            first to second
        }
        if (english.isBlank() || chinese.isBlank()) return Result.Invalid("empty_bilingual_field")
        if (sentinel.matches(english) || sentinel.matches(chinese)) {
            return Result.Invalid("sentinel_mixed_with_subtitle")
        }
        if (!latin.containsMatchIn(english)) return Result.Invalid("english_missing_latin")
        if (!validChinese(chinese)) return Result.Invalid("chinese_invalid")
        if (english.contains("[NONE]", ignoreCase = true) || chinese.contains("[NONE]", ignoreCase = true)) {
            return Result.Invalid("sentinel_mixed_with_subtitle")
        }
        return Result.Subtitle(english, chinese)
    }

    private val forbiddenChineseScript = Regex("[\\u0400-\\u04ff\\u3040-\\u30ff\\uac00-\\ud7af]")
    private val replacementCharacter = Regex("�")
    private val repeatedCharacter = Regex("(.)\\1{8,}")

    /** Keep proper-name Latin tokens, but reject copied English/other scripts. */
    private fun validChinese(value: String): Boolean {
        val text = tidy(value)
        if (text.isBlank() || !han.containsMatchIn(text) ||
            replacementCharacter.containsMatchIn(text) ||
            forbiddenChineseScript.containsMatchIn(text) ||
            repeatedCharacter.containsMatchIn(text)) return false
        val hanCount = text.count { it in '\u3400'..'\u9fff' }
        val latinCount = text.count { it in 'A'..'Z' || it in 'a'..'z' }
        val latinWords = Regex("[A-Za-z]{2,}").findAll(text).count()
        return latinCount <= hanCount * 2 + 24 && !(latinWords >= 4 && hanCount < 8)
    }

    private fun tidy(value: String): String = value
        .replace(Regex("[\\r\\n]+"), " ")
        .replace(Regex("\\s+"), " ")
        .trim()
        .trim('"', '\'', '*', '`')
        .trim()
}

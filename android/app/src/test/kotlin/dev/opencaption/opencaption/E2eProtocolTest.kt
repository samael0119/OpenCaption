package dev.opencaption.opencaption

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class E2eProtocolTest {
    @Test fun repeatedStandaloneAndCompleteSilencePairIsNoSpeech() {
        // Actual quiet-whisper-471 output from the bounded gain2 diagnostic.
        assertEquals(E2eProtocol.Result.NoSpeech,
            E2eProtocol.parse("[NONE]\nEnglish: [NONE]\nChinese: [NONE]"))
        assertEquals(E2eProtocol.Result.NoSpeech,
            E2eProtocol.parse("  [none]\r\n English：[NONE]\r\n 中文：[none]  "))
        assertEquals(E2eProtocol.Result.NoSpeech,
            E2eProtocol.parseFor("[NONE]\nOriginal: [NONE]\nChinese: [NONE]", "auto_zh"))
    }

    @Test fun repeatedSilenceCannotHideRealTextOrIncompleteDeclarations() {
        for (raw in listOf(
            "Hello\n[NONE]\nEnglish: [NONE]\nChinese: [NONE]",
            "[NONE]\nEnglish: [NONE]",
            "[NONE]\n[NONE]",
            "[NONE]\nEnglish: [NONE]\nChinese: [NONE]\nNo speech",
            "Explanation: quiet\n[NONE]\nEnglish: [NONE]\nChinese: [NONE]",
            "[NONE]\nFrench: [NONE]\nChinese: [NONE]",
            "[NONE]\nEnglish: [NONE]\nEnglish: [NONE]\nChinese: [NONE]",
        )) {
            assertTrue(raw, E2eProtocol.parse(raw) is E2eProtocol.Result.Invalid)
        }
        assertTrue(E2eProtocol.parseFor(
            "[NONE]\nOriginal: Bonjour\nChinese: 你好", "auto_zh") is E2eProtocol.Result.Invalid)
    }

    @Test fun silencePreambleDoesNotEraseACompleteSpeechPair() {
        // Preserve existing last-complete-pair compatibility, including the
        // historical run1 window957 shape. Such replies are never NoSpeech.
        for (prefix in listOf("[NONE]\n", "English: [NONE]\nChinese: [NONE]\n")) {
            assertEquals(E2eProtocol.Result.Subtitle("Hello", "你好"),
                E2eProtocol.parse(prefix + "English: Hello\nChinese: 你好"))
        }
        assertEquals(E2eProtocol.Result.Subtitle("No, number two design is bit there.", "译文暂不可用"),
            E2eProtocol.parse("[NONE]\nEnglish: No, number two design is bit there.\nChinese: 译文暂不可用"))
    }

    @Test fun shortNumericAnswersAndScoresDoNotRequireLetters() {
        assertEquals(E2eProtocol.Result.Subtitle("12", "12"), E2eProtocol.parse("English: 12\nChinese: 12"))
        assertEquals(E2eProtocol.Result.Subtitle("12", "十二"), E2eProtocol.parse("12\n十二"))
        assertEquals(E2eProtocol.Result.Subtitle("12-11", "12-11"), E2eProtocol.parse("English: 12-11\nChinese: 12-11"))
        assertEquals(E2eProtocol.Result.Subtitle("12", ""), E2eProtocol.parseFor("12", "english"))
        assertEquals(E2eProtocol.Result.Subtitle("", "12"), E2eProtocol.parseFor("Chinese: 12", "chinese"))
        assertEquals(E2eProtocol.Result.Subtitle("12", "12"), E2eProtocol.parseFor("Original: 12\nChinese: 12", "auto_zh"))
    }

    @Test fun numericExceptionDoesNotRelaxSentinelsOrCopiedEnglish() {
        for (raw in listOf("English: 12\nChinese: [NONE]", "English: ...\nChinese: ...",
            "English: [12]\nChinese: [12]", "English: 12\nChinese: Twelve",
            "English: donk\nChinese: donk", "Explanation: score\nEnglish: 12\nChinese: 12")) {
            assertTrue(raw, E2eProtocol.parse(raw) is E2eProtocol.Result.Invalid)
        }
        assertTrue(E2eProtocol.parseFor("...", "english") is E2eProtocol.Result.Invalid)
        assertTrue(E2eProtocol.parseFor("[12]", "chinese") is E2eProtocol.Result.Invalid)
    }

    @Test fun balancedExactSentinelsAreNoSpeechOnlyWhenEntireReplyMatches() {
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parse("English: [NONE]\nChinese: [NONE]"))
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parse("[NONE]\nand 中文：[NONE]"))
        for (raw in listOf("English: hello\nChinese: [NONE]", "English: [NONE]\nChinese: 你好",
            "English: [NONE]", "Chinese: [NONE]", "Explanation: silence\nEnglish: [NONE]\nChinese: [NONE]",
            "English: [NONE]\nChinese: [NONE]\nNo speech")) {
            assertTrue(raw, E2eProtocol.parse(raw) is E2eProtocol.Result.Invalid)
        }
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parseFor("Original: [NONE]\nChinese: [NONE]", "auto_zh"))
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parseFor("Chinese: [NONE]", "chinese"))
    }

    @Test fun englishOnlyHasNoFabricatedTranslation() {
        assertEquals(E2eProtocol.Result.Subtitle("Hello world.", ""), E2eProtocol.parseFor("Hello world.", "english"))
        assertTrue(E2eProtocol.parseFor("你好", "english") is E2eProtocol.Result.Invalid)
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parseFor("[NONE]", "english"))
    }

    @Test fun chineseOnlyHasNoTranslationPair() {
        assertEquals(E2eProtocol.Result.Subtitle("", "这是中文转写。"), E2eProtocol.parseFor("这是中文转写。", "chinese"))
        assertEquals(E2eProtocol.Result.Subtitle("", "这是中文转写。"), E2eProtocol.parseFor("中文：这是中文转写。", "chinese"))
        assertTrue(E2eProtocol.parseFor("This is English.", "chinese") is E2eProtocol.Result.Invalid)
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parseFor("[NONE]", "chinese"))
    }

    @Test fun chinesePromptsRequireMainlandSimplified() {
        val rule = "Use Mainland China Simplified Chinese (简体中文, zh-CN)."
        assertTrue(E2eProtocol.PROMPT.contains(rule))
        assertTrue(E2eProtocol.PROMPT.contains("Do NOT output Traditional Chinese (繁體中文)."))
        assertTrue(E2eProtocol.promptFor("chinese").contains(rule))
        assertTrue(E2eProtocol.promptFor("auto_zh").contains(rule))
    }

    @Test fun automaticLanguageAllowsNonLatinSourceButRequiresChinese() {
        assertEquals(E2eProtocol.Result.Subtitle("こんにちは", "你好"), E2eProtocol.parseFor("Original: こんにちは\nChinese: 你好", "auto_zh"))
        assertTrue(E2eProtocol.parseFor("Original: Bonjour\nChinese: Bonjour", "auto_zh") is E2eProtocol.Result.Invalid)
        assertTrue(E2eProtocol.parseFor("<think>reasoning</think>\nOriginal: Hi\nChinese: 你好", "auto_zh") is E2eProtocol.Result.Invalid)
    }
    @Test fun parsesTwoLines() {
        assertEquals(
            E2eProtocol.Result.Subtitle(
                "They completely lost control of Banana.",
                "他们彻底丢掉了香蕉道的控制权。",
            ),
            E2eProtocol.parse(
                "English: They completely lost control of Banana.\n" +
                    "Chinese: 他们彻底丢掉了香蕉道的控制权。",
            ),
        )
    }

    @Test fun parsesSingleLineRuntimeResponse() {
        assertEquals(
            E2eProtocol.Result.Subtitle("That's a beautiful sunset.", "那是美丽的日落。"),
            E2eProtocol.parse(
                "English: That's a beautiful sunset. and Chinese: 那是美丽的日落。",
            ),
        )
    }

    @Test fun parsesOfficialAstStyleWithUnlabeledEnglishFirstLine() {
        assertEquals(
            E2eProtocol.Result.Subtitle(
                "Yeah, and sure enough, Daco fine",
                "是的，而且果然，达科很好",
            ),
            E2eProtocol.parse(
                "Yeah, and sure enough, Daco fine\nChinese: 是的，而且果然，达科很好",
            ),
        )
    }

    @Test fun parsesAndChineseOnSecondLine() {
        assertEquals(
            E2eProtocol.Result.Subtitle(
                "around that door and exposed to a killer",
                "在那扇门周围，暴露给一个杀手",
            ),
            E2eProtocol.parse(
                "around that door and exposed to a killer\n" +
                    "and Chinese: 在那扇门周围，暴露给一个杀手",
            ),
        )
    }

    @Test fun parsesTwoUnlabeledLanguageLines() {
        assertEquals(
            E2eProtocol.Result.Subtitle(
                "Now, Zerschen sends a bullet back through the other way.",
                "泽尔森把子弹射向另一边。",
            ),
            E2eProtocol.parse(
                "Now, Zerschen sends a bullet back through the other way.\n" +
                    "泽尔森把子弹射向另一边。",
            ),
        )
    }

    @Test fun promptEchoCannotTurnValidSubtitleIntoNoSpeech() {
        val raw = E2eProtocol.PROMPT +
            "\nEnglish: The crowd is getting louder.\nChinese: 观众的欢呼声越来越大。"
        assertTrue(E2eProtocol.parse(raw) is E2eProtocol.Result.Subtitle)
    }

    @Test fun onlyExactSentinelMeansNoSpeech() {
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parse("[NONE]"))
        assertEquals(E2eProtocol.Result.NoSpeech, E2eProtocol.parse("NO_SPEECH"))
        assertTrue(
            E2eProtocol.parse("Please output NO_SPEECH when quiet") is E2eProtocol.Result.Invalid,
        )
    }

    @Test fun rejectsReasoningLabelInUnlabeledFallback() {
        assertTrue(
            E2eProtocol.parse("Analysis: I should translate\n翻译一下") is E2eProtocol.Result.Invalid,
        )
    }

    @Test fun rejectsMalformedOutputWithoutCreatingSubtitle() {
        assertEquals(
            E2eProtocol.Result.Invalid("missing_bilingual_labels"),
            E2eProtocol.parse("A free-form answer without labels."),
        )
    }
}

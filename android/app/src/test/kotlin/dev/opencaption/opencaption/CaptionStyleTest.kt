package dev.opencaption.opencaption

import org.junit.Assert.*
import org.junit.Test

class CaptionStyleTest {
    private val community = CaptionStyle.Options("community", true)

    @Test fun standardAndTranscriptionKeepTheirExistingPrompt() {
        for (task in listOf("bilingual", "auto_zh", "english", "chinese")) for (style in CaptionStyle.styles) {
            assertEquals(E2eProtocol.systemFor(task), CaptionStyle.systemFor(task, style))
        }
    }

    @Test fun nicknamesRequireTheSameCanonicalIdentityInBothLanguages() {
        val result = CaptionStyle.render("karrigan traded ZywOo.", "karrigan 补枪带走了 ZywOo。", community, true, true)
        assertEquals("大表哥 补枪带走了 载物。", result.chinese)
        assertEquals(2, result.nicknamesUsed)
        assertEquals("ZywOo 留在原地。", CaptionStyle.render("karrigan stays.", "ZywOo 留在原地。", community, true, true).chinese)
        assertEquals("s1mpleX 赢了。", CaptionStyle.render("s1mpleX wins.", "s1mpleX 赢了。", community, true, true).chinese)
    }

    @Test fun ordinaryWordsUnknownNamesAndOtherDomainsRemainUntouched() {
        for (pair in listOf("It is simple." to "这很 simple。", "A bit of time." to "一点 bit 时间。", "Other wins." to "Other 赢了。")) {
            assertEquals(pair.second, CaptionStyle.render(pair.first, pair.second, community, true, true).chinese)
        }
        assertEquals("karrigan 赢了。", CaptionStyle.render("karrigan wins.", "karrigan 赢了。", community, false, true).chinese)
    }

    @Test fun nicknamesAreIndependentOfPlayfulMode() {
        assertEquals("森破 赢了。", CaptionStyle.render("s1mple wins.", "s1mple 赢了。", CaptionStyle.Options("standard", true), true, true).chinese)
        assertEquals("s1mple 赢了。", CaptionStyle.render("s1mple wins.", "s1mple 赢了。", CaptionStyle.Options("community", false), true, true).chinese)
    }

    @Test fun playfulExpressionRequiresAnUnambiguousFactInBothLanguages() {
        assertTrue(CaptionStyle.render("He misses every shot.", "他一枪都没打中。", community, true, true).playful)
        for (english in listOf("If he misses every shot.", "He never misses every shot.", "He almost misses every shot.", "They say he misses every shot.", "He misses every shot, but wins.")) {
            assertFalse(english, CaptionStyle.render(english, "他一枪都没打中。", community, true, true).playful)
        }
        assertFalse(CaptionStyle.render("He misses every shot.", "他并非一枪都没打中。", community, true, true).playful)
        assertFalse(CaptionStyle.render("He misses every shot.", "他一枪没中，但随后赢了。", community, true, true).playful)
    }

    @Test fun cooldownAndDomainAndModeCanEachVetoTheJoke() {
        val en = "He misses every shot."; val zh = "他一枪没中。"
        assertFalse(CaptionStyle.render(en, zh, community, true, false).playful)
        assertFalse(CaptionStyle.render(en, zh, community, false, true).playful)
        assertFalse(CaptionStyle.render(en, zh, CaptionStyle.Options("natural"), true, true).playful)
    }

    @Test fun renderingDoesNotInventOrDeleteNumbersOrNegation() {
        val zh = "karrigan 没赢下 1 对 2，时间只剩 12 秒。"
        val rendered = CaptionStyle.render("karrigan did not win the 1v2; only 12 seconds remain.", zh, community, true, true)
        assertEquals("大表哥 没赢下 1 对 2，时间只剩 12 秒。", rendered.chinese)
        assertFalse(rendered.playful)
    }

    @Test fun lexicalStylePreservesNegationAndHasSourceMeaningGuards() {
        val opts = CaptionStyle.Options("natural")
        assertEquals("他们应该保枪，而不是回防。", CaptionStyle.render(
            "They should save their weapons, not go for the retake.", "他们应该保存他们的武器，而不是去夺回。", opts, true, true).chinese)
        assertEquals("他没拿下一打二。", CaptionStyle.render(
            "He did not win the one-versus-two.", "他没拿下一对二。", opts, true, true).chinese)
        val unchanged = "请保存他们的武器设置。"
        assertEquals(unchanged, CaptionStyle.render("Please save their weapon settings.", unchanged, opts, true, true).chinese)
        assertEquals("炸弹还没有被拆掉。", CaptionStyle.render("The bomb has not been defused yet.", "炸弹还没有被解除。", opts, true, true).chinese)
        assertEquals("请解除闹钟。", CaptionStyle.render("Disable the alarm.", "请解除闹钟。", opts, true, true).chinese)
    }

    @Test fun translatedFormsRequireTheCanonicalEnglishIdentity() {
        assertEquals("大表哥 赢了。", CaptionStyle.render("karrigan wins.", "卡里根 赢了。", community, true, true).chinese)
        assertEquals("卡里根 赢了。", CaptionStyle.render("Other wins.", "卡里根 赢了。", community, true, true).chinese)
        for (text in listOf("卡里根X 赢了。", "卡里根斯基 赢了。")) {
            assertEquals(text, CaptionStyle.render("karrigan wins.", text, community, true, true).chinese)
        }
    }
}

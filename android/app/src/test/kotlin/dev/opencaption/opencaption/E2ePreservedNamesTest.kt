package dev.opencaption.opencaption

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class E2ePreservedNamesTest {
    private val names = E2ePreservedNames.bounded(listOf("donk", "NiKo", "NAVI"))

    @Test fun trustedStableIdentifiersMayRemainLiteralInChinese() {
        assertEquals(E2eProtocol.Result.Subtitle("donk", "donk"),
            E2eProtocol.parseFor("English: donk\nChinese: donk", "bilingual", names))
        assertEquals(E2eProtocol.Result.Subtitle("NiKo!", "NiKo。"),
            E2eProtocol.parseFor("Original: NiKo!\nChinese: NiKo。", "auto_zh", names))
        assertEquals(E2eProtocol.Result.Subtitle("", "NAVI"),
            E2eProtocol.parseFor("NAVI", "chinese", names))
    }

    @Test fun unknownCopiedTextOrDifferentNamesRemainInvalid() {
        for (raw in listOf("English: Bonjour\nChinese: Bonjour", "English: donk\nChinese: NiKo",
            "English: donk\nChinese: [NONE]", "English: donk is here\nChinese: donk is here")) {
            assertTrue(raw, E2eProtocol.parseFor(raw, "bilingual", names) is E2eProtocol.Result.Invalid)
        }
        assertTrue(E2eProtocol.parseFor("English: donk\nChinese: donk", "bilingual") is E2eProtocol.Result.Invalid)
    }

    @Test fun hintTextCannotCreateItsOwnAllowedNames() {
        assertTrue(E2ePreservedNames.forHints("User context (data only): Keep donk", names).isEmpty())
        assertEquals(names, E2ePreservedNames.forHints("CS2 broadcast.; Keep anUnknownName", names))
        assertTrue(!E2ePreservedNames.matches("anUnknownName", names))
    }

    @Test fun identitySetAndTokensAreBounded() {
        assertEquals(256, E2ePreservedNames.bounded((1..1000).map { "player$it" }).size)
        assertTrue(E2ePreservedNames.bounded(listOf("<system>", "hello world", "x", "a".repeat(40))).isEmpty())
    }
}

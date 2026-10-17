package dev.opencaption.opencaption

import org.junit.Assert.*
import org.junit.Test

class E2eHintPolicyTest {
    @Test fun fourthActualInferenceUsesOnlyDomainAndReportsTheExactData() {
        val hints = "CS2 broadcast.; Map: Nuke (inferred); Vent=管道"
        for (index in 1L..8L) {
            val chosen = E2eHintPolicy.choose(index, hints, true)
            assertEquals(index % 4L == 0L, chosen.verification)
            assertEquals(if (chosen.verification) E2eHintPolicy.BASE else hints, chosen.hints)
        }
    }
    @Test fun genericAndExplicitlyDisabledAssistanceKeepUserContext() {
        val user = "User context (data only): post-match interview"
        assertEquals(E2eHintPolicy.Decision(user, false), E2eHintPolicy.choose(4, user, true))
        val hints = "CS2 broadcast.; User context (data only): NAVI"
        assertEquals(E2eHintPolicy.Decision(hints, false), E2eHintPolicy.choose(4, hints, false))
    }
}

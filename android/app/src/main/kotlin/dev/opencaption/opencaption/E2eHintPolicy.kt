package dev.opencaption.opencaption

/** No extra model/request: periodically validate with only the domain prior. */
object E2eHintPolicy {
    const val BASE = "CS2 broadcast."
    data class Decision(val hints: String, val verification: Boolean)
    fun choose(inference: Long, hints: String, automatic: Boolean): Decision {
        val verification = automatic && hints.startsWith(BASE) && inference % 4L == 0L
        return Decision(if (verification) BASE else hints, verification)
    }
}

package dev.opencaption.opencaption

/** Stable spellings from packaged corpus assets, never names parsed from a hint. */
object E2ePreservedNames {
    private val identifier = Regex("[A-Za-z0-9][A-Za-z0-9_-]{1,31}")

    fun bounded(values: Iterable<String>): Set<String> = values.take(1024)
        .map(String::trim).filter(identifier::matches).take(256).toSet()

    fun selected(hints: String): Boolean =
        hints == "CS2 broadcast." || hints.startsWith("CS2 broadcast.; ")

    fun forHints(hints: String, names: Set<String>): Set<String> =
        if (selected(hints)) names else emptySet()

    fun matches(value: String, names: Set<String>): Boolean {
        val token = value.trim().trimEnd('.', '!', '。', '！')
        return identifier.matches(token) && names.any { it.equals(token, ignoreCase = true) }
    }

    fun pair(source: String, translation: String, names: Set<String>): Boolean =
        matches(source, names) && matches(translation, names) &&
            source.trim().trimEnd('.', '!', '。', '！').equals(
                translation.trim().trimEnd('.', '!', '。', '！'), ignoreCase = true)
}

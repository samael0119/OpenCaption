import dev.opencaption.opencaption.E2eProtocol
import java.util.Base64

/** Audit private product regexes without reimplementing their matching semantics. */
object V020Integrity8 {
    private fun enc(s: String) = Base64.getEncoder().encodeToString(s.toByteArray(Charsets.UTF_8))
    private fun regex(name: String): Regex = E2eProtocol::class.java.getDeclaredField(name).let {
        it.isAccessible = true; it.get(null) as Regex
    }
    @JvmStatic fun main(args: Array<String>) {
        val control = regex("controlToken"); val pair = regex("pair")
        generateSequence(::readLine).forEach { line ->
            val f = line.split('\t'); val task = f[0]
            val raw = String(Base64.getDecoder().decode(f[1]), Charsets.UTF_8)
            val result = E2eProtocol.parseFor(raw, task)
            val cleaned = control.replace(raw.replace(E2eProtocol.PROMPT, "", ignoreCase = true), "").trim()
            val matches = if (task == "bilingual") pair.findAll(cleaned).toList() else emptyList()
            val status = when(result) {
                is E2eProtocol.Result.Subtitle -> "subtitle\t${enc(result.english)}\t${enc(result.chinese)}"
                is E2eProtocol.Result.Invalid -> "invalid\t${enc(result.reason)}\t"
                E2eProtocol.Result.NoSpeech -> "no_speech\t\t"
            }
            val groups = matches.joinToString(";") { "${it.range.first},${it.range.last + 1},${enc(it.groupValues[1])},${enc(it.groupValues[2])}" }
            println("$status\t${enc(cleaned)}\t$groups")
        }
    }
}

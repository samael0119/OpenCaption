package dev.opencaption.opencaption

import org.json.JSONObject
import kotlin.math.abs

/** Presentation follows canonical recognition; nicknames never become ASR hints. */
object CaptionStyle {
    val styles = setOf("standard", "natural", "community")
    data class Options(val style: String = "standard", val nicknames: Boolean = false)
    data class Rendered(val chinese: String, val nicknamesUsed: Int, val playful: Boolean, val localizedPhrases: Int = 0)
    data class CommunityName(
        val id: String,
        val variants: List<String>,
        val source: String = "",
        val translatedForms: List<String> = emptyList(),
        val requireContext: Boolean = false,
    ) {
        val chinese: String get() = variants.first()
        fun pick(seed: Int): String =
            if (variants.size <= 1) variants.first() else variants[abs(seed) % variants.size]
    }

    // Minimal fallback for JVM unit tests when Android assets are not mounted.
    // At runtime on Android, MainActivity loads the shared SSOT asset
    // `assets/corpora/cs2_player_nicknames.json` via `loadFromJson(...)`.
    private val fallbackNames = listOf(
        CommunityName("karrigan", listOf("大表哥"), "https://www.csgo.com.cn/article/details/20191025/216681.html", listOf("卡里根")),
        CommunityName("s1mple", listOf("森破"), "https://csgo.5eplay.com/article/s1mple-the-future-i-will-probably-leave-i-have-to-reset-itself1520"),
        CommunityName("ZywOo", listOf("载物"), "https://csgo.5eplay.com/article/231107prjdf6"),
    )

    @Volatile private var loadedNames: List<CommunityName>? = null
    val names: List<CommunityName> get() = loadedNames ?: fallbackNames

    fun loadFromJson(raw: String) {
        val root = JSONObject(raw)
        val players = root.optJSONArray("players") ?: return
        val parsed = ArrayList<CommunityName>()
        for (i in 0 until players.length()) {
            val obj = players.optJSONObject(i) ?: continue
            val id = obj.optString("id").trim()
            val nicksArr = obj.optJSONArray("nicknames") ?: continue
            val variants = ArrayList<String>()
            for (j in 0 until nicksArr.length()) {
                val v = nicksArr.optString(j).trim()
                if (v.isNotEmpty()) variants.add(v)
            }
            if (id.isEmpty() || variants.isEmpty()) continue
            val formsArr = obj.optJSONArray("translated_forms")
            val forms = ArrayList<String>()
            if (formsArr != null) {
                for (j in 0 until formsArr.length()) {
                    val f = formsArr.optString(j).trim()
                    if (f.isNotEmpty()) forms.add(f)
                }
            }
            parsed.add(
                CommunityName(
                    id = id,
                    variants = variants,
                    translatedForms = forms,
                    requireContext = obj.optBoolean("require_context", false),
                )
            )
        }
        if (parsed.isNotEmpty()) loadedNames = parsed
    }
    fun translates(task: String) = task == "bilingual" || task == "auto_zh"
    fun systemFor(task: String, style: String): String {
        require(style in styles)
        // The 2026-10-19 audio screen rejected generative style instructions:
        // music hallucinations rose 1/5 -> 2/5. Keep every audio prompt exact.
        return E2eProtocol.systemFor(task)
    }

    private fun token(id: String) = Regex("(?<![A-Za-z0-9_-])${Regex.escape(id)}(?![A-Za-z0-9_-])", RegexOption.IGNORE_CASE)
    private val allMissed = Regex("^He (?:misses every shot|missed every shot|misses all (?:his |the )?shots|missed all (?:his |the )?shots)[.!]?$", RegexOption.IGNORE_CASE)
    private val missedChinese = Regex("^(?:他)?(?:一枪(?:都)?(?:没中|没打中)|所有(?:的)?(?:子弹|射击)都没(?:有)?(?:打中|命中))[。！!，,]?$" )

    fun render(english: String, chinese: String, options: Options, cs2: Boolean, allowPlayful: Boolean): Rendered {
        if (!cs2) return Rendered(chinese, 0, false)
        var text = chinese
        var localized = 0
        fun replace(from: String, to: String) {
            if (text.contains(from)) { text = text.replace(from, to); localized++ }
        }
        if (options.style in setOf("natural", "community")) {
            // Short lexical rewrites with source-side meaning guards. No free
            // generation, sentence deletion, pronoun resolution or score edits.
            replace("只剩下", "只剩")
            if (Regex("one[- ]versus[- ]two|1v2", RegexOption.IGNORE_CASE).containsMatchIn(english)) {
                replace("单对双人", "一打二")
                replace("一对二", "一打二")
                replace("赢了一打二", "拿下了一打二")
            }
            if (Regex("^(?:They|We|You|He|She) (?:should |must |need to )?save (?:their |our |your |his |her |the )?(?:weapons|guns|rifles)(?:,? (?:rather than|not) (?:go for )?the retake)?[.!]?$", RegexOption.IGNORE_CASE).matches(english.trim())) {
                replace("保存他们的武器", "保枪")
                replace("保留他们的武器", "保枪")
                replace("保存武器", "保枪")
            }
            if (Regex("\\bretake\\b", RegexOption.IGNORE_CASE).containsMatchIn(english)) replace("去夺回", "回防")
            if (Regex("\\bgets? two kills\\b", RegexOption.IGNORE_CASE).containsMatchIn(english)) replace("获得了两次击杀", "拿到两次击杀")
            if (Regex("\\bround is not over\\b", RegexOption.IGNORE_CASE).containsMatchIn(english)) replace("局不是结束", "这一局还没结束")
            if (Regex("\\bdefused\\b", RegexOption.IGNORE_CASE).containsMatchIn(english) &&
                Regex("^炸弹(?:还没有|还没|尚未|已经|已|终于)?被解除(?:了)?[。！!]?$" ).matches(text)) replace("被解除", "被拆掉")
        }
        var used = 0
        val seed = english.hashCode()
        if (options.nicknames) for (name in names) {
            if (name.requireContext) continue
            val pattern = token(name.id)
            if (pattern.containsMatchIn(english)) {
                val before = text
                val chosen = name.pick(seed)
                text = pattern.replace(text, chosen)
                // These forms only render a paired canonical identity; they
                // are never pronunciation evidence or reverse ASR aliases.
                for (form in name.translatedForms) {
                    val exactForm = Regex("(^|[\\s，。；！？、,:;!?])${Regex.escape(form)}(?=$|[\\s，。；！？、,:;!?]|赢|没|不|的|拿|将|说|被|只|还|已|在|有|和|与|获|击|留|走|退|补|消)")
                    text = exactForm.replace(text) { it.groupValues[1] + chosen }
                }
                if (text != before) used++
            }
        }
        // Deliberately narrow: exact factual clause in BOTH languages, never a
        // hypothetical, a quotation, a near miss, or a long multi-clause sentence.
        val playful = options.style == "community" && allowPlayful &&
            allMissed.matches(english.trim()) && missedChinese.matches(text.trim())
        if (playful) text = "一枪没中，这波人体描边了。"
        return Rendered(text, used, playful, localized)
    }
}

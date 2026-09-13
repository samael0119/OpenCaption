"""Host-side mirror of the small Android E2E subtitle protocol."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAINLAND_SIMPLIFIED_RULE = (
    "Use Mainland China Simplified Chinese (简体中文, zh-CN). "
    "Do NOT output Traditional Chinese (繁體中文)."
)
_PROMPT_INJECTION = re.compile(
    r"<\s*/?\s*(?:system|user|assistant|developer|think|analysis)\s*>|"
    r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:the\s+)?"
    r"(?:previous|prior|above|these)?\s*(?:instructions?|rules?|prompts?)|"
    r"(?:system|developer|assistant|user)\s*(?:message|prompt|instruction)\s*[:：]|"
    r"(?:output|respond|answer)\s+(?:only|as|in\s+(?:json|xml|yaml))\b|"
    r"(?:jailbreak|prompt\s+injection)",
    re.IGNORECASE,
)


def sanitize_context(value: str, maximum_characters: int = 240) -> str:
    """Keep user context as bounded data, never as a prompt instruction."""
    if _PROMPT_INJECTION.search(value):
        return ""
    normalized = re.sub(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e<>`{}]", " ", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized or _PROMPT_INJECTION.search(normalized):
        return ""
    return normalized[:maximum_characters].rstrip()

PROMPT = (
    "Transcribe the following speech segment in English, then translate it into Chinese. "
    f"{MAINLAND_SIMPLIFIED_RULE} Output exactly two lines beginning English: and Chinese:. "
    "If the meaning cannot be translated reliably, use 译文暂不可用 as the Chinese line. "
    "If there is no intelligible English speech, output only [NONE]."
)
CHINESE_PROMPT = (
    "Transcribe audible Chinese speech. "
    f"{MAINLAND_SIMPLIFIED_RULE} Output only the "
    "Chinese transcription, without translation, romanization or explanation. "
    "If there is no intelligible Chinese speech, output only [NONE]."
)

_CONTROL_TOKEN = re.compile(r"<\|[^>]+\|>|<(?:start|end)_of_turn>", re.IGNORECASE)
_SENTINEL = re.compile(r"^(?:\[NONE]|NO_SPEECH)[.!]?$", re.IGNORECASE)
_STRUCTURED_OR_REASONING = re.compile(
    r"<think|<analysis|```|^\s*[\{\[]\s*[\"']|^\s*(?:analysis|reasoning|explanation)\s*:",
    re.IGNORECASE,
)
_LATIN = re.compile(r"[A-Za-z]")
_HAN = re.compile(r"[\u3400-\u9fff]")
_EN_LABEL = re.compile(r"^(?:English|EN|Transcript|Transcription)\s*[:：]\s*", re.IGNORECASE)
_ZH_LABEL = re.compile(
    r"^(?:(?:and|和)\s*)?(?:Chinese|中文|ZH(?:-CN)?|Translation|翻译)\s*[:：]\s*",
    re.IGNORECASE,
)
_PAIR = re.compile(
    r"(?:^|[\r\n])\s*(?:English|EN|Transcript|Transcription)\s*[:：]\s*(.+?)"
    r"\s*(?:\r?\n|\s+and\s+)(?:and\s+)?(?:Chinese|中文|ZH(?:-CN)?|Translation|翻译)"
    r"\s*[:：]\s*(.+?)(?=(?:[\r\n]+\s*(?:English|EN|Transcript|Transcription)"
    r"\s*[:：])|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_UNLABELED_ENGLISH_PAIR = re.compile(
    r"^\s*(.+?)\s*[\r\n]+\s*(?:and\s+)?(?:Chinese|中文|ZH(?:-CN)?|Translation|翻译)"
    r"\s*[:：]\s*(.+?)\s*\Z",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class ParsedOutput:
    status: str
    english: str | None = None
    chinese: str | None = None
    reason: str | None = None


def parse_output(raw: str, task: str = "bilingual") -> ParsedOutput:
    if not raw.strip():
        return ParsedOutput("invalid", reason="blank")
    prompt = CHINESE_PROMPT if task == "chinese" else PROMPT
    cleaned = _CONTROL_TOKEN.sub("", re.sub(re.escape(prompt), "", raw, flags=re.I)).strip()
    if not cleaned:
        return ParsedOutput("invalid", reason="prompt_echo_only")
    if _SENTINEL.fullmatch(cleaned):
        return ParsedOutput("no_speech")
    if _STRUCTURED_OR_REASONING.search(cleaned):
        return ParsedOutput("invalid", reason="structured_or_reasoning_output")
    if task == "chinese":
        text = _tidy(_ZH_LABEL.sub("", cleaned))
        if not _HAN.search(text) or _LATIN.search(text):
            return ParsedOutput("invalid", reason="chinese_only_invalid")
        return ParsedOutput("transcription", english="", chinese=text)
    matches = list(_PAIR.finditer(cleaned))
    match = matches[-1] if matches else _UNLABELED_ENGLISH_PAIR.fullmatch(cleaned)
    if match:
        english, chinese = (_tidy(value) for value in match.groups())
    else:
        # Gemma's mobile runtime occasionally omits both labels while still
        # returning exactly two language lines. Android accepts this narrow
        # form; keep the host replay parser byte-for-byte compatible so the
        # local score does not measure a parser mismatch.
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        if len(lines) != 2:
            return ParsedOutput("invalid", reason="missing_bilingual_labels")
        english = _tidy(_EN_LABEL.sub("", lines[0]))
        chinese = _tidy(_ZH_LABEL.sub("", lines[1]))
        chinese = re.sub(r"^(?:and\s+|和\s*[:：]\s*)", "", chinese, flags=re.IGNORECASE)
        if not _LATIN.search(english) or _HAN.search(english):
            return ParsedOutput("invalid", reason="missing_bilingual_labels")
    if not english or not chinese:
        return ParsedOutput("invalid", reason="empty_bilingual_field")
    if _SENTINEL.fullmatch(english) or _SENTINEL.fullmatch(chinese):
        return ParsedOutput("invalid", reason="sentinel_mixed_with_subtitle")
    if not _LATIN.search(english):
        return ParsedOutput("invalid", reason="english_missing_latin")
    if not _HAN.search(chinese):
        return ParsedOutput("invalid", reason="chinese_missing_han")
    if "[NONE]" in english.upper() or "[NONE]" in chinese.upper():
        return ParsedOutput("invalid", reason="sentinel_mixed_with_subtitle")
    return ParsedOutput("subtitle", english=english, chinese=chinese)


def _tidy(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().strip("\"'*`").strip()

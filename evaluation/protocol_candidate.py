"""Experimental parser only: not enabled in Android or the baseline replay."""
import re

from e2e_protocol import ParsedOutput, parse_output

HAN = re.compile(r"[\u3400-\u9fff]")
EN_LABEL = re.compile(r"^(?:English|EN|Transcript|Transcription)\s*[:：]\s*", re.I)
ZH_LABEL = re.compile(r"^(?:(?:and|和)\s*)?(?:Chinese|中文|ZH(?:-CN)?|Translation|翻译)\s*[:：]\s*", re.I)


def parse_candidate(raw):
    # Do not turn reasoning, JSON, fences or explanations into visible subtitles.
    if re.search(r"<think|<analysis|```|^\s*[{\[]\s*[\"']", raw, re.I):
        return ParsedOutput("invalid", reason="structured_or_reasoning_output")
    parsed = parse_output(raw)
    if parsed.status == "no_speech":
        return parsed
    if parsed.status != "subtitle":
        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        if len(lines) != 2:
            return parsed
        english = EN_LABEL.sub("", lines[0])
        chinese = ZH_LABEL.sub("", lines[1])
        # Remove only standalone format artifacts; never strip a real Chinese 和.
        chinese = re.sub(r"^(?:and\s+|和\s*[:：]\s*)", "", chinese, flags=re.I)
        if not re.search(r"[A-Za-z]", english) or HAN.search(english):
            return parsed
        if re.search(r"\b(?:analysis|reasoning|translation|transcription)\s*:", english, re.I):
            return parsed
        parsed = ParsedOutput("subtitle", english=english, chinese=chinese)
    if not HAN.search(parsed.chinese or ""):
        return ParsedOutput("invalid", reason="chinese_missing_han")
    if not parsed.english or not re.search(r"[A-Za-z]", parsed.english):
        return ParsedOutput("invalid", reason="english_missing_latin")
    if "[NONE]" in (parsed.english + parsed.chinese).upper():
        return ParsedOutput("invalid", reason="sentinel_mixed_with_subtitle")
    return parsed

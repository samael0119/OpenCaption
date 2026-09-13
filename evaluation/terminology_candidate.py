"""Offline-only CS2 correction candidate. Keep changes auditable and narrowly gated."""
import re


def correct_candidate(english, chinese):
    # Avoid broad replacements for 'scout' as a verb, a person, or multiple
    # ambiguous mentions. Do not try to repair weapon ownership or bad ASR.
    weapon_context = re.search(
        r"\b(?:just a scout|shot out of the scout|scout versus|a scout and an m4)\b",
        english, re.I,
    )
    if (weapon_context and len(re.findall(r"\bscout\b", english, re.I)) == 1
            and chinese.count("侦察兵") == 1):
        return chinese.replace("侦察兵", "鸟狙"), "scout_weapon_context"
    return chinese, None

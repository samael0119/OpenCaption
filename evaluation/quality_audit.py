"""Reference-free diagnostics, NOT a translation accuracy score.

Read replay JSONL; preserve raw output and compare parser compatibility separately
from language-quality warnings. Run once per dataset/configuration.
"""
import argparse
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from e2e_protocol import ParsedOutput, parse_output
from protocol_candidate import parse_candidate


def recover_format(raw):
    # Only accept two explicit fields; never manufacture a missing translation.
    parsed = parse_candidate(raw)
    if parsed.status != "invalid":
        return parsed
    normalized = re.sub(r"(?m)^(\s*)和中文\s*[:：]", r"\1Chinese:", raw)
    if normalized != raw:
        return parse_candidate(normalized)
    # A no-speech CLAIM is not proof of silence. Keep it out of quality accuracy.
    residue = re.sub(r"\[NONE\]|NO_SPEECH|English|Chinese|中文|and|和|EN|ZH", "", raw, flags=re.I)
    if "[NONE]" in raw.upper() and not re.search(r"\w", residue):
        return ParsedOutput("no_speech")
    return parsed


def language_flags(english, chinese):
    flags = []
    if not re.search(r"[\u3400-\u9fff]", chinese):
        flags.append("missing_chinese")
    if any(c.isalpha() and not (
        "LATIN" in unicodedata.name(c, "") or "CJK" in unicodedata.name(c, "")
        or "IDEOGRAPH" in unicodedata.name(c, "")
    ) for c in chinese):
        flags.append("unexpected_script")
    # Four consecutive Latin words are suspicious, not automatically wrong:
    # a full team/player name may be legitimate. Never delete text here.
    if re.search(r"\b[A-Za-z]+(?:[ '\u2019-]+[A-Za-z]+){3,}\b", chinese):
        flags.append("long_latin_span")
    if chinese.strip().lower() == english.strip().lower():
        flags.append("copied_english")
    return flags


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def audit(path):
    groups = defaultdict(list)
    completed = False
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        if row.get("type") == "summary":
            completed = True
        if row.get("type") == "window":
            groups[row.get("source", "unknown")].append(row)
    reports = []
    for source, rows in groups.items():
        counts, warnings, details = Counter(), Counter(), []
        for row in rows:
            raw = row.get("raw", "")
            if row.get("status") == "error":
                counts["engine_error"] += 1
                continue
            if row.get("task") in ("english", "chinese"):
                counts["transcription_only"] += 1
                counts["english_no_speech_claim"] += row.get("status") == "no_speech"
                continue
            old, parsed = parse_candidate(raw), recover_format(raw)
            counts[parsed.status] += 1
            counts["format_recovered"] += int(old.status == "invalid" and parsed.status == "subtitle")
            flags = language_flags(parsed.english, parsed.chinese) if parsed.status == "subtitle" else []
            if parsed.status == "invalid":
                loose = parse_output(raw)
                if loose.status == "subtitle":
                    flags = language_flags(loose.english, loose.chinese)
            warnings.update(flags)
            counts["windows_with_language_warning"] += bool(flags)
            counts["subtitle_with_language_warning"] += bool(flags) and parsed.status == "subtitle"
            if flags or parsed.status == "invalid":
                details.append({"index": row["index"], "start_ms": row["start_ms"],
                                "status": parsed.status, "flags": flags,
                                "reason": parsed.reason, "raw": raw})
        timings = [r["inference_ms"] for r in rows if "inference_ms" in r]
        steady = [r["inference_ms"] for r in rows if "inference_ms" in r
                  and not (r.get("pass") == 1 and r.get("index") == 1)
                  and r["end_ms"] - r["start_ms"] >= 5000]
        processed_audio_ms = sum(r["end_ms"] - r["start_ms"] for r in rows)
        passes = defaultdict(list)
        for row in rows:
            passes[row.get("pass", 1)].append(row)
        # Overlap is extra work, not extra source audio. Include timeline gaps
        # so this metric cannot reward or punish overlapping input incorrectly.
        audio_ms = sum(max(r["end_ms"] for r in group) - min(r["start_ms"] for r in group)
                       for group in passes.values())
        reports.append({
            "source": source, "run_completed": completed,
            "windows": len(rows), "counts": dict(counts),
            "language_warnings": dict(warnings),
            "bilingual_window_rate": counts["subtitle"] / len(rows) if rows and not counts["transcription_only"] else None,
            "inference_p50_ms": percentile(timings, .5),
            "inference_p95_ms": percentile(timings, .95),
            "steady_full_window_p95_ms": percentile(steady, .95),
            "inference_rtf": sum(timings) / audio_ms if timings and audio_ms else None,
            "processed_audio_ms": processed_audio_ms, "source_timeline_ms": audio_ms,
            "peak_rss_mb": max((r.get("peak_rss_mb", 0) for r in rows), default=0),
            "review": details,
            "caveat": "No speech ground truth: window rate is not speech coverage; warnings are heuristics, not semantic accuracy. Serial RTF does not measure queue/display latency.",
        })
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = [{"file": path, "datasets": audit(path)} for path in args.logs]
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)

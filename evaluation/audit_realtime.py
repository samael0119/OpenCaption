"""Timing and experimental parse audit. Valid formatting is NOT semantic accuracy."""
import argparse
import json
import math
from pathlib import Path
from statistics import mean
from protocol_candidate import parse_candidate
from terminology_candidate import correct_candidate


def audit(path):
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    rows = [r for r in records if r.get("type") == "window"]
    measured = [r for r in rows if "inference_ms" in r]
    captures = [r for r in records if r.get("type") == "capture_summary"]
    def p95(key):
        # Serial replays do not emit capture-relative timing fields.  Keep
        # this audit useful for both serial and realtime JSONL instead of
        # failing the whole report on a missing optional metric.
        values = sorted(r[key] for r in measured if key in r)
        return values[math.ceil(len(values)*.95)-1] if values else None
    recovered, rejected, corrections = [], [], []
    candidate_valid = 0
    previous_words = []
    repeated_boundaries = repeated_tokens = 0
    for row in measured:
        if "raw" not in row:
            continue
        candidate = parse_candidate(row["raw"])
        candidate_valid += candidate.status == "subtitle"
        if candidate.status == "subtitle":
            current_words = candidate.english.lower().split()
            boundary_repeat = 0
            for size in range(1, min(12, len(previous_words), len(current_words)) + 1):
                if previous_words[-size:] == current_words[:size]:
                    boundary_repeat = size
            if boundary_repeat:
                repeated_boundaries += 1
                repeated_tokens += boundary_repeat
            previous_words = current_words
            corrected, rule = correct_candidate(candidate.english, candidate.chinese)
            if rule:
                corrections.append(dict(index=row["index"], english=candidate.english,
                                        before=candidate.chinese, after=corrected, rule=rule))
        if row["status"] != "subtitle" and candidate.status == "subtitle":
            recovered.append(dict(index=row["index"], start_ms=row["start_ms"],
                                  english=candidate.english, chinese=candidate.chinese))
        if row["status"] == "subtitle" and candidate.status != "subtitle":
            rejected.append(row["index"])
    audio_ms = sum(r["audio_ms"] for r in captures)
    result = dict(file=str(path), segments=len(rows), processed=len(measured),
                  skipped_exact_zero=sum(r.get("status") == "skipped_silence" for r in rows),
                  dropped=sum(r["status"] == "dropped" for r in rows),
                  baseline_valid=sum(r["status"] == "subtitle" for r in rows),
                  candidate_valid=candidate_valid, candidate_recovered=len(recovered), candidate_rejected=rejected,
                  compute_rtf=round(sum(r["inference_ms"] for r in measured)/audio_ms, 3) if audio_ms else None,
                  inference_p95_ms=p95("inference_ms"), end_to_output_p95_ms=p95("end_to_output_ms"),
                  start_to_output_p95_ms=p95("start_to_output_ms"), queue_wait_p95_ms=p95("queue_wait_ms"),
                  max_capture_late_ms=max((r["max_capture_late_ms"] for r in captures), default=None),
                  peak_rss_mib=max((r["peak_rss_mb"] for r in measured), default=None),
                  adjacent_repeat_boundaries=repeated_boundaries,
                  adjacent_repeat_tokens=repeated_tokens,
                  recovered_for_manual_review=recovered, terminology_candidate_changes=corrections)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()
    for log in args.logs:
        print(json.dumps(audit(log), ensure_ascii=False, indent=2))

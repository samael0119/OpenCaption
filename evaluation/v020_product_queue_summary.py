"""Score product Kotlin queue interval eligibility, never caption correctness.

Read the existing JUnit replay's raw system-out. No inference or duplicate
Python queue implementation. Human SRT times supply the unit boundaries;
their bilingual content is deliberately neither copied nor scored here.
"""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

POLICIES = {"fixed_5000", "pause_600_max_5000"}


def cue_times(text):
    def milliseconds(parts):
        h, m, s, ms = map(int, parts)
        if m >= 60 or s >= 60:
            raise ValueError("Invalid cue timestamp")
        return ((h*60+m)*60+s)*1000+ms
    pattern = r"(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})"
    cues = []
    for match in re.finditer(pattern, text):
        a, b = milliseconds(match.groups()[:4]), milliseconds(match.groups()[4:])
        if not 0 <= a < b:
            raise ValueError("Invalid cue interval")
        cues.append((a, b))
    if not cues:
        raise ValueError("No human reference cue times")
    return cues


def read_intervals(path):
    result = {}
    suite = ET.parse(path).getroot()
    if (suite.tag != "testsuite" or suite.get("name") != "dev.opencaption.opencaption.E2eQueueReplayTest"
            or int(suite.get("failures", "-1")) != 0 or int(suite.get("errors", "-1")) != 0
            or not any(c.get("name") == "measuredNormalAndInjectedSlowTracesAccountForEveryAudioInterval"
                       for c in suite.findall("testcase"))):
        raise ValueError("No successful product replay suite")
    for out in suite.iter("system-out"):
        for line in (out.text or "").splitlines():
            if not line.startswith("product_queue_interval\t"):
                continue
            fields = line.split("\t")
            if len(fields) != 9 or fields[1] not in POLICIES or fields[2] not in {"false", "true"}:
                raise ValueError("Malformed queue evidence")
            policy, slow, state = fields[1:4]
            if state not in {"delivered", "expired", "replaced"}:
                raise ValueError("Unknown queue outcome")
            a, b, submitted, started, at = map(float, fields[4:])
            result.setdefault((policy, slow), []).append(dict(
                state=state, start_ms=a, end_ms=b, submitted_ms=submitted,
                started_ms=started, at_ms=at))
    if set(result) != {(p, s) for p in POLICIES for s in ("false", "true")}:
        raise ValueError("Missing replay configurations; rerunning analysis cannot supply evidence")
    return result


def analyze(rows, cues, duration):
    rows = sorted(rows, key=lambda r: r["start_ms"])
    previous = 0
    for row in rows:
        a, b = row["start_ms"], row["end_ms"]
        if a != previous or not a < b <= duration or b-a > 5000:
            raise ValueError("Duplicate, missing or overlapping owned audio")
        previous = b
        if row["state"] == "delivered":
            if not 0 <= row["started_ms"]-row["submitted_ms"] <= 5000 or row["at_ms"] < row["started_ms"]:
                raise ValueError("Invalid simulated service/age")
    if previous != duration:
        raise ValueError("Incomplete recording coverage")
    units = []
    for index, (a, b) in enumerate(cues, 1):
        if not 0 <= a < b <= duration:
            raise ValueError("Cue outside recording; do not silently trim reference")
        overlaps = [(r, max(0, min(b, r["end_ms"])-max(a, r["start_ms"]))) for r in rows]
        overlaps = [(r, n) for r, n in overlaps if n > 0]
        retained = sum(n for r, n in overlaps if r["state"] == "delivered")
        full = retained == b-a
        units.append(dict(cue=index, start_ms=a, end_ms=b, retained_ms=retained,
            eligible_fraction=retained/(b-a), fully_eligible=full, across_requests=len(overlaps)>1,
            simulated_completion_after_cue_ms=max(r["at_ms"] for r,n in overlaps)-b if full else None))
    delivered = [r for r in rows if r["state"] == "delivered"]
    return dict(raw_intervals=rows, reference_units=units,
        audio_ms=duration, retained_ms=sum(r["end_ms"]-r["start_ms"] for r in delivered),
        dropped_ms=sum(r["end_ms"]-r["start_ms"] for r in rows if r["state"] != "delivered"),
        fully_eligible_units=sum(u["fully_eligible"] for u in units), total_units=len(units),
        max_started_age_ms=max(r["started_ms"]-r["submitted_ms"] for r in delivered),
        model_correctness="not assessed", measured_ui_latency="not assessed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path, required=True)
    parser.add_argument("--gold", type=Path, default=Path("/home/hyh/Downloads/opencaption/clip_gold_bilingual.srt"))
    parser.add_argument("--trace", type=Path, default=Path("android/app/src/test/resources/s0_service_trace.tsv"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/v020-independent/product_queue_summary.json"))
    args = parser.parse_args()
    groups = read_intervals(args.xml)
    ends = {p: [] for p in POLICIES}
    for line in args.trace.read_text().splitlines():
        if line and not line.startswith("#"):
            fields = line.split("\t")
            ends[fields[0]].append(int(float(fields[3])))
    cues = cue_times(args.gold.read_text(encoding="utf-8-sig"))
    report = dict(kind="actual Kotlin product queue, virtual clock with previously measured S0 services",
        fault="+4000ms per service ending at/before 30000ms; merged costs sum original costs",
        limitation="Development recording; ms endpoints truncate sub-ms tail. Eligible audio is not correct caption coverage.",
        product_acceptance_complete=False, configurations={})
    for (policy, slow), rows in groups.items():
        report["configurations"][f"{policy}/slow={slow}"] = analyze(rows, cues, max(ends[policy]))
    report["eligibility_comparison"] = {}
    for slow in ("false", "true"):
        base = report["configurations"][f"fixed_5000/slow={slow}"]
        candidate = report["configurations"][f"pause_600_max_5000/slow={slow}"]
        report["eligibility_comparison"][f"slow={slow}"] = dict(
            retained_audio_not_lower=candidate["retained_ms"] >= base["retained_ms"],
            fully_eligible_units_not_lower=candidate["fully_eligible_units"] >= base["fully_eligible_units"],
            quality_coverage_gate="not measured by this replay")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print(args.output)


if __name__ == "__main__":
    main()

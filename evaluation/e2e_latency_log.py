"""Summarize diagnostics from one OpenCaption Android session log."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re


EVENT = re.compile(r"] (capture_begin|e2e_(?:gap|(?:cut|window|dispatch|controller|flutter_paint|overlay_draw)_timing)) ")
FIELD = re.compile(r"(\w+)=(\S+)")


def distribution(values):
    values = sorted(values)
    result = {"n": len(values), "p50_ms": None, "p95_ms": None}
    if values:
        for name, fraction in (("p50_ms", .5), ("p95_ms", .95)):
            position = (len(values) - 1) * fraction
            base = int(position)
            result[name] = round(values[base] + (values[min(base + 1, len(values) - 1)] - values[base]) * (position - base), 2)
    return result


def gap_duration(intervals):
    end = 0
    total = 0
    for start, stop in sorted(intervals):
        if stop > end:
            total += stop - max(start, end)
            end = stop
    return total


def summarize(lines):
    capture_start = {}
    by_window = defaultdict(dict)
    gaps = defaultdict(list)
    gap_reasons = Counter()
    for line in lines:
        match = EVENT.search(line)
        if not match:
            continue
        event = match[1]
        row = dict(FIELD.findall(line[match.end():]))
        if "epoch" not in row:
            continue
        epoch = int(row["epoch"])
        if event == "capture_begin":
            if "capture_start_elapsed_ms" in row:
                capture_start[epoch] = int(row["capture_start_elapsed_ms"])
        elif event == "e2e_gap":
            if int(row["end_ms"]) > int(row["start_ms"]):
                gaps[epoch].append((int(row["start_ms"]), int(row["end_ms"])))
                gap_reasons[row["reason"]] += 1
        elif "window" in row:
            by_window[(epoch, int(row["window"]))][event] = row
    samples = defaultdict(list)
    first_by_epoch = {}
    outcomes = Counter()
    for (epoch, _), events in by_window.items():
        cut = events.get("e2e_cut_timing")
        worker = events.get("e2e_window_timing")
        dispatch = events.get("e2e_dispatch_timing")
        controller = events.get("e2e_controller_timing")
        if cut:
            samples["cut_audio_span"].append(int(cut["end_ms"]) - int(cut["start_ms"]))
            samples["cut_to_queue"].append(int(cut["queued_elapsed_ms"]) - int(cut["cut_elapsed_ms"]))
        if worker:
            outcomes[worker["status"]] += 1
            for stage in ("queue", "inference", "parse"):
                samples[stage].append(int(worker[f"{stage}_ms"]))
        if controller:
            samples["controller_work"].append(float(controller["work_us"]) / 1000)
        for surface in ("flutter_paint", "overlay_draw"):
            frame = events.get(f"e2e_{surface}_timing")
            if not frame:
                continue
            at = int(frame["elapsed_ms"])
            if dispatch:
                samples[f"dispatch_to_{surface}"].append(at - int(dispatch["elapsed_ms"]))
            for kind in ("source", "translation"):
                if frame.get(kind) != "true":
                    continue
                if cut:
                    samples[f"cut_to_{surface}_{kind}"].append(at - int(cut["cut_elapsed_ms"]))
                if epoch in capture_start:
                    key = (epoch, surface, kind)
                    elapsed = at - capture_start[epoch]
                    first_by_epoch[key] = min(elapsed, first_by_epoch.get(key, elapsed))
    for (_, surface, kind), elapsed in first_by_epoch.items():
        samples[f"capture_to_first_{surface}_{kind}"].append(elapsed)
    return {
        "windows_with_timing": len(by_window),
        "parsed_outcomes": outcomes,
        "gap_events_by_reason": gap_reasons,
        "gap_union_ms": sum(map(gap_duration, gaps.values())),
        "metrics": {stage: distribution(values) for stage, values in sorted(samples.items())},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    with args.log.open() as source:
        print(json.dumps(summarize(source), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

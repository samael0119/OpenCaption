#!/usr/bin/env python3
"""Extract comparable Gemma E2E metrics from an Android session log.

This is a diagnostic summary, not a speech-accuracy scorer. It deliberately
keeps strict parser success separate from semantic quality.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path


STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})")
PERF = re.compile(
    r"e2e_performance window=(\d+) inference_ms=(\d+) audio_ms=(\d+) rtf_milli=(\d+)"
    r"(?: cpu_process_pct=(-?\d+) gpu_pct=(-?\d+))?"
)
RESOURCE = re.compile(r"e2e_resources window=(\d+) queue_wait_ms=(\d+) pending=(\d+) thermal=(-?\d+) native_heap_bytes=(\d+)")
PREPARE = re.compile(r"^(\S+ \S+) \[caption-inference\] prepare_(begin|ok)")


def percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def analyze(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    performance: list[dict] = []
    resources: list[dict] = []
    prepare_begin = prepare_ok = None
    submitted = skipped = timeout = replaced = parse_failed = successful = pause_cancel = 0
    source = runtime = None
    for line in lines:
        if "segment_submit" in line and "reason=e2e_" in line:
            submitted += 1
        if "segment_skip" in line and "reason=e2e_exact_zero" in line:
            skipped += 1
        timeout += "e2e_timeout" in line
        replaced += "e2e_queue_replaced" in line
        pause_cancel += "e2e_pause_cancel_requested" in line
        parse_failed += "e2e_parse_failed" in line
        successful += "e2e_ok" in line
        if "audio_start_ok" in line:
            source = line.split("audio_start_ok", 1)[1].strip()
        if "e2e_runtime" in line:
            runtime = line.split("e2e_runtime", 1)[1].strip()
        match = PERF.search(line)
        if match:
            performance.append(dict(window=int(match[1]), inference_ms=int(match[2]),
                                     audio_ms=int(match[3]), rtf_milli=int(match[4]),
                                     cpu_process_pct=int(match[5]) if match[5] else None,
                                     gpu_pct=int(match[6]) if match[6] else None))
        match = RESOURCE.search(line)
        if match:
            resources.append(dict(window=int(match[1]), queue_wait_ms=int(match[2]),
                                  pending=int(match[3]), thermal=int(match[4]),
                                  native_heap_bytes=int(match[5])))
        match = PREPARE.search(line)
        if match:
            stamp = datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S.%f")
            if match[2] == "begin":
                prepare_begin = stamp
            else:
                prepare_ok = stamp
    inference = [row["inference_ms"] for row in performance]
    audio = sum(row["audio_ms"] for row in performance)
    waits = [row["queue_wait_ms"] for row in resources]
    heaps = [row["native_heap_bytes"] for row in resources]
    cpu_load = [row["cpu_process_pct"] for row in performance if row["cpu_process_pct"] is not None and row["cpu_process_pct"] >= 0]
    gpu_load = [row["gpu_pct"] for row in performance if row["gpu_pct"] is not None and row["gpu_pct"] >= 0]
    return {
        "file": str(path),
        "source": source,
        "runtime": runtime,
        "prepare_ms": round((prepare_ok - prepare_begin).total_seconds() * 1000) if prepare_begin and prepare_ok else None,
        "e2e_windows_submitted": submitted,
        "e2e_windows_skipped_exact_zero": skipped,
        "e2e_windows_completed": len(performance),
        "e2e_ok": successful,
        "e2e_parse_failed": parse_failed,
        "e2e_timeout": timeout,
        "e2e_queue_replaced_events": replaced,
        "e2e_pause_cancel_requests": pause_cancel,
        "inference_p50_ms": percentile(inference, .50),
        "inference_p95_ms": percentile(inference, .95),
        "inference_rtf": round(sum(inference) / audio, 3) if audio else None,
        "queue_wait_p95_ms": percentile(waits, .95),
        "queue_wait_max_ms": max(waits, default=None),
        "native_heap_peak_mib": round(max(heaps, default=0) / 1024 / 1024, 1),
        "thermal_samples": sorted({row["thermal"] for row in resources}),
        "cpu_process_load_p50_percent": percentile(cpu_load, .50),
        "cpu_process_load_p95_percent": percentile(cpu_load, .95),
        "gpu_load_p50_percent": percentile(gpu_load, .50),
        "gpu_load_p95_percent": percentile(gpu_load, .95),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([analyze(path) for path in args.logs], ensure_ascii=False, indent=2))

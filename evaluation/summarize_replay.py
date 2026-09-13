"""Summarize measured replay times; FIFO latency is a simulation, not a device test."""

import argparse
import json
import math
from pathlib import Path
from statistics import mean


def summarize(path):
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    rows = [row for row in records if row.get("type") == "window" and "inference_ms" in row]
    if not rows:
        raise ValueError(f"No measured windows: {path}")
    times = sorted(row["inference_ms"] for row in rows)
    # Each pass is a fresh simulated capture timeline. Engine initialization and
    # preprocessing are excluded; this is an optimistic unbounded-FIFO estimate.
    finish = 0
    previous = None
    waits, latencies = [], []
    for row in rows:
        key = (row.get("pass", 1), row.get("source"))
        if key != previous or row["index"] == 1:
            finish = 0
        arrival = row["end_ms"]
        wait = max(0, finish - arrival)
        finish = arrival + wait + row["inference_ms"]
        waits.append(wait)
        latencies.append(finish - row["start_ms"])
        previous = key
    return {
        "file": str(path), "windows": len(rows),
        "status_counts": {s: sum(r["status"] == s for r in rows)
                          for s in ("subtitle", "invalid", "no_speech", "error")},
        "mean_inference_ms": round(mean(times)),
        "p95_inference_ms": times[math.ceil(len(times) * .95) - 1],
        "max_rss_mib": max(r.get("peak_rss_mb", 0) for r in rows),
        "max_swap_kib": max(r.get("VmSwap", 0) for r in rows),
        "simulated_fifo_max_wait_ms": max(waits),
        "simulated_fifo_mean_window_start_to_output_ms": round(mean(latencies)),
        "simulation_caveat": "offline timings; excludes initialization/preprocessing/UI; not Android queue behavior",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()
    for log in args.logs:
        print(json.dumps(summarize(log), ensure_ascii=False))

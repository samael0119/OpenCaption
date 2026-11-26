"""Paired local E2B streaming probe. No Android capture or display is involved."""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace

from gemma_replay import LiteRtRuntime, response_text
from v020_stream9 import text_chunk


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation/results"
MODEL = Path(os.environ.get("OPENCAPTION_LITERT_DIR", "/home/hyh/Tools/litert")) / "models/gemma-4-E2B-it.litertlm"
JAVA = Path(os.environ.get("OPENCAPTION_JAVA_HOME", "/home/hyh/Tools/java/eclipse-temurin-jdk17")) / "bin/java"
# A complete second-language label closes the source line. Earlier fragments
# can end halfway through a word and are deliberately ignored.
SOURCE = re.compile(r"^English[ \t]*[:：][ \t]*([^\r\n]+)\r?\n[ \t]*(?:Chinese|中文)[ \t]*[:：]", re.I)


def quantile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    i = int(position)
    return round(values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * (position - i), 1)


def resources():
    group = next(line[3:] for line in Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::"))
    directory = Path("/sys/fs/cgroup") / group.lstrip("/")
    state = {key: (directory / key).read_text().strip() for key in ("memory.max", "memory.swap.max", "memory.peak", "memory.events")}
    if state["memory.max"] == "max" or int(state["memory.max"]) > 6 * 1024**3 or state["memory.swap.max"] != "0":
        raise RuntimeError("Run in a cgroup with MemoryMax ≤ 6 GiB and MemorySwapMax=0")
    return state


def call_bridge(process, operation, *values):
    fields = [operation, *(base64.b64encode(value.encode()).decode() for value in values)]
    process.stdin.write("\t".join(fields) + "\n")
    process.stdin.flush()
    reply = process.stdout.readline()
    if not reply:
        raise RuntimeError("Protocol bridge closed unexpectedly")
    status, *encoded = reply.rstrip("\n").split("\t")
    return status, [base64.b64decode(value).decode() for value in encoded]


def closed_source(raw, allow_repeated_line):
    raw = raw.lstrip()
    match = SOURCE.match(raw)
    if not match and allow_repeated_line:
        leading, separator, rest = raw.partition("\n")
        if not separator:
            return None
        match = SOURCE.match(rest)
        if match and " ".join(leading.split()) != " ".join(match[1].split()):
            return None
    if match and "[none]" not in match[1].lower():
        return " ".join(match[1].split()) or None
    return None


def audit(pair, parse, allow_repeated_line):
    independent = pair["sync"]["raw"]
    stream = pair["stream"]
    chunks = stream["chunks"]
    nonempty = [text for _, text in chunks if text]
    delta = "".join(text for _, text in chunks)
    cumulative = nonempty[-1] if nonempty else ""
    # A synchronous result disambiguates the SDK's chunk semantics off device.
    if independent == delta:
        fold = "delta"
    elif independent == cumulative and all(b.startswith(a) for a, b in zip(nonempty, nonempty[1:])):
        fold = "cumulative"
    else:
        fold = None
    status, fields = parse(independent)
    first = None
    raw = ""
    if fold:
        for at, chunk in chunks:
            raw = raw + chunk if fold == "delta" else chunk or raw
            source = closed_source(raw, allow_repeated_line)
            if source:
                first = at, source
                break
    matches = first is not None and status == "subtitle" and first[1] == fields[0]
    return {
        "status": status,
        "mode": fold,
        "candidate_ms": first[0] if first else None,
        "candidate_matches_final": matches,
        "gain_vs_sync_ms": pair["sync"]["ms"] - first[0] if matches else None,
        "gain_within_stream_ms": stream["ms"] - first[0] if matches else None,
        "stream_source_ready_ms": first[0] if matches else stream["ms"] if status == "subtitle" and fold else None,
    }


def report(pairs, parse, allow_repeated_line):
    rows = [dict(case=pair["case"], group=pair["group"], sync_ms=pair["sync"]["ms"],
                 stream_ms=pair["stream"]["ms"], **audit(pair, parse, allow_repeated_line)) for pair in pairs]
    summaries = {}
    groups = {
        "all": rows,
        "speech": [row for row in rows if row["group"] not in {"music", "known_short_music"}],
        **{name: [row for row in rows if row["group"] == name]
           for name in dict.fromkeys(row["group"] for row in rows)},
    }
    for name, group in groups.items():
        valid = [row for row in group if row["candidate_matches_final"]]
        sources = [row for row in group if row["stream_source_ready_ms"] is not None]
        summaries[name] = {
            "cases": len(group),
            "exact_pairs": sum(row["mode"] is not None for row in group),
            "subtitle": sum(row["status"] == "subtitle" for row in group),
            "early_matching": len(valid),
            "early_wrong": sum(row["candidate_ms"] is not None and not row["candidate_matches_final"] for row in group),
            "sync_p50_p95_ms": [quantile([row["sync_ms"] for row in group], p) for p in (.5, .95)],
            "stream_p50_p95_ms": [quantile([row["stream_ms"] for row in group], p) for p in (.5, .95)],
            "median_gain_vs_sync_ms": quantile([row["gain_vs_sync_ms"] for row in valid], .5),
            "median_gain_within_stream_ms": quantile([row["gain_within_stream_ms"] for row in valid], .5),
            "source_ready_sync_p50_p95_ms": [quantile([row["sync_ms"] for row in sources], p) for p in (.5, .95)],
            "source_ready_stream_p50_p95_ms": [quantile([row["stream_source_ready_ms"] for row in sources], p) for p in (.5, .95)],
        }
    return {"summary": summaries, "cases": rows}


def infer(runtime, system, request, path, mode):
    api = runtime.api
    clock = time.perf_counter
    started = clock()
    with runtime.engine.create_conversation(
        system_message=system,
        thinking_config=api.ThinkingConfig(False, 0),
        sampler_config=api.SamplerConfig(top_k=1, top_p=1.0, temperature=0.0),
        max_output_tokens=128,
    ) as conversation:
        message = api.Contents.of(request, api.Content.AudioFile(str(path)))
        options = {"max_output_tokens": 128, "thinking_config": api.ThinkingConfig(False, 0)}
        if mode == "sync":
            data = {"raw": response_text(conversation.send_message(message, **options))}
        else:
            data = {"chunks": [((clock() - started) * 1000, text_chunk(chunk))
                               for chunk in conversation.send_message_async(message, **options)]}
    return dict(data, ms=(clock() - started) * 1000)


def run(root, bridge):
    checks = resources()
    inputs = RESULTS / "cs-domain-20261020/product_round_v2/audio"
    cases = [(f"{name}-{i}", group, inputs / name / f"{i}.wav", "CS2 broadcast.")
             for name, group in (("clip_interview_niko", "interview"), ("clip", "commentary"))
             for i in (2, 4, 6, 8)]
    cases.extend((name, "music", RESULTS / path, "") for name, path in (
        ("piano", "v020-independent/music/piano_10.wav"),
        ("short-music", "v020-convergence/gain2_audio/known-short-window148.wav"),
    ))
    for _, _, path, _ in cases:
        if not path.is_file():
            raise FileNotFoundError(path)
    with (root / "paired.jsonl").open("x") as log:
        runtime = LiteRtRuntime(SimpleNamespace(
            model=MODEL, threads=4, max_new_tokens=128, hints="", task="bilingual",
            task_profile="baseline", system_profile="minimal", cache_mode="memory",
            speculative_decoding="true", max_context_tokens=768,
        ))
        pairs = []
        try:
            for i, (case, group, path, hints) in enumerate(cases):
                _, prompt = call_bridge(bridge, "prompt", hints)
                if i == 0:
                    infer(runtime, *prompt, path, "sync")  # One warm-up, excluded from comparisons.
                order = ("sync", "stream") if i % 2 == 0 else ("stream", "sync")
                pair = {"case": case, "group": group, "order": order}
                for mode in order:
                    pair[mode] = infer(runtime, *prompt, path, mode)
                log.write(json.dumps(pair, ensure_ascii=False) + "\n")
                log.flush()
                pairs.append(pair)
                print(f"{case} sync={pair['sync']['ms']:.0f} stream={pair['stream']['ms']:.0f}", flush=True)
        finally:
            runtime.close()
    return pairs, {"before": checks, "after": resources()}


def historical_pairs():
    rows = [json.loads(line) for line in (RESULTS / "v020-stream9/requests.jsonl").read_text().splitlines()]
    pairs = {}
    for row in rows:
        if row["type"] != "request":
            continue
        pair = pairs.setdefault(row["case_id"], {"case": str(row["case_id"]), "group": row["group"]})
        if row["mode"] == "sync":
            pair["sync"] = {"raw": row["raw"], "ms": row["service_ms"]}
        else:
            pair["stream"] = {"chunks": [(event["at_ms"], text_chunk(event["chunk"]))
                                         for event in rows if event["type"] == "chunk" and event["index"] == row["index"]],
                              "ms": row["service_ms"]}
    return list(pairs.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-classpath", required=True)
    parser.add_argument("--results", required=True, type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--historical", action="store_true")
    source.add_argument("--paired", type=Path, help="Re-audit a completed paired.jsonl without loading a model")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    with subprocess.Popen([str(JAVA), "-Xmx64m", "-cp", args.bridge_classpath, "E2bP0Bridge"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as bridge:
        try:
            if args.historical:
                pairs, memory = historical_pairs(), None
            elif args.paired:
                pairs, memory = [json.loads(line) for line in args.paired.read_text().splitlines()], None
            else:
                pairs, memory = run(args.results, bridge)
            def parse(raw):
                return call_bridge(bridge, "parse", raw)

            summary = {
                "strict": report(pairs, parse, allow_repeated_line=False),
                "repeated_line": report(pairs, parse, allow_repeated_line=True),
                "resources": memory,
            }
            with (args.results / "summary.json").open("x") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            print(json.dumps({key: summary[key]["summary"] for key in ("strict", "repeated_line")}, ensure_ascii=False, indent=2))
        finally:
            bridge.stdin.close()
    if bridge.returncode != 0:
        raise RuntimeError(f"Protocol bridge exited {bridge.returncode}")


if __name__ == "__main__":
    main()

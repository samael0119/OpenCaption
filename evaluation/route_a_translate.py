"""Stage 2 of Route A: Gemma 4 E2B pure-text translation (NO audio encoder).

Runs strictly serially inside an explicit <=6GiB / swap=0 cgroup via systemd-run.
Translates:
  1. `whisper_la2_v2_roster`: strictly causal 2.5s LocalAgreement-2 streaming clauses (all 4 clips + cs_demo2_18s)
  2. `whisper_base_clean_segs`: Whisper base.en no-prompt natural segments (all 4 clips + cs_demo2_18s; shows clean-ASR ceiling)
  3. `zipformer_int8_hotwords`: cs_demo2_18s 6 clauses (for direct 18s 6-way leaderboard)
"""

import gc
import json
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
import route_a_eval as ra
from gemma_replay import LiteRtRuntime, response_text


def check_cgroup():
    line = next(l for l in Path("/proc/self/cgroup").read_text().splitlines() if l.startswith("0::"))
    cg = Path("/sys/fs/cgroup") / line.split("::", 1)[1].lstrip("/")
    d = {n: (cg / n).read_text().strip() for n in ["memory.max", "memory.swap.max", "memory.peak", "memory.events"]}
    if d["memory.max"] == "max" or int(d["memory.max"]) > 6 * 1024**3 or d["memory.swap.max"] != "0":
        raise RuntimeError(f"Explicit cgroup <=6GiB & swap=0 required, got {d}")
    return d


def translate_clause(runtime, context, prev_en, cur_en):
    api = runtime.api
    prev_part = f"\nPrev: {' '.join(prev_en.split()[-18:])}" if prev_en else ""
    prompt = f"Context: {context}{prev_part}\nCurrent: {cur_en}"
    t0 = time.perf_counter()
    with runtime.engine.create_conversation(
        system_message=ra.SYSTEM_TEXT_TRANSLATE,
        thinking_config=api.ThinkingConfig(False, 0),
        sampler_config=api.SamplerConfig(top_k=1, top_p=1.0, temperature=0.0),
        max_output_tokens=128,
    ) as conv:
        raw = response_text(
            conv.send_message(
                api.Contents.of(prompt),
                max_output_tokens=128,
                thinking_config=api.ThinkingConfig(False, 0),
            )
        )
    tr_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    zh = " ".join(raw.strip().splitlines()).strip()
    return zh, raw, tr_ms


def main():
    limits_before = check_cgroup()
    la2 = json.loads((ra.OUT / "whisper_la2_v2_results.json").read_text())
    wbase = json.loads((ra.OUT / "whisper_base_results.json").read_text())["no_prompt"]
    zipf = json.loads((ra.OUT / "asr_results.json").read_text())["variants"]["int8_hotwords"]["clips"]

    out_jsonl = ra.OUT / "route_a_translations.jsonl"
    summary_json = ra.OUT / "route_a_summary.json"
    if out_jsonl.exists():
        out_jsonl.unlink()

    t_load0 = time.perf_counter()
    runtime = LiteRtRuntime(
        SimpleNamespace(
            model=ra.MODEL,
            threads=4,
            max_new_tokens=128,
            hints="",
            task="bilingual",
            task_profile="baseline",
            system_profile="minimal",
            cache_mode="disk",
            speculative_decoding="true",
            max_context_tokens=768,
        )
    )
    load_ms = round((time.perf_counter() - t_load0) * 1000.0, 1)
    _, _, warmup_ms = translate_clause(runtime, "CS2 broadcast.", "", "hello everyone welcome to the match")
    print(f"E2B loaded={load_ms:.0f}ms warmup={warmup_ms:.0f}ms")

    arm_stats = {}

    def run_arm(arm_name, clip_clause_map):
        lats = []
        e2e_est = []
        with out_jsonl.open("a") as f:
            for src_id, clauses in clip_clause_map.items():
                ctx = ra.PREMATCH[src_id]["context"]
                prev_en = ""
                print(f"\n[{arm_name}] {src_id}: {len(clauses)} clauses")
                for c in clauses:
                    zh, raw, tr_ms = translate_clause(runtime, ctx, prev_en, c["text"])
                    # Clause-end to Chinese latency = ASR step time + text translation time
                    asr_ms = c.get("asr_step_ms", c.get("asr_decode_ms", 0.0))
                    row = {
                        "arm": arm_name,
                        "source_id": src_id,
                        "clause_id": c["clause_id"],
                        "start_ms": c["start_ms"],
                        "end_ms": c["end_ms"],
                        "english_asr": c["text"],
                        "chinese": zh,
                        "asr_ms": asr_ms,
                        "translate_ms": tr_ms,
                    }
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    if src_id != "cs_demo2_18s":
                        lats.append(tr_ms)
                        e2e_est.append(round(asr_ms + tr_ms, 1))
                    prev_en = c["text"]
                    print(f"  [{c['start_ms']/1000:5.1f}-{c['end_ms']/1000:5.1f}s {tr_ms:5.0f}ms] {c['text']} => {zh}")
        arm_stats[arm_name] = {
            "clauses_4clips": len(lats),
            "translate_p50_ms": ra.quantile(lats, 0.5),
            "translate_p95_ms": ra.quantile(lats, 0.95),
            "translate_mean_ms": round(statistics.mean(lats), 1) if lats else None,
            "asr_plus_tr_p50_ms": ra.quantile(e2e_est, 0.5),
            "asr_plus_tr_p95_ms": ra.quantile(e2e_est, 0.95),
        }

    try:
        # Arm 1: Strictly causal LocalAgreement-2 Whisper base.en + roster prompt
        la2_map = {
            src: la2["clips"][src]["streamed"]["clauses"]
            for src in ["cs_demo2_18s", "clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]
        }
        run_arm("whisper_la2_roster", la2_map)

        # Arm 2: Clean Whisper base.en no-prompt natural segments (ASR upper-bound reference for base.en)
        clean_map = {}
        for src in ["cs_demo2_18s", "clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]:
            segs = wbase[src]["segments"]
            clauses = []
            for idx, s in enumerate(segs, 1):
                txt = " ".join(s.get("text", "").split())
                if not txt:
                    continue
                clauses.append({
                    "clause_id": idx,
                    "start_ms": s["offsets"]["from"],
                    "end_ms": s["offsets"]["to"],
                    "asr_step_ms": round(wbase[src]["rtf"] * max(1000, s["offsets"]["to"] - s["offsets"]["from"]), 1),
                    "text": txt,
                })
            clean_map[src] = clauses
        run_arm("whisper_base_clean_segs", clean_map)

        # Arm 3: Zipformer int8 + hotwords on cs_demo2_18s (for complete 18s comparison)
        run_arm("zipformer_int8_hotwords_18s", {"cs_demo2_18s": zipf["cs_demo2_18s"]["streamed"]["clauses"]})
    finally:
        runtime.close()
        gc.collect()

    limits_after = check_cgroup()
    summary = {
        "load_ms": load_ms,
        "warmup_ms": warmup_ms,
        "limits_before": limits_before,
        "limits_after": limits_after,
        "arms": arm_stats,
    }
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("\nFINAL SUMMARY:", json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

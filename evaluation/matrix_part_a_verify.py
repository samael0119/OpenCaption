"""Part A targeted verification (2026-11-26):
  1. Parakeet-TDT-0.6B-v3-int8 + Causal AGC (verify low-volume interview recovery)
  2. HY-MT1.5-1.8B with Dynamic Term Filtering (only inject terms present in Current + compact roster)
     across whisper_large_v3_turbo_q5, whisper_small_q5, and parakeet_agc outputs.

Strictly serial inside explicit <=6GiB / swap=0 cgroup (Parakeet freed before llama-server starts).
"""

import gc
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
import route_a_eval as ra
import matrix_translate as mt

OUT = ROOT / "evaluation/results/matrix-20261126"
MODELS_DIR = Path.home() / "Tools/litert/models/matrix-20261126"
LLAMA_SERVER = OUT / "llama-build/bin/llama-server"
PORT = 18090
BASE_URL = f"http://127.0.0.1:{PORT}"

# Dynamic CS2 term rules: (regex_in_current, source_term, target_zh)
DYNAMIC_TERMS = [
    (r"\bscout\b", "scout", "鸟狙"),
    (r"\bhead\s?shot\b", "headshot", "爆头"),
    (r"\btrade\b", "trade", "补枪"),
    (r"\bone[- ]round game\b", "one-round game", "分差缩到一分"),
    (r"\bclaw\s?back\b", "claw back", "扳回"),
    (r"\bnumbers on\b", "numbers on", "人数优势"),
    (r"\bup to bat\b", "up to bat", "轮到上场"),
    (r"\bbomb\s?site\b|\bsite\b", "site", "包点"),
    (r"\bbomb\b", "bomb", "雷包"),
    (r"\bhigh comms?\b", "high comms", "队内沟通充分"),
    (r"\bcomms?\b", "comms", "队内沟通"),
    (r"\bcat\b", "cat", "小道"),
    (r"\bpalace\b", "palace", "A二楼"),
    (r"\bvent\b", "vent", "管道"),
    (r"\blobby\b", "lobby", "大厅"),
    (r"\bmajor\b", "Major", "Major"),
]


def build_dynamic_hy_mt_prompt(src_id, prev_en, cur_en):
    """Official HY-MT1.5 template with STRICT dynamic term filtering (zero unused glossary leakage)."""
    low = cur_en.lower()
    matched_glossary = []
    # 1. Include only entities whose spelling or obvious stem appears in Current
    for ent in mt.MATCH_ENTITIES[src_id]:
        el = ent.lower()
        # Match exact word or common ASR spelling stem (e.g. niko/nico, yuurih/yuri, sh1ro/shiro, molodoy/molodoi)
        stems = {el}
        if el == "niko":
            stems.add("nico")
        elif el == "yuurih":
            stems.update({"yuri", "yurih"})
        elif el == "sh1ro":
            stems.update({"shiro", "shero"})
        elif el == "molodoy":
            stems.update({"molodoi", "monoloy"})
        elif el == "b1t":
            stems.add("bit")
        elif el == "w0nderful":
            stems.add("wonderful")
        elif el == "jcobbb":
            stems.update({"jcobb", "jacob"})
        elif el == "teses":
            stems.update({"tesis", "tes"})
        elif el == "m0nesy":
            stems.add("monesy")
        elif el == "zont1x":
            stems.update({"zontix", "zontics"})
        elif el == "xertion":
            stems.update({"zertion", "zershin", "zerchin"})
        elif el == "makazze":
            stems.add("makaze")
        if any(re.search(rf"\b{re.escape(s)}\b", low) for s in stems):
            matched_glossary.append(f"{ent} 翻译成 {ent}")

    # 2. Include ONLY CS2 domain terms that actually match Current
    for pat, src_term, tgt_zh in DYNAMIC_TERMS:
        if re.search(pat, low):
            matched_glossary.append(f"{src_term} 翻译成 {tgt_zh}")

    parts = []
    if prev_en:
        parts.append(f"上文：{' '.join(prev_en.split()[-14:])}")
    if matched_glossary:
        parts.append("参考下面的翻译：\n" + "\n".join(matched_glossary))
    if parts:
        user_msg = (
            "\n".join(parts)
            + "\n参考上面的信息，把下面的文本翻译成简体中文，注意不需要翻译上文，也不要额外解释：\n"
            + cur_en
        )
    else:
        user_msg = f"将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n{cur_en}"
    return [{"role": "user", "content": user_msg}], len(matched_glossary)


def run_parakeet_agc(segs_by_clip, ref_en):
    sys.path.insert(0, str(ra.NUMPY_DEPS))
    sys.path.insert(0, str(ra.SHERPA_DEPS))
    import numpy as np
    import sherpa_onnx

    print("\n=== Step A1: Parakeet-TDT-0.6B-v3-int8 + Causal AGC ===", flush=True)
    pdir = MODELS_DIR / "asr/parakeet-v3-int8"
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(pdir / "encoder.int8.onnx"),
        decoder=str(pdir / "decoder.int8.onnx"),
        joiner=str(pdir / "joiner.int8.onnx"),
        tokens=str(pdir / "tokens.txt"),
        num_threads=4, sample_rate=16000, feature_dim=80,
        decoding_method="greedy_search", provider="cpu", model_type="nemo_transducer",
    )

    pcms = {
        src: (ra.AUDIO_ROOT / src / "source.pcm").read_bytes()
        for src in ["clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]
    }
    with wave.open(str(ra.DEMO2_18S), "rb") as wf:
        pcms["cs_demo2_18s"] = wf.readframes(wf.getnframes())

    clips_out = {}
    tot_ref = tot_err = 0
    for src_id, pcm_bytes in pcms.items():
        raw_s = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        # Causal AGC boosting weak/interview audio smoothly toward target_rms=0.08
        agc_s = ra.causal_agc(raw_s, chunk_size=2560, target_rms=0.08, trigger_rms=0.04, floor_rms=1e-4, max_gain=15.0)
        segs = segs_by_clip[src_id]
        clauses = []
        times = []
        for seg in segs:
            chunk = agc_s[seg["start_sample"] : seg["end_sample"]]
            t0 = time.perf_counter()
            s = rec.create_stream()
            s.accept_waveform(16000, chunk)
            rec.decode_stream(s)
            txt = " ".join(s.result.text.split())
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            times.append(ms)
            clauses.append({
                "clause_id": seg["seg_id"],
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
                "asr_ms": ms,
                "text": txt,
            })
        full = " ".join(c["text"] for c in clauses if c["text"])
        rw = ra.norm_words(ref_en[src_id])
        hw = ra.norm_words(full)
        err = ra.edit_ops(rw, hw)
        wer = round(err / len(rw), 4)
        empty_segs = sum(not c["text"] for c in clauses)
        if src_id in ("clip", "clip_match_demo2", "clip_match_demo3"):
            tot_ref += len(rw)
            tot_err += err
        print(
            f"  {src_id:20s}: p50={ra.quantile(times,0.5):5.0f}ms empty={empty_segs:2d}/{len(clauses):2d} "
            f"ratio={len(hw)/len(rw):.2f} WER={wer*100:.1f}%",
            flush=True,
        )
        clips_out[src_id] = {
            "wer_causal": wer,
            "empty_segs": empty_segs,
            "chunk_p50_ms": ra.quantile(times, 0.5),
            "clauses": clauses,
            "full_text": full,
        }

    del rec
    gc.collect()
    print(
        f"  => [parakeet_agc] Match WER={tot_err/tot_ref*100:.1f}% (was 29.6%) | "
        f"Interview WER={clips_out['clip_interview_niko']['wer_causal']*100:.1f}% (was 40.9%)",
        flush=True,
    )
    return {"weighted_match_wer_causal": round(tot_err / tot_ref, 4), "clips": clips_out}


def call_chat(messages):
    payload = {
        "messages": messages,
        "temperature": 0.0,
        "top_k": 1,
        "max_tokens": 128,
        "stream": False,
        "cache_prompt": True,
    }
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    wall_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    zh = " ".join((data["choices"][0]["message"].get("content") or "").strip().splitlines()).strip()
    timings = data.get("timings", {})
    return zh, wall_ms, round(timings.get("predicted_per_second", 0.0), 1)


def main():
    limits_before = mt.check_cgroup()
    asr_all = json.loads((OUT / "matrix_asr_results.json").read_text())
    ref_data = json.loads(ra.REF_PATH.read_text())
    ref_en = {
        src: " ".join(u["reference_en"] for u in ref_data["units"] if u["source_id"] == src)
        for src in ["clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]
    }
    ref_en["cs_demo2_18s"] = (
        "molodoy provides the opening, now FURIA need to find the finish, convert upon this opening. "
        "On their map, pick of Mirage to start us off. There's a claw back from NiKo just on the very edge of the smoke. "
        "The oscillation gave him vision. TeSeS is up to bat."
    )

    # Step A1: Parakeet + AGC (freed before starting llama-server!)
    parakeet_agc = run_parakeet_agc(asr_all["segmentation"], ref_en)

    # Step A2: HY-MT1.5-1.8B with Dynamic Term Filtering
    print("\n=== Step A2: HY-MT1.5-1.8B with Dynamic Term Filtering ===", flush=True)
    log_file = OUT / "server_hy_mt_dynamic.log"
    cmd = [
        str(LLAMA_SERVER),
        "-m", str(MODELS_DIR / "mt/HY-MT1.5-1.8B-Q4_K_M.gguf"),
        "--host", "127.0.0.1", "--port", str(PORT),
        "-t", "4", "-c", "1024", "-np", "1", "--cache-ram", "256", "--no-webui",
    ]
    with log_file.open("w") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)

    out_jsonl = OUT / "part_a_dynamic_translations.jsonl"
    if out_jsonl.exists():
        out_jsonl.unlink()
    cell_stats = {}
    try:
        # Wait health
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 60:
            try:
                with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.2)
        msgs, _ = build_dynamic_hy_mt_prompt("clip", "", "hello everyone")
        _, wms, wtps = call_chat(msgs)
        print(f"  HY-MT1.5 dynamic server ready, warmup={wms:.0f}ms ({wtps} tok/s)", flush=True)

        sources = {
            "whisper_large_v3_turbo_q5": asr_all["models"]["whisper_large_v3_turbo_q5"]["clips"],
            "whisper_small_q5": asr_all["models"]["whisper_small_q5"]["clips"],
            "parakeet_tdt_v3_agc": parakeet_agc["clips"],
        }

        for asr_name, clips in sources.items():
            walls = []
            e2es = []
            gloss_counts = []
            with out_jsonl.open("a") as f:
                for src_id in ["cs_demo2_18s", "clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]:
                    prev_en = ""
                    for c in clips[src_id]["clauses"]:
                        en_txt = c["text"].strip()
                        if not en_txt:
                            zh, wms, tps, gn = "", 0.0, 0.0, 0
                        else:
                            msgs, gn = build_dynamic_hy_mt_prompt(src_id, prev_en, en_txt)
                            zh, wms, tps = call_chat(msgs)
                            prev_en = en_txt
                        row = {
                            "cell": f"{asr_name}__hy_mt_dynamic",
                            "source_id": src_id,
                            "clause_id": c["clause_id"],
                            "start_ms": c["start_ms"],
                            "end_ms": c["end_ms"],
                            "english_asr": en_txt,
                            "chinese": zh,
                            "glossary_terms_used": gn,
                            "asr_ms": c["asr_ms"],
                            "mt_wall_ms": wms,
                            "mt_tps": tps,
                        }
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        if src_id != "cs_demo2_18s" and en_txt:
                            walls.append(wms)
                            e2es.append(round(c["asr_ms"] + wms, 1))
                            gloss_counts.append(gn)
                f.flush()
            cell_stats[asr_name] = {
                "mt_p50_ms": ra.quantile(walls, 0.5),
                "mt_p95_ms": ra.quantile(walls, 0.95),
                "asr_plus_mt_p50_ms": ra.quantile(e2es, 0.5),
                "avg_glossary_terms": round(statistics.mean(gloss_counts), 2) if gloss_counts else 0.0,
            }
            print(
                f"  [{asr_name}__hy_mt_dynamic]: mt_p50={cell_stats[asr_name]['mt_p50_ms']}ms "
                f"(was ~1050ms!) mt_p95={cell_stats[asr_name]['mt_p95_ms']}ms "
                f"asr+mt_p50={cell_stats[asr_name]['asr_plus_mt_p50_ms']}ms "
                f"avg_terms={cell_stats[asr_name]['avg_glossary_terms']}",
                flush=True,
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    res = {
        "parakeet_agc": parakeet_agc,
        "hy_mt_dynamic_stats": cell_stats,
        "limits_after": mt.check_cgroup(),
    }
    (OUT / "part_a_verify_summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    print("\nPART A VERIFICATION COMPLETE!", flush=True)


if __name__ == "__main__":
    main()

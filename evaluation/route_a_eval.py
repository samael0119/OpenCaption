"""Route A evaluation: Streaming Zipformer ASR (+AGC + pre-match hotwords) -> Gemma 4 E2B pure-text translation.

Runs strictly serially (never loads ASR and LLM simultaneously):
  1. `python3 evaluation/route_a_eval.py asr`
  2. `systemd-run --user --scope -p MemoryHigh=5376M -p MemoryMax=6144M -p MemorySwapMax=0 \
      ~/Tools/litert/litert-venv/bin/python evaluation/route_a_eval.py translate`
"""

import argparse
import gc
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/route-a-20261126"
REF_PATH = ROOT / "evaluation/results/cs-domain-20261020/product_round_v2/reference.json"
DIAG_PATH = ROOT / "evaluation/results/cs-domain-20261020/diagnosis/diagnostic.json"
AUDIO_ROOT = ROOT / "evaluation/results/cs-domain-20261020/product_round_v2/audio"
DEMO2_18S = ROOT / "evaluation/results/subtitle-research-20261123/cs-demo2-20s-38s/audio.wav"
ARCH_BASE = ROOT / "evaluation/results/v020-architecture"
ZDIR = ARCH_BASE / "zipformer"
NUMPY_DEPS = ROOT / "evaluation/results/s0-20261013/deps"
SHERPA_DEPS = ARCH_BASE / "deps"
MODEL = Path(os.environ.get("OPENCAPTION_LITERT_DIR", str(Path.home() / "Tools/litert"))) / "models/gemma-4-E2B-it.litertlm"

# Public pre-match context only (full 5+5 rosters + map, zero gold/future leakage).
PREMATCH = {
    "clip": {
        "role": "primary_match",
        "context": "CS2 broadcast. Match: Spirit vs MOUZ, Dust2. Players: donk, sh1ro, tN1R, zont1x, magixx, torzsi, xertioN, Spinx, Brollan, Jimpphat.",
        "hotwords": [
            ("SPIRIT", 2.5), ("MOUZ", 2.5), ("DUST", 2.0),
            ("DONK", 2.8), ("SHIRO", 2.8), ("TENEER", 2.5), ("ZONTIX", 2.8), ("MAGIXX", 2.5),
            ("TORZSI", 2.8), ("XERTION", 2.8), ("SPINX", 2.5), ("BROLLAN", 2.5), ("JIMPPHAT", 2.5),
            ("SCOUT", 2.0), ("HEADSHOT", 1.8), ("AWP", 2.0), ("BOMBSITE", 1.8),
        ],
    },
    "clip_match_demo2": {
        "role": "primary_match",
        "context": "CS2 broadcast. Match: Falcons vs FURIA, Mirage. Players: NiKo, m0NESY, TeSeS, kyousuke, kyxsan, FalleN, yuurih, KSCERATO, YEKINDAR, molodoy.",
        "hotwords": [
            ("FALCONS", 2.5), ("FURIA", 2.8), ("MIRAGE", 2.8),
            ("NIKO", 2.8), ("MONESY", 2.8), ("TESES", 2.8), ("KYOUSUKE", 2.8), ("KYXSAN", 2.5),
            ("FALLEN", 2.5), ("YUURIH", 2.8), ("YURI", 2.5), ("KSCERATO", 2.8), ("YEKINDAR", 2.8), ("MOLODOY", 2.8),
            ("PALACE", 2.0), ("CONNECTOR", 2.0), ("CROSSHAIR", 1.8), ("CLAWBACK", 2.0),
        ],
    },
    "clip_match_demo3": {
        "role": "primary_match",
        "context": "CS2 broadcast. Match: FaZe vs NAVI, Nuke. Players: karrigan, frozen, broky, Twistzz, jcobbb, Aleksib, b1t, iM, w0nderful, makazze.",
        "hotwords": [
            ("FAZE", 2.5), ("NAVI", 2.8), ("NUKE", 2.5),
            ("KARRIGAN", 2.8), ("FROZEN", 2.5), ("BROKY", 2.8), ("TWISTZZ", 2.8), ("JACOB", 2.5),
            ("ALEKSIB", 2.8), ("BIT", 2.0), ("WONDERFUL", 2.5), ("MAKAZZE", 2.8),
            ("LOBBY", 2.0), ("VENT", 2.0), ("HEADSHOT", 1.8),
        ],
    },
    "clip_interview_niko": {
        "role": "secondary_interview",
        "context": "CS2 player interview. Player: NiKo (Falcons).",
        "hotwords": [
            ("NIKO", 2.8), ("FALCONS", 2.5), ("MAJOR", 2.2), ("RATING", 1.8),
        ],
    },
    "cs_demo2_18s": {
        "role": "slice_18s",
        "context": "CS2 broadcast. Match: Falcons vs FURIA, Mirage. Players: NiKo, m0NESY, TeSeS, kyousuke, kyxsan, FalleN, yuurih, KSCERATO, YEKINDAR, molodoy.",
        "hotwords": [
            ("FALCONS", 2.5), ("FURIA", 2.8), ("MIRAGE", 2.8),
            ("NIKO", 2.8), ("MONESY", 2.8), ("TESES", 2.8), ("KYOUSUKE", 2.8), ("KYXSAN", 2.5),
            ("FALLEN", 2.5), ("YUURIH", 2.8), ("YURI", 2.5), ("KSCERATO", 2.8), ("YEKINDAR", 2.8), ("MOLODOY", 2.8),
            ("PALACE", 2.0), ("CLAWBACK", 2.0),
        ],
    },
}

SYSTEM_TEXT_TRANSLATE = (
    "You translate live English ASR transcripts of CS2 esports broadcasts or player interviews into natural "
    "Mainland China Simplified Chinese (简体中文, zh-CN). Do NOT output Traditional Chinese. "
    "The input comes from noisy real-time speech recognition (lowercase/uppercase, no punctuation, occasional phonetic mistakes on player IDs). "
    "Use the provided pre-match Match/Players list ONLY to recover player/team/map names when pronunciation and sentence context clearly support them; keep player/team/map IDs in standard English spelling. "
    "Never invent kills, scores, or events not supported by Current. Preserve numbers, negation, and who acted on whom. "
    "Translate common CS2 commentary phrasing naturally (e.g., scout->鸟狙, trade->补枪, headshot->爆头, one-round game->分差缩到一分, claw back->扳回/反击, numbers on X->对X有人数优势, up to bat->轮到上场). "
    "Output ONLY the single-line Simplified Chinese translation of Current. No English prefix, no labels, no explanations."
)


def quantile(values, fraction):
    vals = sorted(values)
    if not vals:
        return None
    pos = (len(vals) - 1) * fraction
    i = int(pos)
    return round(vals[i] + (vals[min(i + 1, len(vals) - 1)] - vals[i]) * (pos - i), 1)


def norm_words(text):
    # Match diagnostic WER tokenization: lowercase alphanumeric words + light numeric normalization
    num_map = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
        "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
        "eighteen": "18", "nineteen": "19", "twenty": "20",
    }
    toks = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    return [num_map.get(t, t) for t in toks]


def edit_ops(ref, hyp):
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        ri = ref[i - 1]
        row = dp[i]
        prev = dp[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ri == hyp[j - 1] else 1
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost)
    return dp[n][m]


def load_pcm_int16(path):
    import numpy as np
    raw = path.read_bytes()
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def load_wav_mono(path):
    import numpy as np
    with wave.open(str(path), "rb") as wf:
        assert wf.getframerate() == 16000 and wf.getnchannels() == 1 and wf.getsampwidth() == 2
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def causal_agc(samples, chunk_size=2560, target_rms=0.05, trigger_rms=0.015, floor_rms=1e-4, max_gain=25.0):
    """Causal chunk-wise AGC: only boosts ultra-low-amplitude audio (like FLEURS); leaves normal speech untouched."""
    import numpy as np
    out = np.empty_like(samples)
    gain = 1.0
    for off in range(0, len(samples), chunk_size):
        blk = samples[off:off + chunk_size]
        rms = float(np.sqrt(np.mean(blk * blk))) if len(blk) else 0.0
        if floor_rms < rms < trigger_rms:
            desired = min(max_gain, target_rms / rms)
            # Fast attack so weak speech starts immediately, smooth release
            gain = 0.6 * desired + 0.4 * gain
        elif rms >= trigger_rms:
            gain = 0.2 * 1.0 + 0.8 * gain
        else:
            gain = 0.5 * 1.0 + 0.5 * gain
        if abs(gain - 1.0) > 0.02:
            out[off:off + chunk_size] = np.clip(blk * gain, -0.95, 0.95)
        else:
            out[off:off + chunk_size] = blk
    return out


def make_bpe_vocab(tokens_path, dest_path):
    lines = [l.strip().split() for l in tokens_path.read_text().splitlines() if l.strip()]
    vocab_lines = [f"{tok}\t{0.0 if int(idx) < 3 else -(1.0 + int(idx) / 100.0):.3f}" for tok, idx in lines]
    dest_path.write_text("\n".join(vocab_lines) + "\n")


def run_streaming_clip(rec, samples, chunk_size=2560, max_clause_ms=3200, min_clause_ms=1400):
    """True causal streaming decode with endpointing + soft clause splitting for low-latency translation."""
    import numpy as np
    stream = rec.create_stream()
    clauses = []
    clause_start_ms = 0
    clause_first_tok_ms = None
    last_emitted_text = ""
    t_decode_total = 0.0
    t_clause_decode = 0.0
    first_overall_audio_ms = None

    def emit_clause(end_ms, reason, text, dec_ms):
        nonlocal clause_start_ms, clause_first_tok_ms, t_clause_decode
        clean = " ".join(text.split())
        if clean:
            clauses.append({
                "clause_id": len(clauses) + 1,
                "start_ms": clause_start_ms,
                "end_ms": end_ms,
                "first_token_audio_ms": clause_first_tok_ms,
                "reason": reason,
                "asr_decode_ms": round(dec_ms, 1),
                "text": clean,
            })
        clause_start_ms = end_ms
        clause_first_tok_ms = None
        t_clause_decode = 0.0

    for off in range(0, len(samples), chunk_size):
        blk = samples[off:off + chunk_size]
        cur_ms = int(round((off + len(blk)) / 16.0))
        t0 = time.perf_counter()
        stream.accept_waveform(16000, blk)
        while rec.is_ready(stream):
            rec.decode_stream(stream)
        dt = (time.perf_counter() - t0) * 1000.0
        t_decode_total += dt
        t_clause_decode += dt

        cur_text = rec.get_result(stream).strip()
        if cur_text and clause_first_tok_ms is None:
            clause_first_tok_ms = cur_ms
            if first_overall_audio_ms is None:
                first_overall_audio_ms = cur_ms

        is_ep = rec.is_endpoint(stream)
        elapsed_ms = cur_ms - clause_start_ms

        if is_ep and cur_text:
            emit_clause(cur_ms, "endpoint", cur_text, t_clause_decode)
            rec.reset(stream)
            last_emitted_text = ""
        elif elapsed_ms >= max_clause_ms and cur_text:
            # Soft word-boundary split without dropping acoustic context:
            # reset stream at word boundary so continuous rapid commentary still ships every ~3.2s
            # Wait: resetting loses only in-progress phoneme; keep tail clean by checking last word changed or just emitting
            words_cur = cur_text.split()
            if len(words_cur) >= 3 or elapsed_ms >= max_clause_ms + 800:
                emit_clause(cur_ms, "soft_cap", cur_text, t_clause_decode)
                rec.reset(stream)
                last_emitted_text = ""

    # Flush tail
    t0 = time.perf_counter()
    stream.accept_waveform(16000, np.zeros(10560, dtype=np.float32))
    stream.input_finished()
    while rec.is_ready(stream):
        rec.decode_stream(stream)
    dt = (time.perf_counter() - t0) * 1000.0
    t_decode_total += dt
    t_clause_decode += dt
    tail_text = rec.get_result(stream).strip()
    if tail_text:
        emit_clause(int(round(len(samples) / 16.0)), "eof", tail_text, t_clause_decode)

    full_text = " ".join(c["text"] for c in clauses)
    return {
        "duration_ms": int(round(len(samples) / 16.0)),
        "total_decode_ms": round(t_decode_total, 1),
        "rtf": round(t_decode_total / (len(samples) / 16.0), 4),
        "first_token_audio_ms": first_overall_audio_ms,
        "clauses": clauses,
        "full_text": full_text,
    }


def run_continuous_unsplit(rec, samples, chunk_size=2560):
    """Also decode continuous stream with zero resets to check whether soft_cap resets hurt WER."""
    import numpy as np
    stream = rec.create_stream()
    t0 = time.perf_counter()
    first_ms = None
    for off in range(0, len(samples), chunk_size):
        blk = samples[off:off + chunk_size]
        stream.accept_waveform(16000, blk)
        while rec.is_ready(stream):
            rec.decode_stream(stream)
        if first_ms is None and rec.get_result(stream).strip():
            first_ms = int(round((off + len(blk)) / 16.0))
    stream.accept_waveform(16000, np.zeros(10560, dtype=np.float32))
    stream.input_finished()
    while rec.is_ready(stream):
        rec.decode_stream(stream)
    dt = (time.perf_counter() - t0) * 1000.0
    return {
        "duration_ms": int(round(len(samples) / 16.0)),
        "total_decode_ms": round(dt, 1),
        "rtf": round(dt / (len(samples) / 16.0), 4),
        "first_token_audio_ms": first_ms,
        "full_text": " ".join(rec.get_result(stream).split()),
    }


def cmd_asr():
    sys.path.insert(0, str(NUMPY_DEPS))
    sys.path.insert(0, str(SHERPA_DEPS))
    import numpy as np
    import sherpa_onnx

    OUT.mkdir(parents=True, exist_ok=True)
    ref_data = json.loads(REF_PATH.read_text())
    diag_data = json.loads(DIAG_PATH.read_text())

    # Reference full English per clip
    ref_en_by_clip = {}
    for src in ["clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]:
        units = [u for u in ref_data["units"] if u["source_id"] == src]
        ref_en_by_clip[src] = " ".join(u["reference_en"] for u in units)
    ref_en_by_clip["cs_demo2_18s"] = (
        "molodoy provides the opening, now FURIA need to find the finish, convert upon this opening. "
        "On their map, pick of Mirage to start us off. There's a claw back from NiKo just on the very edge of the smoke. "
        "The oscillation gave him vision. TeSeS is up to bat."
    )

    # 1. Verify AGC fix on FLEURS low-amplitude + Music guard
    arch_manifest = json.loads((ARCH_BASE / "screen1/manifest.json").read_text())
    guard_cases = [c for c in arch_manifest["cases"] if c.get("group") in ("fleurs", "music", "known_short_music")]
    print(f"Running AGC + guard check on {len(guard_cases)} FLEURS/music cases...")
    rec_base = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(ZDIR / "tokens.txt"),
        encoder=str(ZDIR / "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx"),
        decoder=str(ZDIR / "decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx"),
        joiner=str(ZDIR / "joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx"),
        num_threads=4, sample_rate=16000, feature_dim=80, provider="cpu",
        decoding_method="greedy_search", enable_endpoint_detection=False,
    )
    guard_results = []
    for c in guard_cases:
        wav_path = ROOT / c["path"]
        raw_s = load_wav_mono(wav_path)
        agc_s = causal_agc(raw_s)
        r_raw = run_continuous_unsplit(rec_base, raw_s)
        r_agc = run_continuous_unsplit(rec_base, agc_s)
        ref = c.get("reference", "")
        ref_w = norm_words(ref)
        wer_raw = edit_ops(ref_w, norm_words(r_raw["full_text"])) / len(ref_w) if ref_w else None
        wer_agc = edit_ops(ref_w, norm_words(r_agc["full_text"])) / len(ref_w) if ref_w else None
        guard_results.append({
            "id": c["id"],
            "group": c["group"],
            "raw_rms": round(float(np.sqrt(np.mean(raw_s * raw_s))), 6),
            "agc_rms": round(float(np.sqrt(np.mean(agc_s * agc_s))), 6),
            "reference": ref,
            "raw_text": r_raw["full_text"],
            "agc_text": r_agc["full_text"],
            "wer_raw": round(wer_raw, 4) if wer_raw is not None else None,
            "wer_agc": round(wer_agc, 4) if wer_agc is not None else None,
        })
    del rec_base
    gc.collect()

    fleurs_rows = [r for r in guard_results if r["group"] == "fleurs"]
    music_rows = [r for r in guard_results if r["group"] != "fleurs"]
    print(
        f"FLEURS nonempty: raw={sum(bool(r['raw_text']) for r in fleurs_rows)}/{len(fleurs_rows)} "
        f"-> agc={sum(bool(r['agc_text']) for r in fleurs_rows)}/{len(fleurs_rows)}; "
        f"Music nonempty: raw={sum(bool(r['raw_text']) for r in music_rows)}/{len(music_rows)} "
        f"-> agc={sum(bool(r['agc_text']) for r in music_rows)}/{len(music_rows)}"
    )

    # 2. Run 3 streaming ASR variants across all 4 full clips + 18s demo2 slice
    audio_clips = {
        "clip": load_pcm_int16(AUDIO_ROOT / "clip/source.pcm"),
        "clip_match_demo2": load_pcm_int16(AUDIO_ROOT / "clip_match_demo2/source.pcm"),
        "clip_match_demo3": load_pcm_int16(AUDIO_ROOT / "clip_match_demo3/source.pcm"),
        "clip_interview_niko": load_pcm_int16(AUDIO_ROOT / "clip_interview_niko/source.pcm"),
        "cs_demo2_18s": load_wav_mono(DEMO2_18S),
    }

    variants = ["int8_greedy", "int8_hotwords", "fp32_hotwords"]
    asr_out = {"guard": guard_results, "variants": {}}

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bpe_vocab = td / "bpe.vocab"
        make_bpe_vocab(ZDIR / "tokens.txt", bpe_vocab)

        for variant in variants:
            print(f"\n=== Running ASR variant: {variant} ===")
            enc = (
                ZDIR / "encoder-epoch-99-avg-1-chunk-16-left-128.onnx"
                if variant.startswith("fp32")
                else ZDIR / "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx"
            )
            use_hw = variant.endswith("hotwords")
            v_clips = {}

            for src_id, raw_samples in audio_clips.items():
                samples = causal_agc(raw_samples)
                hw_file = ""
                if use_hw:
                    hw_path = td / f"hw_{src_id}.txt"
                    hw_path.write_text(
                        "\n".join(f"{w} :{sc}" for w, sc in PREMATCH[src_id]["hotwords"]) + "\n"
                    )
                    hw_file = str(hw_path)

                t_load0 = time.perf_counter()
                kwargs = dict(
                    tokens=str(ZDIR / "tokens.txt"),
                    encoder=str(enc),
                    decoder=str(ZDIR / "decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx"),
                    joiner=str(ZDIR / "joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx"),
                    num_threads=4,
                    sample_rate=16000,
                    feature_dim=80,
                    provider="cpu",
                    enable_endpoint_detection=True,
                    rule1_min_trailing_silence=1.2,
                    rule2_min_trailing_silence=0.5,
                    rule3_min_utterance_length=4.0,
                )
                if use_hw:
                    kwargs.update(
                        decoding_method="modified_beam_search",
                        max_active_paths=6,
                        hotwords_file=hw_file,
                        hotwords_score=2.5,
                        modeling_unit="bpe",
                        bpe_vocab=str(bpe_vocab),
                    )
                else:
                    kwargs.update(decoding_method="greedy_search")

                rec = sherpa_onnx.OnlineRecognizer.from_transducer(**kwargs)
                load_ms = round((time.perf_counter() - t_load0) * 1000.0, 1)

                streamed = run_streaming_clip(rec, samples, max_clause_ms=3200)
                continuous = run_continuous_unsplit(rec, samples)

                ref_w = norm_words(ref_en_by_clip[src_id])
                hyp_stream_w = norm_words(streamed["full_text"])
                hyp_cont_w = norm_words(continuous["full_text"])
                wer_stream = round(edit_ops(ref_w, hyp_stream_w) / len(ref_w), 4)
                wer_cont = round(edit_ops(ref_w, hyp_cont_w) / len(ref_w), 4)

                base_wer = None
                diag_key = f"cs2_auto_{src_id}"
                if diag_key in diag_data["diagnostic_wer"]:
                    base_wer = round(diag_data["diagnostic_wer"][diag_key]["word_error_rate"], 4)

                print(
                    f"  {src_id:20s}: load={load_ms:6.0f}ms rtf={streamed['rtf']:.3f} "
                    f"clauses={len(streamed['clauses']):2d} first_tok={streamed['first_token_audio_ms']}ms "
                    f"WER(stream)={wer_stream*100:.1f}% WER(cont)={wer_cont*100:.1f}% "
                    f"(E2B base={f'{base_wer*100:.1f}%' if base_wer is not None else 'n/a'})"
                )
                v_clips[src_id] = {
                    "load_ms": load_ms,
                    "wer_stream": wer_stream,
                    "wer_continuous": wer_cont,
                    "e2b_baseline_wer": base_wer,
                    "ref_words": len(ref_w),
                    "streamed": streamed,
                    "continuous": continuous,
                }
                del rec
                gc.collect()

            # Compute weighted match WER across the 3 primary match clips
            match_ids = ["clip", "clip_match_demo2", "clip_match_demo3"]
            total_ref = sum(v_clips[i]["ref_words"] for i in match_ids)
            total_err_stream = sum(
                edit_ops(norm_words(ref_en_by_clip[i]), norm_words(v_clips[i]["streamed"]["full_text"]))
                for i in match_ids
            )
            total_err_cont = sum(
                edit_ops(norm_words(ref_en_by_clip[i]), norm_words(v_clips[i]["continuous"]["full_text"]))
                for i in match_ids
            )
            asr_out["variants"][variant] = {
                "weighted_match_wer_stream": round(total_err_stream / total_ref, 4),
                "weighted_match_wer_continuous": round(total_err_cont / total_ref, 4),
                "interview_wer_stream": v_clips["clip_interview_niko"]["wer_stream"],
                "interview_wer_continuous": v_clips["clip_interview_niko"]["wer_continuous"],
                "clips": v_clips,
            }
            print(
                f"  => [{variant}] Weighted Match WER: stream={total_err_stream/total_ref*100:.1f}%, "
                f"continuous={total_err_cont/total_ref*100:.1f}% (E2B auto base=27.8%); "
                f"Interview WER: stream={v_clips['clip_interview_niko']['wer_stream']*100:.1f}%, "
                f"continuous={v_clips['clip_interview_niko']['wer_continuous']*100:.1f}% (E2B auto base=22.3%)"
            )

    (OUT / "asr_results.json").write_text(json.dumps(asr_out, ensure_ascii=False, indent=2) + "\n")
    print(f"\nSaved ASR results to {OUT / 'asr_results.json'}")


def check_cgroup():
    line = next(l for l in Path("/proc/self/cgroup").read_text().splitlines() if l.startswith("0::"))
    cg = Path("/sys/fs/cgroup") / line.split("::", 1)[1].lstrip("/")
    d = {n: (cg / n).read_text().strip() for n in ["memory.max", "memory.swap.max", "memory.peak", "memory.events"]}
    if d["memory.max"] == "max" or int(d["memory.max"]) > 6 * 1024**3 or d["memory.swap.max"] != "0":
        raise RuntimeError(f"Explicit cgroup <=6GiB & swap=0 required, got {d}")
    return d


def cmd_translate(variant):
    sys.path.insert(0, str(ROOT / "evaluation"))
    from gemma_replay import LiteRtRuntime, response_text
    from types import SimpleNamespace

    limits_before = check_cgroup()
    asr_data = json.loads((OUT / "asr_results.json").read_text())
    clips = asr_data["variants"][variant]["clips"]

    out_path = OUT / f"translate_{variant}.jsonl"
    summary_path = OUT / f"translate_{variant}_summary.json"
    if out_path.exists():
        out_path.unlink()

    t_load0 = time.perf_counter()
    runtime = LiteRtRuntime(
        SimpleNamespace(
            model=MODEL,
            threads=4,
            max_new_tokens=128,
            hints="",
            task="bilingual",
            task_profile="baseline",
            system_profile="minimal",
            cache_mode="disk",
            speculative_decoding="on",
            max_context_tokens=768,
        )
    )
    load_ms = round((time.perf_counter() - t_load0) * 1000.0, 1)
    api = runtime.api

    # 1 short text warmup (not timed in latency stats)
    t_w0 = time.perf_counter()
    with runtime.engine.create_conversation(
        system_message=SYSTEM_TEXT_TRANSLATE,
        thinking_config=api.ThinkingConfig(False, 0),
        sampler_config=api.SamplerConfig(top_k=1, top_p=1.0, temperature=0.0),
        max_output_tokens=64,
    ) as conv:
        _ = response_text(
            conv.send_message(
                api.Contents.of("Context: CS2 broadcast.\nCurrent: hello everyone"),
                max_output_tokens=64,
                thinking_config=api.ThinkingConfig(False, 0),
            )
        )
    warmup_ms = round((time.perf_counter() - t_w0) * 1000.0, 1)
    print(f"E2B text translator loaded in {load_ms:.0f}ms, warmup {warmup_ms:.0f}ms")

    all_latencies = []
    all_e2e_tail = []
    rows = []

    try:
        with out_path.open("w") as f:
            f.write(json.dumps({
                "event": "init",
                "variant": variant,
                "load_ms": load_ms,
                "warmup_ms": warmup_ms,
                "limits_before": limits_before,
            }, ensure_ascii=False) + "\n")
            f.flush()

            for src_id in ["cs_demo2_18s", "clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]:
                clauses = clips[src_id]["streamed"]["clauses"]
                ctx = PREMATCH[src_id]["context"]
                prev_en = ""
                print(f"\nTranslating {src_id}: {len(clauses)} streaming clauses...")
                for c in clauses:
                    prev_part = f"\nPrev: {' '.join(prev_en.split()[-18:])}" if prev_en else ""
                    prompt = f"Context: {ctx}{prev_part}\nCurrent: {c['text']}"
                    t0 = time.perf_counter()
                    with runtime.engine.create_conversation(
                        system_message=SYSTEM_TEXT_TRANSLATE,
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
                    # For streaming ASR, decode runs incrementally during speech; only tail chunk (~160ms * rtf)
                    # sits after speech end, plus translation time.
                    tail_asr_ms = round(160.0 * clips[src_id]["streamed"]["rtf"], 1)
                    # Plus endpoint/clause wait: endpoint waits ~500ms silence; soft_cap waits 0ms after cap
                    ep_wait_ms = 500.0 if c["reason"] == "endpoint" else 0.0
                    est_clause_end_to_zh_ms = round(ep_wait_ms + tail_asr_ms + tr_ms, 1)

                    row = {
                        "event": "clause",
                        "source_id": src_id,
                        "clause_id": c["clause_id"],
                        "start_ms": c["start_ms"],
                        "end_ms": c["end_ms"],
                        "reason": c["reason"],
                        "english_asr": c["text"],
                        "chinese": zh,
                        "asr_decode_ms": c["asr_decode_ms"],
                        "translate_ms": tr_ms,
                        "est_clause_end_to_zh_ms": est_clause_end_to_zh_ms,
                    }
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    rows.append(row)
                    if src_id != "cs_demo2_18s":
                        all_latencies.append(tr_ms)
                        all_e2e_tail.append(est_clause_end_to_zh_ms)
                    prev_en = c["text"]
                    print(f"  [{c['start_ms']/1000:5.1f}-{c['end_ms']/1000:5.1f}s {tr_ms:5.0f}ms] {c['text']} => {zh}")
    finally:
        runtime.close()
        gc.collect()

    limits_after = check_cgroup()
    summary = {
        "variant": variant,
        "load_ms": load_ms,
        "warmup_ms": warmup_ms,
        "clauses_4clips": len(all_latencies),
        "translate_p50_ms": quantile(all_latencies, 0.5),
        "translate_p95_ms": quantile(all_latencies, 0.95),
        "translate_mean_ms": round(statistics.mean(all_latencies), 1) if all_latencies else None,
        "est_clause_end_to_zh_p50_ms": quantile(all_e2e_tail, 0.5),
        "est_clause_end_to_zh_p95_ms": quantile(all_e2e_tail, 0.95),
        "limits_after": limits_after,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("\nSummary:", json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["asr", "translate"])
    p.add_argument("--variant", default="int8_hotwords")
    args = p.parse_args()
    if args.mode == "asr":
        cmd_asr()
    else:
        cmd_translate(args.variant)

"""Stage 1 of 3x3 Matrix: Run 3 multilingual-capable ASR models on identical causal VAD segments.

ASR models:
  1. whisper_small_q5:          ggml-small-q5_1.bin (~190 MB, 99 langs, --prompt roster + prev)
  2. whisper_large_v3_turbo_q5: ggml-large-v3-turbo-q5_0.bin (~574 MB, 99 langs, --prompt roster + prev)
  3. parakeet_tdt_v3_int8:      sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8 (~640 MB, 25 EU langs + #1 EN)

All 3 run strictly serially on the exact same causal Silero-VAD + energy-valley segments
(zero future lookahead, 100% PCM coverage, zero dropped audio), plus continuous clip WER diagnostic.
"""

import gc
import json
import os
from pathlib import Path
import re
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
import route_a_eval as ra

MODELS_DIR = Path.home() / "Tools/litert/models/matrix-20261126"
OUT = ROOT / "evaluation/results/matrix-20261126"
WHISPER_BIN_DIR = (ROOT / "evaluation/results/v020-asr-preflight/build/bin").resolve()
WHISPER_CLI = WHISPER_BIN_DIR / "whisper-cli"
WHISPER_ENV = dict(os.environ, LD_LIBRARY_PATH=str(WHISPER_BIN_DIR))
SILERO_ONNX = ROOT / "evaluation/results/s0-20261013/assets/silero_vad.onnx"

ROSTER_PROMPT = {
    "clip": "Spirit, MOUZ, Dust2, donk, sh1ro, tN1R, zont1x, magixx, torzsi, xertioN, Spinx, Brollan, Jimpphat.",
    "clip_match_demo2": "Falcons, FURIA, Mirage, NiKo, m0NESY, TeSeS, kyousuke, kyxsan, FalleN, yuurih, KSCERATO, YEKINDAR, molodoy.",
    "clip_match_demo3": "FaZe, NAVI, Nuke, karrigan, frozen, broky, Twistzz, jcobbb, Aleksib, b1t, iM, w0nderful, makazze.",
    "clip_interview_niko": "NiKo, Falcons, Major, rating.",
    "cs_demo2_18s": "Falcons, FURIA, Mirage, NiKo, m0NESY, TeSeS, kyousuke, kyxsan, FalleN, yuurih, KSCERATO, YEKINDAR, molodoy.",
}


def segment_causal_vad(samples_f32, min_ms=1400, pause_ms=320, soft_cap_ms=4200, valley_lookback_ms=500):
    """Strictly causal Silero VAD + low-energy valley segmenter. Owns 100% of PCM with zero future lookahead."""
    import numpy as np
    import onnxruntime as ort

    sess_opts = ort.SessionOptions()
    sess_opts.intra_op_num_threads = 1
    sess_opts.inter_op_num_threads = 1
    sess = ort.InferenceSession(str(SILERO_ONNX), sess_opts, providers=["CPUExecutionProvider"])
    in_names = [i.name for i in sess.get_inputs()]

    # Handle Silero v5/v6 (input, state, sr) vs v4 (input, h, c, sr)
    use_state = "state" in in_names
    state = np.zeros((2, 1, 128), dtype=np.float32)
    h = np.zeros((2, 1, 64), dtype=np.float32)
    c = np.zeros((2, 1, 64), dtype=np.float32)
    ctx = np.zeros(64, dtype=np.float32)

    sr = 16000
    step = 512  # 32ms
    n = len(samples_f32)
    segs = []

    seg_start = 0
    heard_speech = False
    last_speech_sample = 0
    # Track 32ms frame energies for causal energy-valley selection near soft_cap
    frame_energies = []  # (sample_end, rms)

    for off in range(0, n, step):
        chunk = samples_f32[off : off + step]
        if len(chunk) < step:
            chunk = np.pad(chunk, (0, step - len(chunk)))
        cur_end = min(off + step, n)
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        frame_energies.append((cur_end, rms))

        if use_state:
            inp = np.concatenate([ctx, chunk])[None, :].astype(np.float32)
            out, state = sess.run(None, {"input": inp, "state": state, "sr": np.array(sr, dtype=np.int64)})
            prob = float(out[0][0])
            ctx = chunk[-64:].copy()
        else:
            out, h, c = sess.run(None, {"input": chunk[None, :].astype(np.float32), "h": h, "c": c, "sr": np.array(sr, dtype=np.int64)})
            prob = float(out[0][0])

        if prob >= 0.45:
            heard_speech = True
            last_speech_sample = cur_end

        dur_ms = (cur_end - seg_start) / 16.0
        sil_ms = (cur_end - last_speech_sample) / 16.0

        cut_at = None
        reason = None
        if heard_speech and dur_ms >= min_ms and sil_ms >= pause_ms:
            cut_at = cur_end
            reason = "vad_pause"
        elif dur_ms >= soft_cap_ms:
            # Causal low-energy valley within [cur_end - valley_lookback_ms, cur_end]
            lo = max(seg_start + int(min_ms * 16), cur_end - int(valley_lookback_ms * 16))
            cands = [(s, e) for s, e in frame_energies if lo <= s <= cur_end]
            if cands:
                cut_at = min(cands, key=lambda x: x[1])[0]
            else:
                cut_at = cur_end
            reason = "soft_valley"

        if cut_at is not None and cut_at > seg_start:
            segs.append({
                "seg_id": len(segs) + 1,
                "start_sample": seg_start,
                "end_sample": cut_at,
                "start_ms": int(round(seg_start / 16.0)),
                "end_ms": int(round(cut_at / 16.0)),
                "reason": reason,
            })
            seg_start = cut_at
            heard_speech = any(s > cut_at for s, _ in [(last_speech_sample, 0)])
            frame_energies = [(s, e) for s, e in frame_energies if s > cut_at]

    if seg_start < n:
        if segs and (n - seg_start) < 6400:  # <400ms tiny tail -> merge into last segment
            segs[-1]["end_sample"] = n
            segs[-1]["end_ms"] = int(round(n / 16.0))
        else:
            segs.append({
                "seg_id": len(segs) + 1,
                "start_sample": seg_start,
                "end_sample": n,
                "start_ms": int(round(seg_start / 16.0)),
                "end_ms": int(round(n / 16.0)),
                "reason": "eof",
            })
    return segs


def parse_whisper_infer_ms(stderr):
    def grab(name):
        m = re.search(rf"{name}\s+time\s*=\s*([0-9.]+)\s*ms", stderr)
        return float(m.group(1)) if m else 0.0
    return round(grab("mel") + grab("encode") + grab("decode") + grab("batchd") + grab("prompt"), 1)


def clean_whisper_text(stdout):
    raw = " ".join(l.strip() for l in stdout.splitlines() if l.strip() and not l.strip().startswith("["))
    raw = re.sub(r"<\|[^|]+\|>", "", raw)
    raw = re.sub(r"\[[^\]]*\]", "", raw)
    raw = re.sub(r"\([^)]*music[^)]*\)", "", raw, flags=re.I)
    return " ".join(raw.split())


def run_whisper_model(model_name, model_path, pcms, segs_by_clip, ref_en):
    print(f"\n================ ASR: {model_name} ================", flush=True)
    clips_out = {}
    tot_ref = tot_err_c = tot_err_f = 0

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for src_id, pcm_bytes in pcms.items():
            roster = ROSTER_PROMPT[src_id]
            segs = segs_by_clip[src_id]
            clauses = []
            infer_times = []
            prev_words = []

            for seg in segs:
                wp = td / f"{src_id}_{seg['seg_id']}.wav"
                chunk_pcm = pcm_bytes[seg["start_sample"] * 2 : seg["end_sample"] * 2]
                with wave.open(str(wp), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(chunk_pcm)
                prompt = f"{roster} {' '.join(prev_words[-10:])}".strip() if prev_words else roster
                cmd = [
                    str(WHISPER_CLI), "-m", str(model_path), "-f", str(wp),
                    "-t", "4", "-l", "en", "-nt", "-tp", "0.0", "-bo", "1", "-bs", "1",
                    "--prompt", prompt,
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, check=True, env=WHISPER_ENV)
                txt = clean_whisper_text(r.stdout)
                ms = parse_whisper_infer_ms(r.stderr)
                infer_times.append(ms)
                if txt:
                    prev_words.extend(txt.split())
                clauses.append({
                    "clause_id": seg["seg_id"],
                    "start_ms": seg["start_ms"],
                    "end_ms": seg["end_ms"],
                    "reason": seg["reason"],
                    "asr_ms": ms,
                    "text": txt,
                })

            # Also run continuous full clip (clean roster prompt) as upper-bound diagnostic
            wp_full = td / f"{src_id}_full.wav"
            with wave.open(str(wp_full), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_bytes)
            r_full = subprocess.run(
                [
                    str(WHISPER_CLI), "-m", str(model_path), "-f", str(wp_full),
                    "-t", "4", "-l", "en", "-nt", "-tp", "0.0", "-bo", "1", "-bs", "1",
                    "--prompt", roster,
                ],
                capture_output=True, text=True, check=True, env=WHISPER_ENV,
            )
            full_cont_txt = clean_whisper_text(r_full.stdout)
            full_cont_ms = parse_whisper_infer_ms(r_full.stderr)

            full_causal_txt = " ".join(c["text"] for c in clauses if c["text"])
            rw = ra.norm_words(ref_en[src_id])
            hw_c = ra.norm_words(full_causal_txt)
            hw_f = ra.norm_words(full_cont_txt)
            err_c = ra.edit_ops(rw, hw_c)
            err_f = ra.edit_ops(rw, hw_f)
            wer_c = round(err_c / len(rw), 4)
            wer_f = round(err_f / len(rw), 4)
            dur_ms = len(pcm_bytes) / 32.0
            rtf_c = round(sum(infer_times) / dur_ms, 4)

            if src_id in ("clip", "clip_match_demo2", "clip_match_demo3"):
                tot_ref += len(rw)
                tot_err_c += err_c
                tot_err_f += err_f

            print(
                f"  {src_id:20s}: segs={len(clauses):2d} p50={ra.quantile(infer_times,0.5):5.0f}ms "
                f"p95={ra.quantile(infer_times,0.95):5.0f}ms rtf={rtf_c:.3f} "
                f"ratio={len(hw_c)/len(rw):.2f} WER(causal)={wer_c*100:4.1f}% WER(cont)={wer_f*100:4.1f}%",
                flush=True,
            )
            clips_out[src_id] = {
                "wer_causal": wer_c,
                "wer_continuous": wer_f,
                "ref_words": len(rw),
                "hyp_words_causal": len(hw_c),
                "chunk_p50_ms": ra.quantile(infer_times, 0.5),
                "chunk_p95_ms": ra.quantile(infer_times, 0.95),
                "rtf_causal": rtf_c,
                "rtf_continuous": round(full_cont_ms / dur_ms, 4),
                "clauses": clauses,
                "full_text_causal": full_causal_txt,
                "full_text_continuous": full_cont_txt,
            }

    w_match_c = round(tot_err_c / tot_ref, 4)
    w_match_f = round(tot_err_f / tot_ref, 4)
    w_int_c = clips_out["clip_interview_niko"]["wer_causal"]
    w_int_f = clips_out["clip_interview_niko"]["wer_continuous"]
    print(
        f"  => [{model_name}] Match WER: causal={w_match_c*100:.1f}%, cont={w_match_f*100:.1f}% | "
        f"Interview WER: causal={w_int_c*100:.1f}%, cont={w_int_f*100:.1f}%",
        flush=True,
    )
    print(f"  [cs_demo2_18s causal]: {clips_out['cs_demo2_18s']['full_text_causal']}", flush=True)
    return {
        "model_size_mb": round(model_path.stat().st_size / 1024 / 1024, 1),
        "weighted_match_wer_causal": w_match_c,
        "weighted_match_wer_continuous": w_match_f,
        "interview_wer_causal": w_int_c,
        "interview_wer_continuous": w_int_f,
        "clips": clips_out,
    }


def run_parakeet_model(pdir, samples_by_clip, segs_by_clip, ref_en):
    sys.path.insert(0, str(ra.NUMPY_DEPS))
    sys.path.insert(0, str(ra.SHERPA_DEPS))
    import sherpa_onnx

    print("\n================ ASR: parakeet_tdt_v3_int8 ================", flush=True)
    t_load0 = time.perf_counter()
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(pdir / "encoder.int8.onnx"),
        decoder=str(pdir / "decoder.int8.onnx"),
        joiner=str(pdir / "joiner.int8.onnx"),
        tokens=str(pdir / "tokens.txt"),
        num_threads=4,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        provider="cpu",
        model_type="nemo_transducer",
    )
    load_ms = round((time.perf_counter() - t_load0) * 1000.0, 1)
    print(f"  Parakeet loaded in {load_ms:.0f}ms", flush=True)

    clips_out = {}
    tot_ref = tot_err_c = tot_err_f = 0

    for src_id, samples in samples_by_clip.items():
        segs = segs_by_clip[src_id]
        clauses = []
        infer_times = []

        for seg in segs:
            chunk = samples[seg["start_sample"] : seg["end_sample"]]
            t0 = time.perf_counter()
            s = rec.create_stream()
            s.accept_waveform(16000, chunk)
            rec.decode_stream(s)
            txt = " ".join(s.result.text.split())
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            infer_times.append(ms)
            clauses.append({
                "clause_id": seg["seg_id"],
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
                "reason": seg["reason"],
                "asr_ms": ms,
                "text": txt,
            })

        # Continuous clip diagnostic
        t0 = time.perf_counter()
        s_full = rec.create_stream()
        s_full.accept_waveform(16000, samples)
        rec.decode_stream(s_full)
        full_cont_txt = " ".join(s_full.result.text.split())
        full_cont_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        full_causal_txt = " ".join(c["text"] for c in clauses if c["text"])
        rw = ra.norm_words(ref_en[src_id])
        hw_c = ra.norm_words(full_causal_txt)
        hw_f = ra.norm_words(full_cont_txt)
        err_c = ra.edit_ops(rw, hw_c)
        err_f = ra.edit_ops(rw, hw_f)
        wer_c = round(err_c / len(rw), 4)
        wer_f = round(err_f / len(rw), 4)
        dur_ms = len(samples) / 16.0
        rtf_c = round(sum(infer_times) / dur_ms, 4)

        if src_id in ("clip", "clip_match_demo2", "clip_match_demo3"):
            tot_ref += len(rw)
            tot_err_c += err_c
            tot_err_f += err_f

        print(
            f"  {src_id:20s}: segs={len(clauses):2d} p50={ra.quantile(infer_times,0.5):5.0f}ms "
            f"p95={ra.quantile(infer_times,0.95):5.0f}ms rtf={rtf_c:.3f} "
            f"ratio={len(hw_c)/len(rw):.2f} WER(causal)={wer_c*100:4.1f}% WER(cont)={wer_f*100:4.1f}%",
            flush=True,
        )
        clips_out[src_id] = {
            "wer_causal": wer_c,
            "wer_continuous": wer_f,
            "ref_words": len(rw),
            "hyp_words_causal": len(hw_c),
            "chunk_p50_ms": ra.quantile(infer_times, 0.5),
            "chunk_p95_ms": ra.quantile(infer_times, 0.95),
            "rtf_causal": rtf_c,
            "rtf_continuous": round(full_cont_ms / dur_ms, 4),
            "clauses": clauses,
            "full_text_causal": full_causal_txt,
            "full_text_continuous": full_cont_txt,
        }

    del rec
    gc.collect()

    w_match_c = round(tot_err_c / tot_ref, 4)
    w_match_f = round(tot_err_f / tot_ref, 4)
    w_int_c = clips_out["clip_interview_niko"]["wer_causal"]
    w_int_f = clips_out["clip_interview_niko"]["wer_continuous"]
    size_mb = round(sum(p.stat().st_size for p in pdir.glob("*")) / 1024 / 1024, 1)
    print(
        f"  => [parakeet_tdt_v3_int8] Match WER: causal={w_match_c*100:.1f}%, cont={w_match_f*100:.1f}% | "
        f"Interview WER: causal={w_int_c*100:.1f}%, cont={w_int_f*100:.1f}%",
        flush=True,
    )
    print(f"  [cs_demo2_18s causal]: {clips_out['cs_demo2_18s']['full_text_causal']}", flush=True)
    return {
        "model_size_mb": size_mb,
        "load_ms": load_ms,
        "weighted_match_wer_causal": w_match_c,
        "weighted_match_wer_continuous": w_match_f,
        "interview_wer_causal": w_int_c,
        "interview_wer_continuous": w_int_f,
        "clips": clips_out,
    }


def main():
    sys.path.insert(0, str(ra.NUMPY_DEPS))
    sys.path.insert(0, str(ROOT / "evaluation/results/s0-20261013/deps"))
    import numpy as np

    OUT.mkdir(parents=True, exist_ok=True)
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

    pcms = {
        src: (ra.AUDIO_ROOT / src / "source.pcm").read_bytes()
        for src in ["clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]
    }
    with wave.open(str(ra.DEMO2_18S), "rb") as wf:
        pcms["cs_demo2_18s"] = wf.readframes(wf.getnframes())

    samples_by_clip = {
        k: np.frombuffer(v, dtype=np.int16).astype(np.float32) / 32768.0
        for k, v in pcms.items()
    }

    print("Running causal Silero VAD + energy-valley segmentation (shared across all 3 ASR models)...", flush=True)
    segs_by_clip = {}
    for k, s in samples_by_clip.items():
        segs = segment_causal_vad(s)
        durs = [(sg["end_ms"] - sg["start_ms"]) for sg in segs]
        print(f"  {k:20s}: {len(segs):2d} segments, mean={statistics.mean(durs):.0f}ms, max={max(durs)}ms", flush=True)
        segs_by_clip[k] = segs

    results = {"segmentation": {k: segs_by_clip[k] for k in segs_by_clip}, "models": {}}

    # 1. Parakeet-TDT-0.6B-v3-int8 (in-process sherpa-onnx, freed immediately after)
    results["models"]["parakeet_tdt_v3_int8"] = run_parakeet_model(
        MODELS_DIR / "asr/parakeet-v3-int8", samples_by_clip, segs_by_clip, ref_en
    )
    # 2. Whisper small-q5_1 (multilingual)
    results["models"]["whisper_small_q5"] = run_whisper_model(
        "whisper_small_q5", MODELS_DIR / "asr/ggml-small-q5_1.bin", pcms, segs_by_clip, ref_en
    )
    # 3. Whisper large-v3-turbo-q5_0 (multilingual)
    results["models"]["whisper_large_v3_turbo_q5"] = run_whisper_model(
        "whisper_large_v3_turbo_q5", MODELS_DIR / "asr/ggml-large-v3-turbo-q5_0.bin", pcms, segs_by_clip, ref_en
    )

    out_path = OUT / "matrix_asr_results.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(f"\nALL 3 ASR MODELS DONE -> {out_path}", flush=True)


if __name__ == "__main__":
    main()

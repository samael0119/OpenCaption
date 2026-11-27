"""Causal LocalAgreement-2 rolling-buffer streaming Whisper base.en with segment-boundary buffer trim.

Strictly causal (zero future lookahead):
- Advances every `step_ms=2500` (2.5s)
- Maintains a rolling audio buffer; trims `buf_start_ms` ONLY at an already-committed
  Whisper segment boundary (`seg_end_ms <= committed_seg_end`) so uncommitted audio is NEVER cut!
- Uses LocalAgreement-2 word-prefix confirmation between consecutive decodes.
- Passes `<clean roster> <recent committed words>` as Whisper `--prompt` for seamless context.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
import route_a_eval as ra

BIN_DIR = (ROOT / "evaluation/results/v020-asr-preflight/build/bin").resolve()
CLI = BIN_DIR / "whisper-cli"
MODEL = ROOT / "evaluation/results/v020-asr-preflight/ggml-base.en.bin"
ENV = dict(os.environ, LD_LIBRARY_PATH=str(BIN_DIR))

ROSTER_PROMPT = {
    "clip": "Spirit, MOUZ, Dust2, donk, sh1ro, tN1R, zont1x, magixx, torzsi, xertioN, Spinx, Brollan, Jimpphat.",
    "clip_match_demo2": "Falcons, FURIA, Mirage, NiKo, m0NESY, TeSeS, kyousuke, kyxsan, FalleN, yuurih, KSCERATO, YEKINDAR, molodoy.",
    "clip_match_demo3": "FaZe, NAVI, Nuke, karrigan, frozen, broky, Twistzz, jcobbb, Aleksib, b1t, iM, w0nderful, makazze.",
    "clip_interview_niko": "NiKo, Falcons, Major, rating.",
    "cs_demo2_18s": "Falcons, FURIA, Mirage, NiKo, m0NESY, TeSeS, kyousuke, kyxsan, FalleN, yuurih, KSCERATO, YEKINDAR, molodoy.",
}


def clean_tok(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def parse_whisper_timings(stderr):
    def grab(name):
        m = re.search(rf"{name}\s+time\s*=\s*([0-9.]+)\s*ms", stderr)
        return float(m.group(1)) if m else 0.0
    return round(grab("mel") + grab("encode") + grab("decode") + grab("batchd") + grab("prompt"), 1)


def sanitize_text(s):
    s = re.sub(r"<\|[^|]+\|>", "", s)
    s = re.sub(r"\[[^\]]*\]", "", s)
    return " ".join(s.split())


def align_tail(committed_words, hyp_words):
    if not committed_words:
        return 0
    c_norm = [clean_tok(w) for w in committed_words if clean_tok(w)]
    h_norm = [clean_tok(w) for w in hyp_words]
    if not c_norm:
        return 0
    for skip in (0, 1):
        sub_c = c_norm[: len(c_norm) - skip] if skip else c_norm
        for k in (4, 3, 2):
            if len(sub_c) < k:
                continue
            needle = sub_c[-k:]
            # Search near expected length first to avoid matching far earlier repeats
            expected = len(c_norm)
            matches = [i for i in range(len(h_norm) - k + 1) if h_norm[i : i + k] == needle]
            if matches:
                best = min(matches, key=lambda i: abs((i + k) - expected))
                return best + k
    # Fallback: match longest common prefix from index 0
    i = 0
    while i < len(c_norm) and i < len(h_norm) and c_norm[i] == h_norm[i]:
        i += 1
    return i


def lcp_words(a, b):
    n = min(len(a), len(b))
    i = 0
    while i < n and clean_tok(a[i]) == clean_tok(b[i]):
        i += 1
    return a[:i]


def run_step_json(wav_path, prompt):
    out_prefix = str(wav_path) + ".out"
    cmd = [
        str(CLI), "-m", str(MODEL), "-f", str(wav_path),
        "-t", "4", "-l", "en", "-tp", "0.0", "-bo", "1", "-bs", "1",
        "-oj", "-of", out_prefix,
    ]
    if prompt:
        cmd += ["--prompt", prompt]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True, env=ENV)
    j = json.loads(Path(out_prefix + ".json").read_text())
    segs = []
    for s in j.get("transcription", []):
        txt = sanitize_text(s.get("text", ""))
        if txt:
            segs.append((s["offsets"]["from"], s["offsets"]["to"], txt))
    return segs, parse_whisper_timings(r.stderr)


def run_local_agreement(pcm_bytes, roster_prompt, step_ms=2500, trim_trigger_ms=16000):
    total_ms = len(pcm_bytes) // 32
    buf_start_ms = 0
    committed_in_buf = []
    all_committed = []
    prev_tail = []
    pending_words = []
    pending_start = 0
    clauses = []
    infer_times = []
    first_preview_audio_ms = None
    first_preview_ready_ms = None

    def flush_clause(end_ms, infer_ms, reason):
        nonlocal pending_words, pending_start
        txt = " ".join(pending_words).strip()
        if txt:
            clauses.append({
                "clause_id": len(clauses) + 1,
                "start_ms": pending_start,
                "end_ms": end_ms,
                "reason": reason,
                "asr_step_ms": infer_ms,
                "text": txt,
            })
            pending_start = end_ms
            pending_words = []

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cur_end = step_ms
        step_idx = 0
        while True:
            cur_end = min(cur_end, total_ms)
            step_idx += 1
            wp = td / f"s{step_idx}.wav"
            with wave.open(str(wp), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_bytes[buf_start_ms * 32 : cur_end * 32])

            # Keep prompt clean: roster + last ~8 committed words (only after a trim)
            if buf_start_ms > 0 and all_committed:
                prompt = f"{roster_prompt} {' '.join(all_committed[-8:])}"
            else:
                prompt = roster_prompt

            segs, infer_ms = run_step_json(wp, prompt)
            infer_times.append(infer_ms)

            # Build flat word list with each word's parent segment end offset (relative to buf_start_ms)
            hyp_words = []
            word_seg_end = []
            for s_from, s_to, s_txt in segs:
                ws = s_txt.split()
                hyp_words.extend(ws)
                word_seg_end.extend([s_to] * len(ws))

            if hyp_words and first_preview_audio_ms is None:
                first_preview_audio_ms = cur_end
                first_preview_ready_ms = round(cur_end + infer_ms, 1)

            pos = align_tail(committed_in_buf, hyp_words)
            cur_tail = hyp_words[pos:]

            if cur_end >= total_ms:
                newly = cur_tail
            else:
                newly = lcp_words(prev_tail, cur_tail)

            if newly:
                committed_in_buf.extend(newly)
                all_committed.extend(newly)
                pending_words.extend(newly)
                prev_tail = cur_tail[len(newly) :]
            else:
                prev_tail = cur_tail

            has_punct = bool(pending_words and pending_words[-1][-1:] in ".?!")
            if cur_end >= total_ms:
                flush_clause(cur_end, infer_ms, "eof")
            elif pending_words and (has_punct or len(pending_words) >= 8 or (cur_end - pending_start >= 4000)):
                flush_clause(cur_end, infer_ms, "punct" if has_punct else "clause_ready")

            # Clean segment-boundary buffer trim:
            # Only trim up to a Whisper segment end that lies strictly inside committed words!
            buf_len = cur_end - buf_start_ms
            if buf_len >= trim_trigger_ms and cur_end < total_ms:
                committed_count = pos + len(newly)
                # Find the latest segment whose words are ALL committed and ends at least 3s before cur_end
                trim_rel_ms = 0
                trim_word_idx = 0
                idx_cursor = 0
                for s_from, s_to, s_txt in segs:
                    n_w = len(s_txt.split())
                    if idx_cursor + n_w <= committed_count and (buf_len - s_to) >= 2500:
                        trim_rel_ms = s_to
                        trim_word_idx = idx_cursor + n_w
                    idx_cursor += n_w

                if trim_rel_ms >= 4000:
                    buf_start_ms += trim_rel_ms
                    # Keep only committed words AFTER the trimmed segment
                    committed_in_buf = hyp_words[trim_word_idx:committed_count]
                    # Keep prev_tail as-is (it is strictly after committed_count!)
                elif buf_len >= 24000:
                    # Hard safety cap (never let buffer exceed 24s / Whisper 30s limit):
                    # force-commit everything up to the last segment ending <= buf_len - 4000
                    force_idx = 0
                    force_ms = 0
                    idx_cursor = 0
                    for s_from, s_to, s_txt in segs:
                        n_w = len(s_txt.split())
                        if s_to <= buf_len - 4000:
                            force_idx = idx_cursor + n_w
                            force_ms = s_to
                        idx_cursor += n_w
                    if force_ms >= 6000:
                        extra = hyp_words[committed_count:force_idx] if force_idx > committed_count else []
                        if extra:
                            all_committed.extend(extra)
                            pending_words.extend(extra)
                            flush_clause(cur_end, infer_ms, "force_trim")
                        buf_start_ms += force_ms
                        committed_in_buf = []
                        prev_tail = hyp_words[force_idx:]

            if cur_end >= total_ms:
                break
            cur_end += step_ms

    full_text = " ".join(all_committed)
    return {
        "duration_ms": total_ms,
        "steps": len(infer_times),
        "step_p50_ms": ra.quantile(infer_times, 0.5),
        "step_p95_ms": ra.quantile(infer_times, 0.95),
        "total_decode_ms": round(sum(infer_times), 1),
        "rtf": round(sum(infer_times) / max(1, total_ms), 4),
        "first_preview_audio_ms": first_preview_audio_ms,
        "first_preview_ready_ms": first_preview_ready_ms,
        "clauses": clauses,
        "full_text": full_text,
    }


def main():
    ref_data = json.loads(ra.REF_PATH.read_text())
    diag_data = json.loads(ra.DIAG_PATH.read_text())
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

    print("=== Running Whisper base.en LocalAgreement-2 (v2 segment-boundary trim, step=2.5s, roster prompt) ===")
    v_clips = {}
    tot_ref = tot_err = 0
    for src_id, pcm_bytes in pcms.items():
        res = run_local_agreement(pcm_bytes, ROSTER_PROMPT[src_id], step_ms=2500, trim_trigger_ms=16000)
        rw = ra.norm_words(ref_en[src_id])
        hw = ra.norm_words(res["full_text"])
        err = ra.edit_ops(rw, hw)
        wer = round(err / len(rw), 4)
        if src_id in ("clip", "clip_match_demo2", "clip_match_demo3"):
            tot_ref += len(rw)
            tot_err += err
        bwer = diag_data["diagnostic_wer"].get(f"cs2_auto_{src_id}", {}).get("word_error_rate")
        print(
            f"  {src_id:20s}: rtf={res['rtf']:.3f} step_p50={res['step_p50_ms']:5.0f}ms "
            f"p95={res['step_p95_ms']:5.0f}ms clauses={len(res['clauses']):2d} "
            f"first_en={res['first_preview_ready_ms']}ms WER={wer*100:.1f}% (E2B={f'{bwer*100:.1f}%' if bwer else 'n/a'})"
        )
        v_clips[src_id] = {
            "wer_stream": wer,
            "e2b_baseline_wer": round(bwer, 4) if bwer else None,
            "ref_words": len(rw),
            "streamed": res,
        }

    w_match = round(tot_err / tot_ref, 4)
    w_int = v_clips["clip_interview_niko"]["wer_stream"]
    print(
        f"\n=> [whisper_la2_v2_roster] Weighted Match WER={w_match*100:.1f}% (E2B=27.8%) | "
        f"Interview WER={w_int*100:.1f}% (E2B=22.3%)"
    )
    print("[cs_demo2_18s]:", v_clips["cs_demo2_18s"]["streamed"]["full_text"])

    out = {
        "variant": "whisper_la2_v2_roster",
        "step_ms": 2500,
        "trim_trigger_ms": 16000,
        "weighted_match_wer_stream": w_match,
        "interview_wer_stream": w_int,
        "clips": v_clips,
    }
    ra.OUT.mkdir(parents=True, exist_ok=True)
    (ra.OUT / "whisper_la2_v2_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved to {ra.OUT / 'whisper_la2_v2_results.json'}")


if __name__ == "__main__":
    main()

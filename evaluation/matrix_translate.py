"""Stage 2 of 3x3 Matrix: Cross-validate 3 GGUF translation models across all 3 ASR outputs.

Strictly serial (one llama-server loaded at a time, inside explicit <=6GiB / swap=0 cgroup):
  1. hy_mt_1.8b:  HY-MT1.5-1.8B-Q4_K_M.gguf  (official HY-MT1.5 terminology + context template)
  2. qwen3_1.7b:  Qwen3-1.7B-Q4_K_M.gguf     (thinking disabled, CS2 broadcast + roster recovery)
  3. qwen3_0.6b:  Qwen3-0.6B-Q4_K_M.gguf     (thinking disabled, ultra-lightweight tier)
"""

import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
import route_a_eval as ra

MODELS_DIR = Path.home() / "Tools/litert/models/matrix-20261126"
OUT = ROOT / "evaluation/results/matrix-20261126"
LLAMA_SERVER = OUT / "llama-build/bin/llama-server"
PORT = 18089
BASE_URL = f"http://127.0.0.1:{PORT}"

COMMON_CS_GLOSSARY = [
    ("scout", "鸟狙"),
    ("headshot", "爆头"),
    ("trade", "补枪"),
    ("one-round game", "分差缩到一分"),
    ("claw back", "扳回"),
    ("clawback", "扳回"),
    ("numbers on", "人数优势"),
    ("up to bat", "轮到上场"),
    ("bombsite", "包点"),
    ("high comms", "充分队内沟通"),
]

MATCH_ENTITIES = {
    "clip": ["Spirit", "MOUZ", "Dust2", "donk", "sh1ro", "tN1R", "zont1x", "magixx", "torzsi", "xertioN", "Spinx", "Brollan", "Jimpphat"],
    "clip_match_demo2": ["Falcons", "FURIA", "Mirage", "NiKo", "m0NESY", "TeSeS", "kyousuke", "kyxsan", "FalleN", "yuurih", "KSCERATO", "YEKINDAR", "molodoy"],
    "clip_match_demo3": ["FaZe", "NAVI", "Nuke", "karrigan", "frozen", "broky", "Twistzz", "jcobbb", "Aleksib", "b1t", "iM", "w0nderful", "makazze"],
    "clip_interview_niko": ["NiKo", "Falcons", "Major"],
    "cs_demo2_18s": ["Falcons", "FURIA", "Mirage", "NiKo", "m0NESY", "TeSeS", "kyousuke", "kyxsan", "FalleN", "yuurih", "KSCERATO", "YEKINDAR", "molodoy"],
}

QWEN_SYSTEM = (
    "你是专业的CS2电竞直播与选手采访英译中实时字幕译员。将Current中的英文语音识别文本忠实译为自然流畅的中国大陆简体中文（禁止繁体）。"
    "输入可能包含ASR同音错词或漏标点；仅在发音和语境明显支持时，参考给定的Match/Players名单还原规范英文ID并保留英文原拼写。"
    "严禁编造原文未发生的击杀、比分或事实；严格保留数字、否定和主客体关系。"
    "常用CS2表达：scout=鸟狙、headshot=爆头、trade=补枪、one-round game=分差缩到一分、claw back=扳回/反击、numbers on X=对X有人数优势、up to bat=轮到上场、high comms=队内沟通充分。"
    "仅输出Current对应的单行简体中文译文，不要复述Prev，不要加任何标签或解释。"
)


def check_cgroup():
    line = next(l for l in Path("/proc/self/cgroup").read_text().splitlines() if l.startswith("0::"))
    cg = Path("/sys/fs/cgroup") / line.split("::", 1)[1].lstrip("/")
    d = {n: (cg / n).read_text().strip() for n in ["memory.max", "memory.swap.max", "memory.peak", "memory.events"]}
    if d["memory.max"] == "max" or int(d["memory.max"]) > 6 * 1024**3 or d["memory.swap.max"] != "0":
        raise RuntimeError(f"Explicit cgroup <=6GiB & swap=0 required, got {d}")
    return d


def read_proc_rss_mb(pid):
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024.0, 1)
    except Exception:
        return None
    return None


def wait_server(proc, timeout_s=60):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited early with code {proc.returncode}")
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as r:
                if r.status == 200:
                    return round((time.perf_counter() - t0) * 1000.0, 1)
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("llama-server health timeout")


def build_messages(mt_name, src_id, prev_en, cur_en):
    if mt_name == "hy_mt_1.8b":
        # Put static context + glossary FIRST so llama-server KV prefix cache hits ~85-90%!
        glossary_lines = [f"{e} 翻译成 {e}" for e in MATCH_ENTITIES[src_id]]
        if src_id != "clip_interview_niko":
            glossary_lines += [f"{en} 翻译成 {zh}" for en, zh in COMMON_CS_GLOSSARY]
        else:
            glossary_lines.append("high comms 翻译成 队内沟通充分")
        prev_block = f"\n上一句英文（仅作上文参考，不要翻译）：{' '.join(prev_en.split()[-16:])}" if prev_en else ""
        user_msg = (
            ra.PREMATCH[src_id]["context"]
            + "\n参考下面的翻译：\n"
            + "\n".join(glossary_lines)
            + prev_block
            + "\n参考上面的信息，把下面的文本翻译成中文，注意不需要翻译上文，也不要额外解释：\n"
            + cur_en
        )
        return [{"role": "user", "content": user_msg}]
    else:
        # Qwen3-1.7B / Qwen3-0.6B with thinking explicitly disabled (static system + static Context first!)
        prev_part = f"\nPrev: {' '.join(prev_en.split()[-16:])}" if prev_en else ""
        user_msg = f"Context: {ra.PREMATCH[src_id]['context']}{prev_part}\nCurrent: {cur_en} /no_think"
        return [
            {"role": "system", "content": QWEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]


def call_chat(messages, is_qwen3=False):
    payload = {
        "messages": messages,
        "temperature": 0.0,
        "top_k": 1,
        "max_tokens": 128,
        "stream": False,
        "cache_prompt": True,
    }
    if is_qwen3:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    wall_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    msg = data["choices"][0]["message"]
    raw = msg.get("content") or ""
    had_think = "<think>" in raw.lower() or bool(msg.get("reasoning_content"))
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I)
    cleaned = re.sub(r"<think>[\s\S]*", "", cleaned, flags=re.I)
    zh = " ".join(cleaned.strip().splitlines()).strip()
    timings = data.get("timings", {})
    return {
        "zh": zh,
        "raw": raw,
        "had_think": had_think,
        "wall_ms": wall_ms,
        "prompt_ms": round(timings.get("prompt_ms", 0.0), 1),
        "predicted_ms": round(timings.get("predicted_ms", 0.0), 1),
        "predicted_n": timings.get("predicted_n", 0),
        "tps": round(timings.get("predicted_per_second", 0.0), 1),
    }


def main():
    limits_before = check_cgroup()
    asr_data = json.loads((OUT / "matrix_asr_results.json").read_text())
    asr_names = ["whisper_small_q5", "whisper_large_v3_turbo_q5", "parakeet_tdt_v3_int8"]
    mt_specs = [
        ("hy_mt_1.8b", MODELS_DIR / "mt/HY-MT1.5-1.8B-Q4_K_M.gguf", False),
        ("qwen3_1.7b", MODELS_DIR / "mt/Qwen3-1.7B-Q4_K_M.gguf", True),
        ("qwen3_0.6b", MODELS_DIR / "mt/Qwen3-0.6B-Q4_K_M.gguf", True),
    ]

    out_jsonl = OUT / "matrix_translations.jsonl"
    if out_jsonl.exists():
        out_jsonl.unlink()

    summary = {"limits_before": limits_before, "mt_models": {}, "cells": {}}

    for mt_name, model_path, is_qwen3 in mt_specs:
        print(f"\n==================== MT MODEL: {mt_name} ====================", flush=True)
        log_file = OUT / f"server_{mt_name}.log"
        cmd = [
            str(LLAMA_SERVER),
            "-m", str(model_path),
            "--host", "127.0.0.1",
            "--port", str(PORT),
            "-t", "4",
            "-c", "1024",
            "-np", "1",
            "--cache-ram", "256",
            "--no-webui",
        ]
        if is_qwen3:
            cmd += ["--reasoning-budget", "0"]

        with log_file.open("w") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        try:
            load_ms = wait_server(proc, timeout_s=90)
            # 1 warmup call
            w = call_chat(build_messages(mt_name, "clip", "", "hello welcome to the match"), is_qwen3=is_qwen3)
            print(f"  Server ready in {load_ms:.0f}ms; warmup={w['wall_ms']:.0f}ms ({w['tps']} tok/s) -> {w['zh']}", flush=True)

            mt_peak_rss = read_proc_rss_mb(proc.pid)
            for asr_name in asr_names:
                cell_key = f"{asr_name}__{mt_name}"
                print(f"\n  --- Cell: {cell_key} ---", flush=True)
                wall_list = []
                e2e_list = []
                tps_list = []
                think_leaks = 0
                empty_count = 0

                with out_jsonl.open("a") as f:
                    for src_id in ["cs_demo2_18s", "clip", "clip_match_demo2", "clip_match_demo3", "clip_interview_niko"]:
                        clauses = asr_data["models"][asr_name]["clips"][src_id]["clauses"]
                        prev_en = ""
                        for c in clauses:
                            en_txt = c["text"].strip()
                            if not en_txt:
                                zh = ""
                                res = {"zh": "", "raw": "", "had_think": False, "wall_ms": 0.0, "prompt_ms": 0.0, "predicted_ms": 0.0, "predicted_n": 0, "tps": 0.0}
                            else:
                                res = call_chat(build_messages(mt_name, src_id, prev_en, en_txt), is_qwen3=is_qwen3)
                                zh = res["zh"]
                                prev_en = en_txt
                            if res["had_think"]:
                                think_leaks += 1
                            if en_txt and not zh:
                                empty_count += 1
                            row = {
                                "cell": cell_key,
                                "asr": asr_name,
                                "mt": mt_name,
                                "source_id": src_id,
                                "clause_id": c["clause_id"],
                                "start_ms": c["start_ms"],
                                "end_ms": c["end_ms"],
                                "english_asr": en_txt,
                                "chinese": zh,
                                "asr_ms": c["asr_ms"],
                                "mt_wall_ms": res["wall_ms"],
                                "mt_prompt_ms": res["prompt_ms"],
                                "mt_pred_ms": res["predicted_ms"],
                                "mt_tps": res["tps"],
                                "had_think": res["had_think"],
                            }
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
                            if src_id != "cs_demo2_18s" and en_txt:
                                wall_list.append(res["wall_ms"])
                                e2e_list.append(round(c["asr_ms"] + res["wall_ms"], 1))
                                if res["tps"] > 0:
                                    tps_list.append(res["tps"])
                        if src_id == "cs_demo2_18s":
                            f.flush()
                    f.flush()

                cur_rss = read_proc_rss_mb(proc.pid)
                if cur_rss and (mt_peak_rss is None or cur_rss > mt_peak_rss):
                    mt_peak_rss = cur_rss

                cell_stat = {
                    "clauses_4clips": len(wall_list),
                    "mt_p50_ms": ra.quantile(wall_list, 0.5),
                    "mt_p95_ms": ra.quantile(wall_list, 0.95),
                    "mt_mean_ms": round(statistics.mean(wall_list), 1) if wall_list else None,
                    "mt_median_tps": ra.quantile(tps_list, 0.5),
                    "asr_plus_mt_p50_ms": ra.quantile(e2e_list, 0.5),
                    "asr_plus_mt_p95_ms": ra.quantile(e2e_list, 0.95),
                    "think_leaks": think_leaks,
                    "empty_outputs": empty_count,
                }
                summary["cells"][cell_key] = cell_stat
                print(
                    f"    DONE {cell_key}: mt_p50={cell_stat['mt_p50_ms']}ms mt_p95={cell_stat['mt_p95_ms']}ms "
                    f"tps={cell_stat['mt_median_tps']} asr+mt_p50={cell_stat['asr_plus_mt_p50_ms']}ms "
                    f"think_leaks={think_leaks} empty={empty_count}",
                    flush=True,
                )

            summary["mt_models"][mt_name] = {
                "size_mb": round(model_path.stat().st_size / 1024 / 1024, 1),
                "load_ms": load_ms,
                "peak_rss_mb": mt_peak_rss,
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            time.sleep(0.5)

    summary["limits_after"] = check_cgroup()
    (OUT / "matrix_translate_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("\nALL 9 MATRIX CELLS DONE!", flush=True)


if __name__ == "__main__":
    main()

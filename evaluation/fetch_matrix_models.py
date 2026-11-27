"""Download the 3 ASR + 3 MT models for the 3x3 Route A cross-validation matrix into ~/Tools/litert/models/matrix-20261126."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

DEST = Path.home() / "Tools/litert/models/matrix-20261126"

FILES = [
    # 3 ASR models (all multilingual-capable, English-priority)
    ("asr/ggml-small-q5_1.bin", "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin"),
    ("asr/ggml-large-v3-turbo-q5_0.bin", "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin"),
    ("asr/parakeet-v3-int8/encoder.int8.onnx", "https://hf-mirror.com/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/encoder.int8.onnx"),
    ("asr/parakeet-v3-int8/decoder.int8.onnx", "https://hf-mirror.com/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/decoder.int8.onnx"),
    ("asr/parakeet-v3-int8/joiner.int8.onnx", "https://hf-mirror.com/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/joiner.int8.onnx"),
    ("asr/parakeet-v3-int8/tokens.txt", "https://hf-mirror.com/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/tokens.txt"),
    # 3 MT models (llama.cpp GGUF Q4_K_M)
    ("mt/HY-MT1.5-1.8B-Q4_K_M.gguf", "https://hf-mirror.com/tencent/HY-MT1.5-1.8B-GGUF/resolve/main/HY-MT1.5-1.8B-Q4_K_M.gguf"),
    ("mt/Qwen3-1.7B-Q4_K_M.gguf", "https://hf-mirror.com/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf"),
    ("mt/Qwen3-0.6B-Q4_K_M.gguf", "https://hf-mirror.com/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for rel, url in FILES:
        out = DEST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"==> Fetching {rel} ...", flush=True)
        subprocess.run(
            ["curl", "-fL", "--retry", "3", "--retry-delay", "2", "-C", "-", "--connect-timeout", "20", "-o", str(out), url],
            check=True,
        )
        size = out.stat().st_size
        print(f"    OK {rel}: {size / 1024 / 1024:.1f} MiB", flush=True)
        manifest[rel] = {"url": url, "size": size, "sha256": sha256(out)}
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("ALL MODELS READY:", DEST / "manifest.json", flush=True)


if __name__ == "__main__":
    main()

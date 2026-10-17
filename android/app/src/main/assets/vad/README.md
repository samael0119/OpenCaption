# Silero boundary detector

Pinned to snakers4/silero-vad v6.2.1 (`src/silero_vad/data/silero_vad.onnx`).
SHA-256: `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`.
Upstream: https://github.com/snakers4/silero-vad/tree/v6.2.1
MIT licence and copyright are in LICENSE beside the model.

16 kHz, 512 completed samples + 64 context samples, recurrent state 2×1×128.
Used only to choose causal submission boundaries; never to delete quiet PCM.
Unavailable detector falls back to continuous five-second windows.

ONNX Runtime Android is pinned to 1.22.0; its MIT notice is retained in
ONNXRUNTIME_LICENSE (upstream microsoft/onnxruntime v1.22.0/LICENSE).

# Changelog

Notable user-visible changes are documented here. The project follows semantic version tags for public snapshots; it does not yet promise a stable API.

## 0.2.0 - 2026-11-27

Major mobile real-time captioning release introducing a dual-pipeline architecture inside the main `OpenCaption` APK, upgraded floating overlay UX, CS2 phonetic normalization and unified community nicknames, and faster startup/model management.

### Dual-Pipeline On-Device Architecture
- **Decoupled ONNX ASR + HY-MT1.5-1.8B pipeline** (`听译分离 · ONNX + HY-MT`) alongside **Gemma 4 E2B/E4B LiteRT-LM** (`端到端 · Gemma 4`), switchable directly on the home screen while preserving each mode's selected models.
- **Pure-Kotlin ONNX Runtime ASR (`OnnxAsrEngine`)** reusing the existing `onnxruntime-android` runtime with zero extra APK bloat:
  - **Parakeet-TDT 0.6B v3 INT8** (639 MB, 25 European languages, recommended for English — ~0.3–0.4 s per window on Snapdragon 8 Elite CPU).
  - **SenseVoice-Small INT8** (228 MB, zh/en/ja/ko/yue — ~0.18–0.22 s per window on CPU) with Silero VAD speech gating, `<|nospeech|>/<|BGM|>` header filtering, quiet-speech gain guard, and filler hallucination suppression.
- **Tencent HY-MT1.5-1.8B Q4** local Chinese translation via `llama.cpp` forced to CPU (`op_offload=false`, empty Vulkan device list) to eliminate mobile Adreno Vulkan prompt corruption while keeping 1.0–2.5 s per-sentence latency.
- Removed slow/deprecated Whisper (`small`/`base`/`large-v3-turbo`) and legacy Qwen 0.5B/0.8B models from the catalog.

### Floating Overlay & Playback Capture UX
- **2-slot rolling caption display** (dimmed previous subtitle above, bold active bilingual caption below) with length-scaled minimum reading hold (`1.8–2.6 s`) to prevent rapid subtitle flashing.
- Whole-panel drag and tap-to-toggle quick bar (`双语/仅中`, `2行/1行`, `A−`, `A+`, `停止`) with 4.5 s auto-hide and 12 s silence smooth fade.
- **Persistent overlay preferences** (font size, bilingual/Chinese-only, 2-line/1-line) synchronized bidirectionally with Settings (`14–36` font size), plus immediate persistence for all Home and Settings controls.
- **Android 14+ full-display default** via `MediaProjectionConfig.createConfigForDefaultDisplay()` so system playback capture defaults directly to sharing the entire screen.
- Stopping the overlay now keeps the local translator warm in memory so retrying an interrupted last line works immediately.

### CS2 Terminology, Phonetic Normalizer & Community Styles
- Added pre-MT **CS2 phonetic normalizer (`AsrPhoneticNormalizer`)** covering 60+ active pro player IDs (200+ phonetic variants including `monese→m0NESY`, `carrigan→karrigan`, `shira→sh1ro`, etc.), callout homophones (`Maine→Main`, `city side→CT side`, `double orb→double AWP`, `U til→util`), and context-gated ambiguous names.
- Added curated broadcast terminology pack (`cs2_zh_asr_broadcast_v0.3.json`), 5-minute decoupled match memory, and custom `A=B` hint pair injection.
- Unified **148-player CS2 community nickname asset** (`assets/corpora/cs2_player_nicknames.json`) shared by both Dart (HY-MT1.5) and Kotlin (Gemma E2E), supporting multi-variant nickname rotation and context guards for ordinary English words.
- Enabled **Standard / Natural commentary / Community** translation styles and community nicknames across both decoupled HY-MT1.5 and Gemma E2E pipelines.

### Model Management & Startup
- Added **one-tap deprecated model cleanup (`一键清理`)** in the Model Manager to safely reclaim storage from removed legacy weights without touching active models.
- Extended receipt+stat fast-path verification to all large single-file and multi-file bundle models (millisecond startup checks) with live `% · MB/s` download progress.
- Unified Android launcher name to **OpenCaption** while keeping package ID and signing key unchanged for seamless in-place upgrades.

## 0.2.0-preview.3 - 2026-10-17

- Fix overlay bottom dragging in immersive playback by matching visible system-bar insets and updating placement when those insets change.
- Preserve the manually chosen bottom anchor through long/short captions, temporary screen-edge clamping, rotation and settings expansion; avoid cumulative position drift.
- Add five geometry regressions (53 Android unit tests pass). Android device interaction remains unverified; recognition and terminology behaviour are unchanged.

## 0.2.0-preview.2 - 2026-10-17

- Center overlay subtitles and integrate a small settings toggle at the right end of the subtitle bar; reveal drag, stop and text-size controls inside the same bar only when opened.
- Adapt overlay width to landscape screens and reflow/clamp the overlay after rotation while preserving subtitle colours, opacity and capture controls.
- Package the approved integrated-settings layout as an arm64 Release-mode preview (123.6MB), using the existing local test signature and keeping R8 disabled for LiteRT compatibility. Six geometry checks pass alongside the existing 42 Android unit tests; native on-device interaction remains unverified.

## 0.2.0-preview.1 - 2026-10-17

Local engineering and subtitle-reading preview (`0.2.0-preview.1+3`), not a completed v0.2.0 release. Build and acceptance limits are described in these version entries.

- Pause-first Gemma segmentation with a five-second cap and fixed-window fallback; a bounded pending queue merges contiguous short intervals and reports replacement or expiry as audio gaps.
- Exact-zero audio filtering and stricter bilingual/no-speech validation; E2B short nonzero inputs receive leading-zero padding without additional capture wait.
- Conditional CS2 terminology corrections, dated relationship checks and bounded recent evidence. Selecting the CS2 library enables the existing automatic assistance path; uncertain scenes abstain.
- Optional current-session map and team corrections, conflict feedback and a restore-auto action; a partial team pair stays pending.
- A simpler subtitle reading surface, expandable status details, theme and large-text handling, and stable history review. Overlay layout changes have not been checked on Android.
- Mouse-wheel history review now stays in place when new captions arrive; returning to the latest caption restores automatic following.

Nonzero-music hallucinations, critical short-answer omissions and independent CS2/Chinese quality remain unresolved. Related one-hop candidates and semantic preceding context have not been enabled in normal generation. Local unit/build/UI checks do not establish content accuracy or screen latency; final joint long-run acceptance remains incomplete. The bounded optimization cycle is paused. Detailed checkpoints and experiment records are maintained locally under the ignored `docs/dev/` directory.

## 0.1.0 - 2026-09-16

Initial public source release of the Android development and evaluation build:

- English and Chinese project entry points, screenshots, and a concise design overview;
- original OpenCaption branding and Android launcher icons;
- PolyForm Noncommercial 1.0.0 license, contribution guide, security policy, and third-party notices;
- local-first Gemma 4 E2B/E4B captions through LiteRT-LM;
- microphone and Android playback-capture inputs;
- bilingual, transcription-only, and automatic-language tasks;
- model download/import verification and local evaluation tooling;
- experimental legacy cascade and Qwen E2E flavors.

This release remains a development preview and has not passed the documented long-run, power, quality, or multi-device release gates.

<p align="center">
  <img src="assets/branding/opencaption-logo.png" alt="OpenCaption logo" width="144">
</p>

# OpenCaption

[简体中文](README.zh-CN.md) · [Documentation](docs/README.md) · [License](LICENSE)

OpenCaption is a local-first Android app for real-time captions. Its main path combines a Flutter UI, Kotlin audio capture and scheduling, and Gemma 4 through LiteRT-LM to produce English transcripts and Simplified Chinese captions directly on the device.

> [!WARNING]
> OpenCaption is a development and evaluation preview. Model quality, long-run stability, power consumption, and device compatibility have not passed the release gates. Current release-mode APKs use a local development signature and are not store-ready packages.

## Screenshots

<table>
  <tr>
    <td align="center"><img src="docs/images/home.jpg" alt="OpenCaption home screen" width="260"></td>
    <td align="center"><img src="docs/images/models.jpg" alt="Offline model management" width="260"></td>
    <td align="center"><img src="docs/images/captions.jpg" alt="Live bilingual captions and diagnostics" width="260"></td>
  </tr>
  <tr>
    <td align="center">Session setup</td>
    <td align="center">Offline models</td>
    <td align="center">Live captions</td>
  </tr>
</table>

## What it does

- Runs speech understanding and caption generation locally after model setup; audio is not uploaded by the default path.
- Supports microphone input and Android 10+ playback capture with a movable caption overlay, subject to the source app's audio-sharing policy.
- Offers English-to-bilingual captions, automatic-language-to-Chinese plus source text, English-only transcription, and Chinese-only transcription.
- Downloads or imports models with expected-size and SHA-256 verification, resumable downloads, and multiple configured sources.
- Provides optional scene/name context, a CS2 terminology profile, theme and caption styling, and bounded runtime diagnostics.
- Keeps captions in the current session only. Returning to the home screen clears the transcript.

## Recommended path

`gemmaE2E` is the current mainline flavor. Gemma 4 E2B is the default and recommended real-time model:

- LiteRT-LM Android `0.17.0` with `.litertlm` packages from `litert-community`.
- GPU-first initialization with CPU fallback; audio encoding runs on the CPU.
- E2B and E4B both use MTP/speculative decoding, `maxNumTokens=768`, a maximum output of 128 tokens, and the app cache directory.
- Configurable CPU support threads: 2, 4, 6, or 8; the default is 4.
- Observed latency on the current test phone is roughly 0.6–1.6 seconds for E2B and 2.6–6 seconds for E4B. These figures are observations, not cross-device guarantees.

| Flavor | Role | Implementation | Recommendation |
| --- | --- | --- | --- |
| `gemmaE2E` | Mainline | Gemma 4 E2B/E4B through LiteRT-LM; one model handles speech understanding, transcription, and Chinese output | Default |
| `cascade` | Compatibility and historical evaluation | whisper.cpp followed by ML Kit or local GGUF translation | Not a future mainline |
| `qwenE2E` | Experimental | Qwen Omni through MNN | Dedicated experiments only |

The repository retains the older whisper.cpp/llama.cpp path and Qwen manifests for reproducibility and compatibility. The Gemma flavor does not load Whisper, Silero, or a separate translation model.

## Models

The model manager shows purpose, size, readiness, source, recommendation, and integrity status. Current entries include:

- Gemma 4 E2B (~2.59 GB): default real-time caption model.
- Gemma 4 E4B (~3.66 GB): quality-oriented option with higher mobile latency.
- Whisper `small.en` and `base.en`: English-only legacy cascade candidates.
- Qwen2.5 0.5B and Qwen3.5 0.8B: legacy local-translation experiments; Qwen3.5 did not fit the current real cgroup memory constraints reliably.
- Qwen Omni 3B MNN: earlier end-to-end experimental flavor.
- NLLB-200: unavailable because the current runtime does not support its encoder-decoder architecture.

TranslateGemma 4B is not listed because the published LiteRT Community artifact is a MediaPipe Web `.task`, not a LiteRT-LM-loadable `.litertlm` package.

Models are downloaded separately and remain subject to their providers' licenses and terms. They are not covered by this repository's license.

## Using the app

1. Install the APK for the required flavor and open **Prepare and manage models**. Downloads and imports are checked against the catalog size and SHA-256 digest.
2. For Gemma E2E, keep E2B selected unless quality is more important than latency. Choose the speech task on the home screen.
3. Choose an input:
   - **Microphone** captures ambient sound. Audio playing only in headphones cannot reach the microphone.
   - **This-device audio** uses Android 10+ playback capture and a foreground overlay. It requires system and overlay permission, and the source app must allow audio sharing. Calls, DRM content, and some apps may block capture. OpenCaption does not record the screen.
4. Optionally provide up to 240 characters of scene or proper-name context. It is filtered and treated as untrusted data, not as a second instruction channel.
5. The default terminology profile is general and injects no glossary. Select the CS2 profile explicitly to use its terminology.
6. Adjust theme, font size, source/translation colors, overlay opacity, and CPU support threads in settings.

Gemma uses fixed five-second, non-overlapping audio windows and serial inference. If work backs up, an old window that has not started may be replaced so latency cannot grow without bound. Pause, stop, background transitions, serious thermal conditions, memory pressure, or revoked audio permission stop or cancel the relevant task.

## Privacy and limitations

- Default recognition and caption generation run on-device. Raw audio is kept in native memory and is not persisted or uploaded.
- The external Chat Completions-compatible text translation code path is hidden in current product builds. A custom build that enables it sends text to the configured service.
- The first model download requires a network connection. The legacy ML Kit path may also download language packs through Google's SDK.
- Debug builds can expose diagnostics and write timestamped logs to Android public Downloads. Release mode disables that behavior by default. Review logs before sharing them.
- No current APK has completed the required 3 × 60-minute stability run, power and thermal evaluation, held-out quality evaluation, and multi-device validation.

## Development

The local development convention uses:

- JDK 17: `~/Tools/java/eclipse-temurin-jdk17`
- shared LiteRT/LiteRT-LM tools and models: `~/Tools/litert`
- test audio, references, and logs: `~/Downloads/opencaption`

The project wrapper isolates Flutter, Pub, and Gradle state under the repository. The current toolchain is Flutter 3.47.2, Dart 3.13.2, JDK 17, Android SDK 36, NDK 28.2.13676358, and CMake 3.22.1. The minimum Android API is 28, and only `arm64-v8a` is built.

```bash
export OPENCAPTION_JAVA_HOME="$HOME/Tools/java/eclipse-temurin-jdk17"
python3 scripts/fetch_native.py
scripts/flutterw pub get
scripts/flutterw analyze --no-pub
scripts/flutterw test --no-pub
```

Native revisions are pinned in `native.lock.json`. After changing `pigeons/engine.dart`, regenerate the bridge:

```bash
PUB_CACHE="$PWD/.pub-cache" .tools/flutter/bin/dart --suppress-analytics \
  run pigeon --input pigeons/engine.dart
```

## Building an APK

The build script enforces arm64 and verifies the configured signing fingerprint so test APK upgrades retain app-private model files:

```bash
# Debug test APK with diagnostics enabled by default
scripts/build-apk gemmaE2E

# Release-mode test APK; still not a store-signed package
OPENCAPTION_BUILD_MODE=release \
OPENCAPTION_DIAGNOSTICS=false \
scripts/build-apk gemmaE2E
```

`cascade` and `qwenE2E` can be built in the same way. Output is written under `build/app/outputs/flutter-apk/`. Release builds currently leave R8 and resource shrinking disabled until LiteRT-LM reflection and native binding keep rules are complete and device-tested.

Run tests and builds serially. Do not load multiple large models concurrently.

## LiteRT-LM evaluation

Linux CPU evaluation uses the shared LiteRT-LM environment and an explicit cgroup memory limit:

```bash
scripts/setup-gemma-eval
scripts/fetch-gemma-litert

OPENCAPTION_MEMORY_MAX_MB=6144 scripts/run-gemma-eval \
  "$HOME/Downloads/opencaption/clip.wav" \
  --model "$HOME/Tools/litert/models/gemma-4-E2B-it.litertlm" \
  --speculative-decoding=true \
  --cache-mode=memory \
  --warmup=1 \
  --max-context-tokens=768
```

The runner uses systemd `MemoryHigh`/`MemoryMax` with swap disabled. Do not replace the real memory limit with `ulimit -v`; mapped address space is not resident memory. Results include raw model output, parser status, per-window inference time, RTF, and peak RSS.

## Documentation

- [Design overview](docs/design.md)

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report sensitive vulnerabilities according to [SECURITY.md](SECURITY.md), not through a public issue.

## License

Original project material is available under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use is not permitted by that license.

This is a **source-available** license, not an OSI-approved open-source license. Third-party software, models, and data retain their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

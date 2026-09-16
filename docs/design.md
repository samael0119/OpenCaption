# OpenCaption Design Overview

This document describes the current system shape and the boundaries contributors should preserve. It is intentionally concise; benchmark history and product planning remain in the repository's Chinese working notes.

## Goals

OpenCaption is a local-first Android application that turns live speech into readable source-language and Simplified Chinese captions.

The current design prioritizes:

- on-device audio processing after model setup;
- bounded latency and memory instead of unbounded queues;
- explicit user control over capture, models, and context;
- predictable cancellation across pause, stop, and lifecycle changes;
- measurable behavior without presenting evaluation data as a product guarantee.

## System structure

```text
Microphone / Android playback capture
                 │
                 ▼
      Kotlin audio and lifecycle layer
                 │
          bounded audio windows
                 │
                 ▼
     LiteRT-LM Gemma inference worker
                 │
       validated caption protocol
                 │
                 ▼
       Dart session and caption state
                 │
        Flutter UI / overlay service
```

### Flutter and Dart

The Dart layer owns:

- application screens and settings;
- session phase and generation IDs;
- caption ordering and bounded history;
- model catalog state and integrity receipts;
- terminology matching and context filtering;
- translation compatibility paths.

`SessionController` coordinates the active session. `CaptionLedger` keeps stable caption IDs, prevents stale generations from overwriting current results, and limits retained entries. `ModelStore` manages catalog metadata, downloads, imports, and verification.

### Kotlin and Android

The Android layer owns:

- microphone and playback audio capture;
- foreground-service and overlay lifecycles;
- audio buffering and window scheduling;
- LiteRT-LM engine creation and cancellation;
- thermal, memory, CPU, and available GPU signals;
- the Pigeon bridge back to Dart.

Audio remains in native/runtime memory and is not written as a recording. Playback capture uses Android's MediaProjection authorization but does not create or encode video.

### Model paths

`gemmaE2E` is the mainline flavor. One Gemma model performs speech understanding, transcription, and optional Chinese output through LiteRT-LM.

The repository also retains two experimental or compatibility flavors:

- `cascade`: whisper.cpp recognition followed by ML Kit or GGUF translation;
- `qwenE2E`: Qwen Omni through MNN.

These paths exist for reproducibility and comparison. New product work should not silently expand them into additional mainlines.

## Runtime flow

1. The user selects an input, speech task, model, and optional context.
2. The selected model is accepted only after expected-size and SHA-256 verification.
3. Android prepares capture and a single inference worker.
4. Gemma receives fixed five-second, non-overlapping audio windows.
5. At most one window runs and one waits. If the device falls behind, the older waiting window is replaced rather than allowing latency to grow without bound.
6. Model output must pass the expected caption protocol before entering Dart state.
7. Captions are displayed in stable order in the app and, for playback capture, in the movable overlay.
8. Pause, stop, generation changes, permission loss, serious thermal state, or memory pressure invalidate or cancel relevant work.

The mainline uses GPU-first initialization with CPU fallback. Audio encoding uses CPU support threads. The current Gemma configuration uses speculative decoding, a bounded context and output length, deterministic sampling, and the app cache directory.

## Data and trust boundaries

### Audio and captions

- Raw audio is not persisted or uploaded by the default path.
- Captions live only in the current session and are cleared after returning home.
- Debug diagnostics may write operational logs to Android public Downloads; users should review them before sharing.

### User context

Optional scene and proper-name context is length-limited, stripped of control characters and tags, checked for common instruction-injection forms, and presented to the model as untrusted data. It is not a second instruction channel.

### Models

Models are downloaded separately and are not licensed by this repository. The catalog pins expected size and SHA-256 and can use multiple download sources. A completed file is enabled atomically only after verification.

### Terminology packs

Terminology is optional. General mode injects no domain glossary; the CS2 profile must be selected explicitly. The bundled packs are maintainer-directed, AI-assisted project compilations. Their metadata distinguishes project-contributed expression from public facts, names, trademarks, and third-party rights.

## Failure behavior

- Missing or invalid models block session start with a visible error.
- Invalid model output is rejected rather than displayed as a caption.
- Translation failure preserves source text.
- Results from canceled or obsolete generations cannot update current captions.
- Queue overload drops or replaces bounded pending work and records the event.
- Capture authorization loss, task removal, or severe resource conditions stop the affected session instead of silently restarting it.

## Build and generated interfaces

- Flutter/Dart and Kotlin communicate through Pigeon definitions in `pigeons/engine.dart`.
- Generated bridge files are committed and must be regenerated with their source change.
- Native dependency revisions are pinned in `native.lock.json` and fetched outside Git.
- Only `arm64-v8a` is currently built; the minimum Android API is 28.
- Release-mode test APKs currently use a local development signature and are not store-ready artifacts.

## Extension guidelines

When adding a model, capture source, or output mode:

1. keep model instances and queues bounded;
2. define cancellation and stale-result behavior before implementation;
3. preserve local processing unless the UI explicitly discloses an external service;
4. validate external data and model output at their trust boundaries;
5. add focused tests and update README-visible behavior and limitations;
6. report performance with the exact model, device, input, and configuration rather than as a universal claim.

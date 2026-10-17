# Changelog

Notable user-visible changes are documented here. The project follows semantic version tags for public snapshots; it does not yet promise a stable API.

## Unreleased

## 0.2.0-preview.1 - 2026-10-17

Local engineering and subtitle-reading preview (`0.2.0-preview.1+3`), not a completed v0.2.0 release. See the [preview notes](docs/v0.2.0-preview.1.md) for build and acceptance limits.

- Pause-first Gemma segmentation with a five-second cap and fixed-window fallback; a bounded pending queue merges contiguous short intervals and reports replacement or expiry as audio gaps.
- Exact-zero audio filtering and stricter bilingual/no-speech validation; E2B short nonzero inputs receive leading-zero padding without additional capture wait.
- Conditional CS2 terminology corrections, dated relationship checks and bounded recent evidence. Selecting the CS2 library enables the existing automatic assistance path; uncertain scenes abstain.
- Optional current-session map and team corrections, conflict feedback and a restore-auto action; a partial team pair stays pending.
- A simpler subtitle reading surface, expandable status details, theme and large-text handling, and stable history review. Overlay layout changes have not been checked on Android.
- Mouse-wheel history review now stays in place when new captions arrive; returning to the latest caption restores automatic following.

Nonzero-music hallucinations, critical short-answer omissions and independent CS2/Chinese quality remain unresolved. Related one-hop candidates and semantic preceding context have not been enabled in normal generation. Local unit/build/UI checks do not establish content accuracy or screen latency; final joint long-run acceptance remains incomplete. The bounded optimization cycle is paused. See the [checkpoint](docs/v0.2.0执行检查点.md) for evidence and remaining work.

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

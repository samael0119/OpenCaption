# Changelog

Notable user-visible changes are documented here. The project follows semantic version tags for public snapshots; it does not yet promise a stable API.

## Unreleased

- Add optional Gemma caption styles and independently selectable Chinese community player names. Keep the existing audio prompts and Standard default; apply a small, guarded set of CS2 wording and playful display rules after inference, with an audio-time cooldown for added jokes.
- Reject the tested generative style/meaning prompts after nonzero-music hallucinations increased. This development work does not establish an ASR accuracy or independent human preference improvement.

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

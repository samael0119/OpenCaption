# Public release checklist

Use this checklist before creating the first public GitHub release. It intentionally separates repository preparation from actions that publish or sign artifacts.

## Blocking decisions

- [x] Resolve version identity. `pubspec.yaml` now declares `0.1.0+2`, aligned with the planned `v0.1.0` tag and release title.
- [x] Document the CS2 terminology provenance and license scope: maintainer-directed, AI-assisted project compilation; PolyForm applies only to project-contributed expression and does not relicense third-party facts, names, or trademarks.
- [ ] Decide whether the first public release includes an APK or source only. Current release-mode APKs use a development key and are explicitly not store-ready.
- [x] Replace the placeholder Flutter launcher icon with the approved OpenCaption artwork and retain the supplied master assets.

## Repository review

- [ ] Keep the repository private until the blocking decisions above are resolved, then switch visibility only after reviewing the public file list from a clean clone.
- [ ] Review the English and Chinese README/major documents for product claims, model names, paths, dates, and current limitations.
- [ ] Confirm `LICENSE` is the intended PolyForm Noncommercial 1.0.0 text and that the repository description says source-available/noncommercial rather than OSI open source.
- [ ] Review `THIRD_PARTY_NOTICES.md` and generate the complete notice inventory for the exact APK, if an APK is distributed.
- [ ] Confirm no models, APKs, audio, transcripts, debug logs, keystores, credentials, private evaluation data, or local tool caches are tracked.
- [ ] Review screenshots for private information and third-party content. The imported README screenshots intentionally exclude the Bilibili/CS2 playback screenshot.
- [ ] Configure GitHub private vulnerability reporting or replace the fallback wording in `SECURITY.md` with a dedicated security contact.
- [ ] Set the repository description to something explicit, for example: `Local-first Android real-time bilingual captions powered by Gemma 4 and LiteRT-LM.`
- [ ] Add focused topics such as `android`, `flutter`, `kotlin`, `on-device-ai`, `speech-to-text`, `live-captions`, `gemma`, and `litert`.
- [ ] Add the social preview after branding is final; consider branch protection and Discussions when accepting outside contributions.

## Validation

- [ ] `scripts/flutterw analyze --no-pub`
- [ ] `scripts/flutterw test --no-pub`
- [ ] Gemma Android unit tests.
- [ ] Build the selected flavor serially with the intended diagnostics setting.
- [ ] Inspect the APK manifest, supported ABI, version name/code, signature, and native libraries.
- [ ] Install/upgrade on a clean test device and verify model download/import, microphone, playback capture, overlay, pause/resume/stop, and offline operation.
- [ ] Record checksums for every distributed binary.

## Release actions — only after maintainer approval

- [ ] Freeze the changelog date and release notes.
- [ ] Commit the reviewed release-preparation changes.
- [ ] Create an annotated tag matching the approved app version.
- [ ] Push the commit and tag.
- [ ] Create the GitHub release and attach only reviewed artifacts and checksums.
- [ ] Verify links, screenshots, license detection, and downloadable artifacts from the public repository view.

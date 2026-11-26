# Evaluation utilities

This directory contains evaluation source code and fixtures. Shared setup and example commands are in the [project README](../README.md#litert-lm-evaluation); contribution requirements are in [CONTRIBUTING.md](../CONTRIBUTING.md).

Run inference serially with an explicit memory limit and disabled swap. Parser success, component timings and local replay results do not establish transcript accuracy, screen latency or Android device performance. Input audio and references belong in ignored `evaluation/private/`; generated results and frozen evidence belong in ignored `evaluation/results/`.

Development plans, per-round reports and historical evaluation notes have moved to the ignored local `docs/dev/` workspace. They are not distributed with this repository. Previously completed batches should not be rerun merely because the documentation was reorganized.

Resolve these output directories from the current checkout root. Retain completed evidence there so research links survive cleanup of temporary files.

`cs_domain_round.py`, `CsDomainBridge.java`, and the opt-in
`test/cs_domain_live_eval_test.dart` connect fresh audio inference to the current
Kotlin protocol/style rules and Dart corpus/session controller. The local CS
reference stays in ignored `evaluation/private/`; results and frozen source
snapshots stay in `evaluation/results/`. This offline fixed-fallback replay
does not exercise Android capture, VAD, queue deadlines, or the overlay. The
audit script sums an explicitly authored judgment ledger; it is not an
independent automatic translation-quality judge. Existing runs refuse to
overwrite evidence or retry model calls implicitly.

## E2B latency

In a diagnostics build, the Android session log records matching epoch and
window IDs for the audio cut, queue, inference, parser, Dart controller, and
subtitle drawing stages. Analyze one log with
`python3 evaluation/e2e_latency_log.py /path/to/session.log`.
The Flutter marker is reported after framework painting and includes the
return through the platform channel. The overlay marker is recorded in
`onDraw`. These are drawing milestones, with separate distributions for
source and translated text. Use a physical-screen measurement for display
latency.

`e2b_p0_stream.py` pairs synchronous and streaming SDK calls, comparing the
first closed English line with the synchronous parser result. Compile
`E2bP0Bridge.java` with `CaptionStyle`, `E2eProtocol`,
`E2ePreservedNames` and the existing Kotlin runtime on its classpath, then
pass that classpath as `--bridge-classpath`. Use `--historical` or
`--paired /path/to/paired.jsonl` for a model-free re-audit. Each audit needs
a fresh `--results` directory. Fresh inference uses one existing E2B model
under a 6 GiB cgroup limit with swap disabled.

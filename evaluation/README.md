# Evaluation utilities

This directory contains evaluation source code and fixtures. Shared setup and example commands are in the [project README](../README.md#litert-lm-evaluation); contribution requirements are in [CONTRIBUTING.md](../CONTRIBUTING.md).

Run inference serially with an explicit memory limit and disabled swap. Parser success, component timings and local replay results do not establish transcript accuracy, screen latency or Android device performance. Input audio and references belong in ignored `evaluation/private/`; generated results and frozen evidence belong in ignored `evaluation/results/`.

Development plans, per-round reports and historical evaluation notes have moved to the ignored local `docs/dev/` workspace. They are not distributed with this repository. Previously completed batches should not be rerun merely because the documentation was reorganized.

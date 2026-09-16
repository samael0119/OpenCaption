# Contributing to OpenCaption

Thank you for considering a contribution. OpenCaption is currently an early development and evaluation project, so please open an issue before starting a large change.

## Before you start

- Search existing issues and describe the user problem, target Android device, app flavor, and model involved.
- Keep pull requests focused. Do not combine behavior changes with broad formatting or generated-file churn.
- Do not commit model files, APKs, recordings, transcripts, diagnostic logs, credentials, keystores, or private evaluation data.
- Only contribute material that you have the right to redistribute. This applies especially to terminology corpora, screenshots, test audio, model artifacts, and translated text.
- AI-assisted contributions are welcome only when the contributor has reviewed, tested, and can license the result.

## Development setup

The supported toolchain and build commands are documented in the [README](README.md#development). The short validation path is:

```bash
python3 scripts/fetch_native.py
scripts/flutterw pub get
scripts/flutterw analyze --no-pub
scripts/flutterw test --no-pub
```

Run tests and model experiments serially. Inference experiments must use an explicit memory limit; do not load multiple large models concurrently.

For behavior changes, update the relevant tests and documentation. Generated Pigeon bridge files must be regenerated from `pigeons/engine.dart` and committed with the source change.

## Pull requests

A pull request should include:

- a concise explanation of the problem and approach;
- the exact validation commands and results;
- device/model details for Android inference changes;
- screenshots for visible UI changes;
- documentation updates for changed behavior, defaults, limits, or model requirements.

The project does not claim cross-device performance or release readiness from a single benchmark. Keep measurements scoped to the tested device, model, input, and configuration.

## Licensing of contributions

By submitting a contribution, you agree that it may be distributed under the repository's [PolyForm Noncommercial License 1.0.0](LICENSE). Third-party components and model artifacts remain under their own licenses.

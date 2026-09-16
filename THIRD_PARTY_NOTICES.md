# Third-party software and models

OpenCaption's project license applies only to original project material. Dependencies, native engines, SDKs, models, and data remain under their respective licenses and terms.

## Native engines

Exact source revisions are recorded in [`native.lock.json`](native.lock.json) and fetched by [`scripts/fetch_native.py`](scripts/fetch_native.py). The repository does not vendor those source trees.

- whisper.cpp and llama.cpp: MIT License. The notice bundled into the app is in [`assets/native_licenses.txt`](assets/native_licenses.txt).
- MNN: Apache License 2.0.
- SPIRV-Headers and Vulkan-Headers: see the upstream license files at the pinned revisions.

## Runtime and application dependencies

- Flutter and Dart packages retain their upstream licenses. Flutter-generated application notices are available through the framework's license registry.
- LiteRT-LM and Google ML Kit retain their upstream licenses and service terms.
- Android, Kotlin, Gradle, and related build dependencies retain their upstream licenses.

Before distributing an APK, generate and review the complete dependency notice inventory for that exact artifact. This file is a project-level guide, not a substitute for the license files embedded by dependencies.

## Models

Models are not included in this repository. The application can download or import them after installation. Each model is governed by the terms published by its provider; the PolyForm license does not relicense any model.

In particular, Gemma models are subject to Google's Gemma terms. Qwen, Whisper, Silero, and other catalog entries retain their own model licenses. Review the provider's current terms before downloading, redistributing, or using a model.

## Terminology data

The bundled CS2 terminology packs are AI-assisted project compilations. The maintainer supplied public reference links and the intended schema and use; AI assisted with factual extraction, translation, normalization, and structuring; the maintainer reviewed and adopted the resulting data.

PolyForm Noncommercial 1.0.0 applies only to the project-contributed selection, structure, translations, annotations, and other original expression, to the extent those rights are held by the project licensor. It does not relicense factual names, player or team identifiers, trademarks, public facts, or any third-party material. The source URLs in each pack are citations for factual verification, not claims that the referenced pages use the project license.

The packs contain short terms, names, factual records, and project-produced annotations rather than copied long-form source passages. Contributors must not add third-party prose, images, or datasets without compatible redistribution permission.

# Security Policy

## Supported versions

OpenCaption is currently a pre-release project. Security fixes are applied to the latest revision on the `main` branch; older commits and locally built APKs are not supported release lines.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose recordings, captions, credentials, model-download integrity, or device data. Use GitHub's private vulnerability reporting feature for this repository. If it is unavailable, contact the repository owner through the email address listed on the maintainer's GitHub profile.

Include the affected commit, Android version and device, app flavor, reproduction steps, impact, and any suggested mitigation. Do not include real API keys, private audio, transcripts, or diagnostic logs containing sensitive information.

You can expect an initial acknowledgement within seven days. A remediation timeline depends on severity and reproducibility; no public disclosure date should be assumed until coordinated with the maintainer.

## Scope notes

- Models are downloaded from third-party hosts and enabled only after the expected size and SHA-256 digest are verified.
- Release-mode test APKs currently use a local development signature and are not store-ready artifacts.
- External text translation is hidden in current product builds. If enabled in a custom build, it sends text to the configured service; audio remains local.
- Debug diagnostics may write logs to Android public Downloads. Review them before sharing.

#!/usr/bin/env bash
# Sequential checks: do not run this alongside an APK build on a small host.
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
scripts/flutterw test --concurrency=1 --no-pub
scripts/flutterw analyze --no-pub lib test pigeons
if [[ "${1:-}" == "--android" ]]; then
  if [[ -z "${OPENCAPTION_JAVA_HOME:-}" ]]; then
    echo 'Set OPENCAPTION_JAVA_HOME to a JDK 17 installation.' >&2
    exit 1
  fi
  scripts/build-apk cascade
  (
    cd android
    JAVA_HOME="$OPENCAPTION_JAVA_HOME" \
    ANDROID_HOME="${ANDROID_HOME:-$project_root/.tools/android-sdk}" \
    GRADLE_USER_HOME="$project_root/.gradle" \
    CMAKE_BUILD_PARALLEL_LEVEL=8 \
    ./gradlew --no-daemon --max-workers=8 -Ptarget-platform=android-arm64 :app:testDebugUnitTest
  )
fi

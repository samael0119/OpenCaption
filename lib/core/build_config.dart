/// Compile-time product/test switch.
///
/// Test APKs are built with `--dart-define=OPENCAPTION_DIAGNOSTICS=true`;
/// release APKs set it to false.  Keeping the flag compile-time means a
/// production build cannot accidentally expose evaluation counters or the
/// diagnostics panel through a runtime preference.
const bool diagnosticsEnabled = bool.fromEnvironment(
  'OPENCAPTION_DIAGNOSTICS',
  defaultValue: false,
);

const String buildChannel = String.fromEnvironment(
  'OPENCAPTION_CHANNEL',
  defaultValue: 'release',
);

const bool isTestBuild = diagnosticsEnabled || buildChannel == 'test';

/// External text translation remains implemented for a future release, but
/// is not exposed in the current product builds.  A dedicated compile-time
/// switch keeps the stored configuration backwards compatible without making
/// the feature accidentally selectable from the UI.
const bool externalTranslationEnabled = bool.fromEnvironment(
  'OPENCAPTION_ENABLE_EXTERNAL_TRANSLATION',
  defaultValue: false,
);

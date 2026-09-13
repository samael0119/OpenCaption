import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(
  PigeonOptions(
    dartPackageName: 'opencaption',
    dartOut: 'lib/platform/engine.g.dart',
    kotlinOut:
        'android/app/src/main/kotlin/dev/opencaption/opencaption/Engine.g.kt',
    kotlinOptions: KotlinOptions(package: 'dev.opencaption.opencaption'),
  ),
)
class EngineConfig {
  EngineConfig({
    required this.asrPath,
    required this.vadPath,
    required this.translationPath,
    required this.mode,
    required this.threads,
    required this.names,
  });
  String asrPath;
  String vadPath;
  String translationPath;
  String mode;
  int threads;
  /// Bounded user scene/context hint or glossary data; never an instruction.
  String names;
}

class RecognitionEvent {
  RecognitionEvent({
    required this.epoch,
    required this.window,
    required this.revision,
    required this.startMs,
    required this.endMs,
    required this.text,
    required this.finalResult,
  });
  int epoch;
  int window;
  int revision;
  int startMs;
  int endMs;
  String text;
  bool finalResult;
}

class BilingualEvent {
  BilingualEvent({
    required this.epoch,
    required this.window,
    required this.startMs,
    required this.endMs,
    required this.english,
    required this.chinese,
  });
  int epoch;
  int window;
  int startMs;
  int endMs;
  String english;
  String chinese;
}

@HostApi()
abstract class EngineHost {
  @async
  bool requestMicrophone();
  @async
  void prepare(EngineConfig config);
  void start(int epoch);
  void pause();
  @async
  void drain();
  void cancel();

  /// Replace the bounded E2E hint string between audio windows.
  void updateHints(String hints);
  @async
  void release();
  @async
  String translate(int epoch, String id, String text, String payload);
  void cancelTranslation(String id);
  @async
  bool mlKitReady();
  @async
  void downloadMlKit();
  @async
  void deleteMlKit();
  void openAppSettings();
}

@FlutterApi()
abstract class EngineEvents {
  void recognition(RecognitionEvent event);
  void bilingual(BilingualEvent event);
  void activity(int epoch, double level, bool speech, int audioMs);
  void interrupted(int epoch, String code);
  void gap(int epoch, int startMs, int endMs);
  void diagnostic(int epoch, String code, int durationMs);
}

// Explicit loopback-only evaluation entry. Not imported by the shipped app.
import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'core/captions.dart';
import 'core/corpus.dart';
import 'core/session_controller.dart';
import 'models/model_store.dart';
import 'platform/engine.g.dart';
import 'main.dart' show OpenCaptionApp;

@JS('deliveryBridge.install')
external void install(JSFunction callback);
@JS('deliveryBridge.frame')
external void frame(JSString value);
@JS('deliveryBridge.log')
external void record(JSString value);

void log(Map<String, Object?> row) => record(jsonEncode(row).toJS);

class DeliveryHost extends EngineHost {
  @override
  Future<void> updateHints(String hints, bool automaticAssist) async {
    log({'type': 'actual_hints', 'hints': hints, 'automatic': automaticAssist});
  }
}

class DeliveryController extends SessionController {
  DeliveryController() : super(host: DeliveryHost());
  @override
  String get backendFlavor => 'gemmaE2E';
  @override
  Future<void> savePreferences() async {}
  void setTheme(String value) {
    theme = value;
    notifyListeners();
  }

  @override
  Future<void> start() async {
    phase = SessionPhase.listening;
    notifyListeners();
  }

  @override
  Future<void> pause() async {
    phase = SessionPhase.paused;
    notifyListeners();
  }

  @override
  Future<void> resume() async {
    phase = SessionPhase.listening;
    notifyListeners();
  }

  @override
  Future<void> end() async {
    phase = SessionPhase.ended;
    notifyListeners();
  }
}

Map<String, Object?> locateCaption(String id, String chinese) {
  Element? found;
  void walk(Element e) {
    if (e.widget.key == ValueKey(id)) found = e;
    if (found == null) e.visitChildren(walk);
  }

  final root = WidgetsBinding.instance.rootElement;
  if (root != null) walk(root);
  if (found == null) {
    return {'laid_out': false, 'reason': 'not_built_or_offscreen'};
  }
  Element? text;
  void findText(Element e) {
    final w = e.widget;
    if (w is Text && w.data == chinese) text = e;
    if (text == null) e.visitChildren(findText);
  }

  findText(found!);
  final box = text?.findRenderObject();
  if (box is! RenderBox || !box.hasSize || !box.attached) {
    return {'laid_out': false, 'reason': 'translation_not_laid_out'};
  }
  final rect = box.localToGlobal(Offset.zero) & box.size;
  final viewport = RenderAbstractViewport.maybeOf(box);
  var clip = Offset.zero & (MediaQuery.maybeOf(found!)?.size ?? Size.zero);
  final viewportBox = viewport is RenderBox ? viewport as RenderBox : null;
  if (viewportBox != null && viewportBox.hasSize) {
    clip = clip.intersect(
      viewportBox.localToGlobal(Offset.zero) & viewportBox.size,
    );
  }
  final intersection = rect.intersect(clip);
  final visible = intersection.width > 0 && intersection.height > 0;
  return {
    'laid_out': true,
    'visible_in_viewport': visible,
    'fully_in_viewport':
        visible &&
        intersection.width >= rect.width - .5 &&
        intersection.height >= rect.height - .5,
    'bounds': [rect.left, rect.top, rect.width, rect.height],
    'viewport': [clip.left, clip.top, clip.width, clip.height],
    'text': chinese,
  };
}

Future<void> main() async {
  if (!const bool.fromEnvironment('OPENCAPTION_DELIVERY_PREVIEW')) {
    throw StateError('Requires explicit local delivery evaluation build');
  }
  WidgetsFlutterBinding.ensureInitialized();
  final c = DeliveryController();
  c.corpus = await CorpusIndex.load(rootBundle);
  c.models.catalog =
      (jsonDecode(await rootBundle.loadString('assets/models.json')) as List)
          .map((v) => ModelSpec(Map<String, dynamic>.from(v as Map)))
          .toList();
  c.asrId = 'gemma-4-e2b-litert';
  c.models.ready.add(c.asrId);
  c.corpusProfile = CorpusProfile.cs2;
  c.initialized = true;
  c.phase = SessionPhase.listening;
  c.theme = Uri.base.queryParameters['theme'] ?? 'dark';
  c.message = '本机交付验证 · 缓存字幕';
  runApp(OpenCaptionApp(controller: c));
  install(
    ((JSString input) {
      try {
        final row = jsonDecode(input.toDart) as Map<String, dynamic>;
        final commandId = row['id'];
        if (row['type'] == 'theme') {
          c.setTheme(row['value'] == 'light' ? 'light' : 'dark');
          return jsonEncode({
            'type': 'theme_changed',
            'event_id': commandId,
          }).toJS;
        }
        if (row['type'] == 'end') {
          unawaited(c.end());
          return jsonEncode({'type': 'ended', 'event_id': commandId}).toJS;
        }
        if (row['type'] == 'no_speech') {
          // No subtitle injection. This is a transport control, not a native parser test.
          return jsonEncode({
            'type': 'no_subtitle_control',
            'event_id': commandId,
            'ledger_count': c.ledger.items.length,
          }).toJS;
        }
        if (row['type'] != 'subtitle' ||
            row['window'] is! int ||
            row['start_ms'] is! int ||
            row['end_ms'] is! int ||
            row['english'] is! String ||
            row['chinese'] is! String ||
            row['start_ms'] < 0 ||
            row['end_ms'] <= row['start_ms']) {
          return jsonEncode({
            'type': 'invalid_event',
            'event_id': commandId,
          }).toJS;
        }
        final before = c.ledger.items.map((item) => item.id).toSet();
        c.bilingual(
          BilingualEvent(
            epoch: c.epoch,
            window: row['window'],
            startMs: row['start_ms'],
            endMs: row['end_ms'],
            english: row['english'],
            chinese: row['chinese'],
            appliedHints: row['hints'] as String? ?? 'CS2 broadcast.',
          ),
        );
        final appended = c.ledger.items
            .where((item) => !before.contains(item.id))
            .toList();
        if (appended.isEmpty) {
          return jsonEncode({
            'type': 'not_delivered',
            'event_id': commandId,
            'reason': 'controller_rejected_or_duplicate',
          }).toJS;
        }
        final item = appended.single;
        final watch = Stopwatch()..start();
        var tries = 0;
        void measure(Duration _) {
          final bounds = locateCaption(item.id, item.chinese);
          frame(
            jsonEncode({
              'event_id': commandId,
              'caption_id': item.id,
              'caption_chinese': item.chinese,
              'source': item.english,
              'attempt': ++tries,
              'elapsed_since_controller_ms': watch.elapsedMicroseconds / 1000,
              'semantic_correctness': 'unrated_cache_instrumentation',
              ...bounds,
            }).toJS,
          );
          if (bounds['fully_in_viewport'] != true &&
              watch.elapsedMilliseconds < 1500 &&
              tries < 100) {
            WidgetsBinding.instance.addPostFrameCallback(measure);
            WidgetsBinding.instance.scheduleFrame();
          }
        }

        WidgetsBinding.instance.addPostFrameCallback(measure);
        WidgetsBinding.instance.scheduleFrame();
        return jsonEncode({
          'type': 'controller_delivered',
          'event_id': commandId,
          'caption_id': item.id,
          'ledger_count': c.ledger.items.length,
          'chinese': item.chinese,
        }).toJS;
      } catch (e) {
        return jsonEncode({
          'type': 'invalid_event',
          'reason': e.toString(),
        }).toJS;
      }
    }).toJS,
  );
}

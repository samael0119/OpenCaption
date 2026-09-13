import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

class ModelSource {
  ModelSource(Map<String, dynamic> json, {bool allowInsecure = false})
    : id = json['id'] as String,
      label = json['label'] as String,
      priority = json['priority'] as int? ?? 100,
      url = Uri.parse(json['url'] as String) {
    if (id.isEmpty ||
        label.isEmpty ||
        !url.hasAuthority ||
        (!allowInsecure && url.scheme != 'https') ||
        (allowInsecure && url.scheme != 'https' && url.scheme != 'http')) {
      throw const FormatException('模型下载源配置无效');
    }
  }

  final String id;
  final String label;

  /// Lower values are preferred source tiers; latency ranks sources in a tier.
  final int priority;
  final Uri url;
}

class ModelPart {
  ModelPart(Map<String, dynamic> json, {bool allowInsecureSources = false})
    : file = json['file'] as String,
      size = json['size'] as int,
      hash = json['sha256'] as String,
      sources = (json['sources'] as List<dynamic>)
          .map(
            (source) => ModelSource(
              source as Map<String, dynamic>,
              allowInsecure: allowInsecureSources,
            ),
          )
          .toList(growable: false);
  final String file, hash;
  final int size;
  final List<ModelSource> sources;
}

class ModelSpec {
  ModelSpec(Map<String, dynamic> json, {bool allowInsecureSources = false})
    : id = json['id'] as String,
      file = json['file'] as String,
      label = json['label'] as String,
      kind = json['kind'] as String,
      size = json['size'] as int,
      hash = json['sha256'] as String,
      sources = (json['sources'] as List<dynamic>)
          .map(
            (source) => ModelSource(
              source as Map<String, dynamic>,
              allowInsecure: allowInsecureSources,
            ),
          )
          .toList(growable: false),
      parts = (json['files'] as List<dynamic>? ?? const [])
          .map(
            (part) => ModelPart(
              part as Map<String, dynamic>,
              allowInsecureSources: allowInsecureSources,
            ),
          )
          .toList(growable: false),
      releaseApproved = json['releaseApproved'] == true,
      runtimeSupported = json['runtimeSupported'] != false,
      unavailableReason = json['unavailableReason'] as String? ?? '' {
    if (sources.isEmpty ||
        sources.map((source) => source.id).toSet().length != sources.length) {
      throw const FormatException('模型必须配置不重复的下载源');
    }
  }

  final String id, file, label, kind, hash;
  final int size;
  final List<ModelSource> sources;
  final List<ModelPart> parts;
  final bool releaseApproved;
  final bool runtimeSupported;
  final String unavailableReason;
}

class _ProbeResult {
  const _ProbeResult(this.source, this.elapsed);
  final ModelSource source;
  final Duration elapsed;
}

class _SourceFailure implements Exception {
  const _SourceFailure(this.message);
  final String message;
  @override
  String toString() => message;
}

typedef ModelHttpClientFactory = HttpClient Function();

class ModelStore extends ChangeNotifier {
  ModelStore({
    ModelHttpClientFactory? clientFactory,
    this.probeBytes = 64 * 1024,
  }) : _clientFactory = clientFactory ?? HttpClient.new;

  final ModelHttpClientFactory _clientFactory;
  final int probeBytes;
  late Directory directory;
  List<ModelSpec> catalog = [];
  final Map<String, double> progress = {};
  final Map<String, String> errors = {};
  final Map<String, String> states = {};
  final Map<String, String> activeSources = {};
  final Set<String> ready = {};
  final Map<String, Set<HttpClient>> _clients = {};
  final Set<String> _cancelled = {};

  Future<void> initialize() async {
    directory = Directory(
      '${(await getApplicationSupportDirectory()).path}/models',
    );
    await directory.create(recursive: true);
    catalog =
        (jsonDecode(await rootBundle.loadString('assets/models.json')) as List)
            .map((json) => ModelSpec(json as Map<String, dynamic>))
            .toList();
    for (final spec in catalog) {
      final entity = spec.parts.isEmpty
          ? File(path(spec.id))
          : Directory(path(spec.id));
      final receipt = await _readReceipt(spec);
      if (await entity.exists() &&
          receipt != null &&
          (entity is Directory ||
              await (entity as File).length() == spec.size)) {
        if (entity is Directory) await _writeQwenOverrides(spec, entity);
        ready.add(spec.id);
        final source = receipt['sourceLabel'];
        if (source is String && source.isNotEmpty) {
          activeSources[spec.id] = source;
        }
      }
    }
    notifyListeners();
  }

  ModelSpec spec(String id) => catalog.firstWhere((spec) => spec.id == id);
  String path(String id) => '${directory.path}/${spec(id).file}';
  bool get busy => progress.isNotEmpty;

  HttpClient _openClient(String id) {
    final client = _clientFactory()
      ..connectionTimeout = const Duration(seconds: 15);
    _clients.putIfAbsent(id, () => <HttpClient>{}).add(client);
    return client;
  }

  void _closeClient(String id, HttpClient client) {
    _clients[id]?.remove(client);
    if (_clients[id]?.isEmpty ?? false) _clients.remove(id);
    client.close(force: true);
  }

  Future<Map<String, Object?>?> _readReceipt(ModelSpec spec) async {
    final receipt = File('${path(spec.id)}.verified');
    if (!await receipt.exists()) return null;
    try {
      final contents = await receipt.readAsString();
      if (contents.trim() == spec.hash) {
        return <String, Object?>{'sha256': spec.hash};
      }
      final json = jsonDecode(contents) as Map<String, dynamic>;
      if (json['sha256'] != spec.hash || json['size'] != spec.size) return null;
      return Map<String, Object?>.from(json);
    } catch (_) {
      return null;
    }
  }

  Future<void> _writeReceipt(ModelSpec spec, ModelSource? source) async {
    final stat = spec.parts.isEmpty ? await File(path(spec.id)).stat() : null;
    await File('${path(spec.id)}.verified').writeAsString(
      jsonEncode(<String, Object?>{
        'sha256': spec.hash,
        'size': spec.size,
        if (stat != null) 'modifiedUs': stat.modified.microsecondsSinceEpoch,
        if (stat != null) 'changedUs': stat.changed.microsecondsSinceEpoch,
        'sourceId': source?.id ?? 'manual-import',
        'sourceLabel': source?.label ?? '手动导入',
        'completedAt': DateTime.now().toUtc().toIso8601String(),
      }),
      flush: true,
    );
  }

  Future<void> verifyForUse(String id) async {
    try {
      final model = spec(id);
      if (model.id == 'gemma-4-e2b-litert' && model.parts.isEmpty) {
        final receipt = await _readReceipt(model);
        final stat = await File(path(id)).stat();
        if (stat.type == FileSystemEntityType.file &&
            stat.size == model.size &&
            receipt?['modifiedUs'] == stat.modified.microsecondsSinceEpoch &&
            receipt?['changedUs'] == stat.changed.microsecondsSinceEpoch) {
          return;
        }
        await _verify(model, path(id));
        // Old receipts undergo one full check, then retain download provenance.
        final refreshed = <String, Object?>{
          ...?receipt,
          'sha256': model.hash,
          'size': model.size,
          'modifiedUs': stat.modified.microsecondsSinceEpoch,
          'changedUs': stat.changed.microsecondsSinceEpoch,
        };
        await File(
          '${path(id)}.verified',
        ).writeAsString(jsonEncode(refreshed), flush: true);
        return;
      }
      await _verify(spec(id), path(id));
    } catch (_) {
      ready.remove(id);
      errors[id] = '模型校验失败，请重新获取';
      notifyListeners();
      rethrow;
    }
  }

  Future<void> _verify(ModelSpec spec, String filename) async {
    final valid = await Isolate.run(() async {
      if (spec.parts.isNotEmpty) {
        for (final part in spec.parts) {
          final file = File('$filename/${part.file}');
          if (!await file.exists() ||
              await file.length() != part.size ||
              (await sha256.bind(file.openRead()).first).toString() !=
                  part.hash) {
            return false;
          }
        }
        return true;
      }
      final file = File(filename);
      return await file.exists() &&
          await file.length() == spec.size &&
          (await sha256.bind(file.openRead()).first).toString() == spec.hash;
    });
    if (!valid) throw const FormatException('模型大小或 SHA-256 不匹配');
  }

  RegExpMatch _contentRange(HttpClientResponse response) {
    final value = response.headers.value(HttpHeaders.contentRangeHeader) ?? '';
    final match = RegExp(r'^bytes (\d+)-(\d+)/(\d+)$').firstMatch(value);
    if (match == null) throw const _SourceFailure('下载源未返回有效范围');
    return match;
  }

  Future<_ProbeResult> _probe(
    String id,
    ModelSpec spec,
    ModelSource source,
  ) async {
    final client = _openClient(id);
    final watch = Stopwatch()..start();
    try {
      final last = probeBytes.clamp(1, spec.size).toInt() - 1;
      final request = await client
          .getUrl(source.url)
          .timeout(const Duration(seconds: 15));
      request.headers
        ..set(HttpHeaders.rangeHeader, 'bytes=0-$last')
        ..set(HttpHeaders.acceptEncodingHeader, 'identity');
      final response = await request.close().timeout(
        const Duration(seconds: 20),
      );
      if (response.statusCode != HttpStatus.partialContent) {
        throw _SourceFailure('HTTP ${response.statusCode}');
      }
      final range = _contentRange(response);
      if (int.parse(range.group(1)!) != 0 ||
          int.parse(range.group(2)!) != last ||
          int.parse(range.group(3)!) != spec.size) {
        throw const _SourceFailure('下载源文件大小不匹配');
      }
      var received = 0;
      await for (final chunk in response.timeout(const Duration(seconds: 15))) {
        received += chunk.length;
        if (received > last + 1) throw const _SourceFailure('测速响应过大');
      }
      if (received != last + 1) throw const _SourceFailure('测速响应不完整');
      watch.stop();
      return _ProbeResult(source, watch.elapsed);
    } finally {
      _closeClient(id, client);
    }
  }

  Future<List<ModelSource>> _rankSources(String id, ModelSpec spec) async {
    states[id] = '正在测速…';
    notifyListeners();
    final results = await Future.wait(
      spec.sources.indexed.map((entry) async {
        try {
          return (index: entry.$1, result: await _probe(id, spec, entry.$2));
        } catch (_) {
          return null;
        }
      }),
    );
    if (_cancelled.contains(id)) throw const _SourceFailure('已取消');
    final available =
        results.whereType<({int index, _ProbeResult result})>().toList()
          ..sort((left, right) {
            final byPriority = left.result.source.priority.compareTo(
              right.result.source.priority,
            );
            if (byPriority != 0) return byPriority;
            final byTime = left.result.elapsed.compareTo(right.result.elapsed);
            return byTime != 0 ? byTime : left.index.compareTo(right.index);
          });
    if (available.isEmpty) throw const _SourceFailure('所有下载源均不可用');
    return available
        .map((entry) => entry.result.source)
        .toList(growable: false);
  }

  Future<void> _downloadFrom(
    String id,
    ModelSpec spec,
    ModelSource source,
    File partial,
  ) async {
    final client = _openClient(id);
    try {
      final offset = await partial.exists() ? await partial.length() : 0;
      if (offset < 0 || offset >= spec.size) {
        throw const _SourceFailure('断点位置无效');
      }
      final request = await client
          .getUrl(source.url)
          .timeout(const Duration(seconds: 20));
      request.headers
        ..set(HttpHeaders.rangeHeader, 'bytes=$offset-')
        ..set(HttpHeaders.acceptEncodingHeader, 'identity');
      final response = await request.close().timeout(
        const Duration(seconds: 30),
      );
      if (response.statusCode != HttpStatus.partialContent) {
        throw _SourceFailure('HTTP ${response.statusCode}');
      }
      final range = _contentRange(response);
      if (int.parse(range.group(1)!) != offset ||
          int.parse(range.group(2)!) != spec.size - 1 ||
          int.parse(range.group(3)!) != spec.size) {
        throw const _SourceFailure('断点范围不匹配');
      }
      final expectedRemaining = spec.size - offset;
      if (response.contentLength >= 0 &&
          response.contentLength != expectedRemaining) {
        throw const _SourceFailure('响应长度不匹配');
      }
      final sink = partial.openWrite(
        mode: offset == 0 ? FileMode.write : FileMode.append,
      );
      var received = offset;
      var lastNotification = DateTime.now();
      try {
        await for (final chunk in response.timeout(
          const Duration(seconds: 30),
        )) {
          if (_cancelled.contains(id)) throw const _SourceFailure('已取消');
          received += chunk.length;
          if (received > spec.size) throw const _SourceFailure('模型文件过大');
          sink.add(chunk);
          progress[id] = received / spec.size;
          if (DateTime.now().difference(lastNotification).inMilliseconds >
              150) {
            lastNotification = DateTime.now();
            notifyListeners();
          }
        }
      } finally {
        await sink.close();
      }
      if (received != spec.size) throw const _SourceFailure('下载未完成');
    } finally {
      _closeClient(id, client);
    }
  }

  Future<void> _activate(
    ModelSpec spec,
    File partial,
    ModelSource? source,
  ) async {
    states[spec.id] = '正在校验…';
    notifyListeners();
    await _verify(spec, partial.path);
    if (_cancelled.contains(spec.id)) throw const _SourceFailure('已取消');
    await partial.rename(path(spec.id));
    await _writeReceipt(spec, source);
    ready.add(spec.id);
    activeSources[spec.id] = source?.label ?? '手动导入';
  }

  Future<void> install(String id, {String? importPath}) async {
    if (progress.containsKey(id)) return;
    final model = spec(id);
    if (!model.runtimeSupported) {
      errors[id] = model.unavailableReason;
      notifyListeners();
      return;
    }
    final previousSource = activeSources[id];
    _cancelled.remove(id);
    errors.remove(id);
    states.remove(id);
    progress[id] = 0;
    notifyListeners();
    if (model.parts.isNotEmpty) {
      await _installBundle(model, importPath: importPath);
      return;
    }
    final partial = File('${path(id)}.part');
    try {
      if (importPath != null) {
        states[id] = '正在导入…';
        notifyListeners();
        await File(importPath).copy(partial.path);
        await _activate(model, partial, null);
        return;
      }
      if (await partial.exists()) {
        final length = await partial.length();
        if (length == model.size) {
          try {
            await _activate(model, partial, null);
            return;
          } catch (_) {
            await partial.delete();
          }
        } else if (length > model.size) {
          await partial.delete();
        }
      }
      final ranked = await _rankSources(id, model);
      Object? lastFailure;
      for (var index = 0; index < ranked.length; index++) {
        if (_cancelled.contains(id)) throw const _SourceFailure('已取消');
        final source = ranked[index];
        activeSources[id] = source.label;
        states[id] = index == 0
            ? '使用${source.label}下载…'
            : '正在切换到${source.label}…';
        notifyListeners();
        try {
          await _downloadFrom(id, model, source, partial);
          await _activate(model, partial, source);
          return;
        } catch (error) {
          lastFailure = error;
          if (_cancelled.contains(id)) rethrow;
          if (await partial.exists() && await partial.length() == model.size) {
            await partial.delete();
          }
        }
      }
      throw lastFailure ?? const _SourceFailure('所有下载源均不可用');
    } catch (error) {
      if (ready.contains(id) && previousSource != null) {
        activeSources[id] = previousSource;
      } else {
        activeSources.remove(id);
      }
      errors[id] = error is FormatException
          ? '模型校验失败，请重新下载或选择正确文件'
          : (_cancelled.contains(id) ? '已取消，可继续下载' : '所有下载源失败，可重试或手动导入');
      if (error is FormatException && await partial.exists()) {
        await partial.delete();
      }
    } finally {
      for (final client in _clients.remove(id) ?? <HttpClient>{}) {
        client.close(force: true);
      }
      progress.remove(id);
      states.remove(id);
      notifyListeners();
    }
  }

  Future<void> _installBundle(ModelSpec model, {String? importPath}) async {
    final id = model.id;
    final partial = Directory('${path(id)}.part');
    try {
      if (importPath != null) throw const _SourceFailure('目录模型不支持单文件导入');
      await partial.create(recursive: true);
      var completed = 0;
      for (final part in model.parts) {
        if (_cancelled.contains(id)) throw const _SourceFailure('已取消');
        final target = File('${partial.path}/${part.file}');
        if (await target.exists() &&
            await target.length() == part.size &&
            (await sha256.bind(target.openRead()).first).toString() ==
                part.hash) {
          completed += part.size;
          progress[id] = completed / model.size;
          continue;
        }
        if (await target.exists() && await target.length() >= part.size) {
          // A complete file with a wrong digest cannot be resumed. Smaller
          // files are retained so retries and source failover continue from
          // the last verified byte boundary instead of restarting multi-GB
          // Qwen weights.
          await target.delete();
        }
        Object? lastFailure;
        for (final source in part.sources) {
          try {
            activeSources[id] = source.label;
            states[id] = '下载 ${part.file}…';
            notifyListeners();
            await _downloadPart(
              id,
              part,
              source,
              target,
              completed,
              model.size,
            );
            final hash = (await sha256.bind(target.openRead()).first)
                .toString();
            if (hash != part.hash) throw const FormatException('模型分片校验失败');
            lastFailure = null;
            break;
          } catch (error) {
            lastFailure = error;
            if (error is FormatException && await target.exists()) {
              await target.delete();
            }
            if (_cancelled.contains(id)) rethrow;
          }
        }
        if (lastFailure != null) throw lastFailure;
        completed += part.size;
      }
      states[id] = '正在校验…';
      await _verify(model, partial.path);
      final destination = Directory(path(id));
      if (await destination.exists()) await destination.delete(recursive: true);
      await partial.rename(destination.path);
      await _writeQwenOverrides(model, destination);
      await _writeReceipt(model, null);
      ready.add(id);
      activeSources[id] = '官方 Thinker-only 文件集';
    } catch (error) {
      errors[id] = _cancelled.contains(id) ? '已取消，可继续下载' : '模型目录下载或校验失败，可重试';
    } finally {
      for (final client in _clients.remove(id) ?? <HttpClient>{}) {
        client.close(force: true);
      }
      progress.remove(id);
      states.remove(id);
      notifyListeners();
    }
  }

  Future<void> _downloadPart(
    String id,
    ModelPart part,
    ModelSource source,
    File target,
    int completed,
    int total,
  ) async {
    final client = _openClient(id);
    try {
      final offset = await target.exists() ? await target.length() : 0;
      if (offset > part.size) throw const _SourceFailure('模型分片过大');
      if (offset == part.size) return;
      final request = await client
          .getUrl(source.url)
          .timeout(const Duration(seconds: 20));
      request.headers
        ..set(HttpHeaders.rangeHeader, 'bytes=$offset-')
        ..set(HttpHeaders.acceptEncodingHeader, 'identity');
      final response = await request.close().timeout(
        const Duration(seconds: 30),
      );
      final completeResponse =
          offset == 0 && response.statusCode == HttpStatus.ok;
      final partialResponse = response.statusCode == HttpStatus.partialContent;
      if (!completeResponse && !partialResponse) {
        throw _SourceFailure('HTTP ${response.statusCode}');
      }
      if (partialResponse) {
        final range = _contentRange(response);
        if (int.parse(range.group(1)!) != offset ||
            int.parse(range.group(2)!) != part.size - 1 ||
            int.parse(range.group(3)!) != part.size) {
          throw const _SourceFailure('下载源文件大小不匹配');
        }
      } else if (response.contentLength >= 0 &&
          response.contentLength != part.size) {
        throw const _SourceFailure('下载源文件大小不匹配');
      }
      final sink = target.openWrite(
        mode: offset == 0 ? FileMode.write : FileMode.append,
      );
      var received = offset;
      try {
        await for (final chunk in response.timeout(
          const Duration(seconds: 30),
        )) {
          if (_cancelled.contains(id)) throw const _SourceFailure('已取消');
          received += chunk.length;
          if (received > part.size) throw const _SourceFailure('模型分片过大');
          sink.add(chunk);
          progress[id] = (completed + received) / total;
          notifyListeners();
        }
      } finally {
        await sink.close();
      }
      if (received != part.size) throw const _SourceFailure('模型分片不完整');
    } finally {
      _closeClient(id, client);
    }
  }

  Future<void> _writeQwenOverrides(ModelSpec model, Directory directory) async {
    if (model.id != 'qwen2.5-omni-3b-mnn') return;
    final config =
        jsonDecode(await File('${directory.path}/config.json').readAsString())
            as Map<String, dynamic>;
    config['llm_config'] = 'opencaption_llm_config.json';
    config['system_prompt'] =
        'Return English transcription and Mainland China Simplified Chinese (简体中文, zh-CN) translation only. '
        'Do NOT output Traditional Chinese (繁體中文). Never generate speech or reasoning.';
    await File(
      '${directory.path}/opencaption_config.json',
    ).writeAsString(jsonEncode(config), flush: true);
    final llm =
        jsonDecode(
              await File('${directory.path}/llm_config.json').readAsString(),
            )
            as Map<String, dynamic>;
    llm['is_visual'] = false;
    llm['has_talker'] = false;
    llm['backend_type'] = 'opencl';
    llm['thread_num'] = 4;
    await File(
      '${directory.path}/opencaption_llm_config.json',
    ).writeAsString(jsonEncode(llm), flush: true);
  }

  void cancel(String id) {
    _cancelled.add(id);
    for (final client in List<HttpClient>.of(
      _clients[id] ?? const <HttpClient>{},
    )) {
      client.close(force: true);
    }
  }

  Future<void> delete(String id) async {
    if (progress.containsKey(id)) return;
    for (final suffix in ['', '.part', '.verified']) {
      final file = File('${path(id)}$suffix');
      final directory = Directory('${path(id)}$suffix');
      if (await file.exists()) await file.delete();
      if (await directory.exists()) await directory.delete(recursive: true);
    }
    ready.remove(id);
    activeSources.remove(id);
    errors.remove(id);
    notifyListeners();
  }
}

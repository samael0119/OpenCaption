import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/models/model_store.dart';

void main() {
  late Directory temp;
  late ModelStore store;
  final servers = <HttpServer>[];
  final bytes = <int>[1, 2, 3, 4];

  ModelSpec fixture({List<Map<String, String>>? sources, List<int>? data}) {
    final contents = data ?? bytes;
    return ModelSpec({
      'id': 'fixture',
      'file': 'model.bin',
      'label': 'test',
      'kind': 'asr',
      'size': contents.length,
      'sha256': sha256.convert(contents).toString(),
      'sources':
          sources ??
          [
            {
              'id': 'fixture-source',
              'label': '测试源',
              'url': 'https://example.invalid/model.bin',
            },
          ],
    }, allowInsecureSources: sources != null);
  }

  Future<Uri> startServer(
    FutureOr<void> Function(HttpRequest request) handler,
  ) async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    servers.add(server);
    server.listen(handler);
    return Uri.parse('http://127.0.0.1:${server.port}/model.bin');
  }

  Future<void> serveRange(HttpRequest request, List<int> data) async {
    final header = request.headers.value(HttpHeaders.rangeHeader) ?? '';
    final match = RegExp(r'^bytes=(\d+)-(\d*)$').firstMatch(header);
    if (match == null) {
      request.response.statusCode = HttpStatus.badRequest;
      await request.response.close();
      return;
    }
    final start = int.parse(match.group(1)!);
    final end = match.group(2)!.isEmpty
        ? data.length - 1
        : int.parse(match.group(2)!);
    request.response
      ..statusCode = HttpStatus.partialContent
      ..headers.set(
        HttpHeaders.contentRangeHeader,
        'bytes $start-$end/${data.length}',
      )
      ..contentLength = end - start + 1
      ..add(data.sublist(start, end + 1));
    await request.response.close();
  }

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('opencaption-model-test-');
    store = ModelStore(probeBytes: 2)
      ..directory = temp
      ..catalog = [fixture()];
  });

  tearDown(() async {
    store.dispose();
    for (final server in servers) {
      await server.close(force: true);
    }
    servers.clear();
    await temp.delete(recursive: true);
  });

  Future<void> importModel(List<int> data) async {
    final source = File('${temp.path}/source.bin');
    await source.writeAsBytes(data);
    await store.install('fixture', importPath: source.path);
  }

  test(
    'verified import activates model and deletion removes its receipt',
    () async {
      await importModel(bytes);
      expect(store.ready, contains('fixture'));
      final receiptFile = File('${store.path('fixture')}.verified');
      expect(await receiptFile.exists(), isTrue);
      final receipt = jsonDecode(await receiptFile.readAsString());
      expect(receipt['sourceId'], 'manual-import');
      await store.verifyForUse('fixture');
      await store.delete('fixture');
      expect(store.ready, isEmpty);
      expect(await receiptFile.exists(), isFalse);
    },
  );

  test('same-size wrong hash never replaces a valid model', () async {
    await importModel(bytes);
    await importModel([4, 3, 2, 1]);
    expect(store.errors['fixture'], contains('校验失败'));
    expect(await File(store.path('fixture')).readAsBytes(), bytes);
    expect(await File('${store.path('fixture')}.part').exists(), isFalse);
  });

  test('startup integrity check rejects corruption after import', () async {
    await importModel(bytes);
    await File(store.path('fixture')).writeAsBytes([0, 0, 0, 0]);
    await expectLater(store.verifyForUse('fixture'), throwsFormatException);
    expect(store.ready, isEmpty);
  });

  test('selects the fastest valid source', () async {
    final slow = await startServer((request) async {
      if (request.headers.value(HttpHeaders.rangeHeader) == 'bytes=0-1') {
        await Future<void>.delayed(const Duration(milliseconds: 80));
      }
      await serveRange(request, bytes);
    });
    final fast = await startServer((request) => serveRange(request, bytes));
    store.catalog = [
      fixture(
        sources: [
          {'id': 'slow', 'label': '慢源', 'url': slow.toString()},
          {'id': 'fast', 'label': '快源', 'url': fast.toString()},
        ],
      ),
    ];

    await store.install('fixture');

    expect(store.ready, contains('fixture'));
    expect(store.activeSources['fixture'], '快源');
    expect(await File(store.path('fixture')).readAsBytes(), bytes);
  });

  test('switches source and resumes an existing partial file', () async {
    final failed = await startServer((request) async {
      if (request.headers.value(HttpHeaders.rangeHeader) == 'bytes=0-1') {
        await serveRange(request, bytes);
      } else {
        request.response.statusCode = HttpStatus.serviceUnavailable;
        await request.response.close();
      }
    });
    String? resumedRange;
    final backup = await startServer((request) async {
      if (request.headers.value(HttpHeaders.rangeHeader) == 'bytes=0-1') {
        await Future<void>.delayed(const Duration(milliseconds: 60));
      } else {
        resumedRange = request.headers.value(HttpHeaders.rangeHeader);
      }
      await serveRange(request, bytes);
    });
    store.catalog = [
      fixture(
        sources: [
          {'id': 'failed', 'label': '故障源', 'url': failed.toString()},
          {'id': 'backup', 'label': '备用源', 'url': backup.toString()},
        ],
      ),
    ];
    await File(
      '${store.path('fixture')}.part',
    ).writeAsBytes(bytes.take(2).toList());

    await store.install('fixture');

    expect(resumedRange, 'bytes=2-');
    expect(store.activeSources['fixture'], '备用源');
    expect(await File(store.path('fixture')).readAsBytes(), bytes);
  });

  test(
    'bundle accepts a full 200 response on its first ModelScope request',
    () async {
      final source = await startServer((request) async {
        expect(request.headers.value(HttpHeaders.rangeHeader), 'bytes=0-');
        request.response
          ..statusCode = HttpStatus.ok
          ..contentLength = bytes.length
          ..add(bytes);
        await request.response.close();
      });
      store.catalog = [
        ModelSpec({
          'id': 'fixture-bundle',
          'file': 'fixture-bundle',
          'label': 'bundle',
          'kind': 'e2e-test',
          'size': bytes.length,
          'sha256': 'directory',
          'sources': [
            {'id': 'modelscope', 'label': '魔搭', 'url': source.toString()},
          ],
          'files': [
            {
              'file': 'part.bin',
              'size': bytes.length,
              'sha256': sha256.convert(bytes).toString(),
              'sources': [
                {'id': 'modelscope', 'label': '魔搭', 'url': source.toString()},
              ],
            },
          ],
        }, allowInsecureSources: true),
      ];

      await store.install('fixture-bundle');

      expect(store.ready, contains('fixture-bundle'));
      expect(
        await File('${store.path('fixture-bundle')}/part.bin').readAsBytes(),
        bytes,
      );
    },
  );

  test('rejects malformed range metadata and uses another source', () async {
    final malformed = await startServer((request) async {
      request.response
        ..statusCode = HttpStatus.partialContent
        ..headers.set(HttpHeaders.contentRangeHeader, 'bytes 0-1/999')
        ..contentLength = 2
        ..add(bytes.take(2).toList());
      await request.response.close();
    });
    final valid = await startServer((request) => serveRange(request, bytes));
    store.catalog = [
      fixture(
        sources: [
          {'id': 'bad', 'label': '错误源', 'url': malformed.toString()},
          {'id': 'good', 'label': '有效源', 'url': valid.toString()},
        ],
      ),
    ];

    await store.install('fixture');

    expect(store.ready, contains('fixture'));
    expect(store.activeSources['fixture'], '有效源');
  });

  test('reports failure when no source passes the probe', () async {
    final unavailable = await startServer((request) async {
      request.response.statusCode = HttpStatus.serviceUnavailable;
      await request.response.close();
    });
    store.catalog = [
      fixture(
        sources: [
          {'id': 'down', 'label': '不可用源', 'url': unavailable.toString()},
        ],
      ),
    ];

    await store.install('fixture');

    expect(store.ready, isEmpty);
    expect(store.errors['fixture'], contains('所有下载源失败'));
  });
}

import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/translation.dart';

void main() {
  test(
    'HTTPS by default, explicit private HTTP, reject credentials and fragments',
    () {
      expect(
        () => const ServiceConfig(
          baseUrl: 'http://example.com/v1',
          model: 'm',
          allowLocalHttp: true,
        ).endpoint,
        throwsA(isA<TranslationFailure>()),
      );
      expect(
        () => const ServiceConfig(
          baseUrl: 'http://192.168.1.3/v1',
          model: 'm',
        ).endpoint,
        throwsA(isA<TranslationFailure>()),
      );
      expect(
        const ServiceConfig(
          baseUrl: 'http://192.168.1.3/v1/',
          model: 'm',
          allowLocalHttp: true,
        ).endpoint.path,
        '/v1/chat/completions',
      );
      expect(
        () => const ServiceConfig(
          baseUrl: 'https://user:secret@example.com/v1',
          model: 'm',
        ).endpoint,
        throwsA(isA<TranslationFailure>()),
      );
      expect(
        () => const ServiceConfig(
          baseUrl: 'https://example.com/v1#x',
          model: 'm',
        ).endpoint,
        throwsA(isA<TranslationFailure>()),
      );
    },
  );
  test(
    'sends text-only request, parses response and enforces subsequent soft budget',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final translator = ExternalTranslator();
      addTearDown(() async {
        translator.cancelAll();
        await server.close(force: true);
      });
      final config = ServiceConfig(
        baseUrl: 'http://127.0.0.1:${server.port}/v1',
        model: 'test',
        allowLocalHttp: true,
        tokenBudget: 5,
      );
      server.listen((request) async {
        expect(request.uri.path, '/v1/chat/completions');
        expect(request.headers.value('authorization'), isNull);
        final body = jsonDecode(await utf8.decoder.bind(request).join()) as Map;
        expect(body.keys.toSet(), {'model', 'messages', 'stream'});
        expect(body['stream'], false);
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode({
            'choices': [
              {
                'message': {'content': '我们决定保枪。'},
                'finish_reason': 'stop',
              },
            ],
            'usage': {'total_tokens': 8},
          }),
        );
        await request.response.close();
      });
      expect(
        (await translator.translate(
          '1',
          '{"CURRENT":"We decided to save."}',
          config,
        )).text,
        '我们决定保枪。',
      );
      expect(translator.tokens, 8);
      await expectLater(
        translator.translate('2', '{}', config),
        throwsA(isA<TranslationFailure>()),
      );
    },
  );
  for (final code in [401, 403, 429, 503, 302]) {
    test('HTTP $code is not shown as translated text', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final client = ExternalTranslator();
      addTearDown(() async {
        client.cancelAll();
        await server.close(force: true);
      });
      server.listen((request) async {
        await request.drain<void>();
        request.response.statusCode = code;
        request.response.write('private server detail');
        await request.response.close();
      });
      await expectLater(
        client.translate(
          'id',
          '{}',
          ServiceConfig(
            baseUrl: 'http://127.0.0.1:${server.port}',
            model: 'm',
            allowLocalHttp: true,
          ),
        ),
        throwsA(isA<TranslationFailure>()),
      );
      expect(client.stopped, code == 401 || code == 403);
    });
  }
  test('does not accept truncated translation', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final client = ExternalTranslator();
    addTearDown(() async {
      client.cancelAll();
      await server.close(force: true);
    });
    server.listen((r) async {
      await r.drain<void>();
      r.response.write(
        jsonEncode({
          'choices': [
            {
              'message': {'content': '半句'},
              'finish_reason': 'length',
            },
          ],
        }),
      );
      await r.response.close();
    });
    await expectLater(
      client.translate(
        'id',
        '{}',
        ServiceConfig(
          baseUrl: 'http://127.0.0.1:${server.port}',
          model: 'm',
          allowLocalHttp: true,
        ),
      ),
      throwsA(
        isA<TranslationFailure>().having(
          (e) => e.code,
          'code',
          'truncated_translation',
        ),
      ),
    );
  });
}

import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/translation.dart';

void main() {
  test(
    'numeric caption exception keeps ordinary translation validation strict',
    () {
      expect(parseTranslationText('12-11', allowNumeric: true), '12-11');
      expect(
        () => parseTranslationText('12-11'),
        throwsA(isA<TranslationFailure>()),
      );
      for (final value in [
        '...',
        '[12]',
        '[NONE]',
        '111111111',
        'Explanation: 12',
      ]) {
        expect(
          () => parseTranslationText(value, allowNumeric: true),
          throwsA(isA<TranslationFailure>()),
        );
      }
    },
  );

  test(
    'literal names require a registry and do not accept copied sentences',
    () {
      expect(
        parseTranslationText('donk', preservedIdentifiers: {'donk'}),
        'donk',
      );
      expect(
        () => parseTranslationText('donk'),
        throwsA(isA<TranslationFailure>()),
      );
      expect(
        () => parseTranslationText(
          'donk is here',
          preservedIdentifiers: {'donk'},
        ),
        throwsA(isA<TranslationFailure>()),
      );
      expect(
        () => parseTranslationText('NiKo', preservedIdentifiers: {'donk'}),
        throwsA(isA<TranslationFailure>()),
      );
    },
  );
}

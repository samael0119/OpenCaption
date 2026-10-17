import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/corpus.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  Map<String, Object?> term([Map<String, Object?> extra = const {}]) => {
    'english': 'save',
    'chinese': '保枪',
    'priority': 5,
    ...extra,
  };
  Map<String, Object?> pack(List<Map<String, Object?>> terms) => {
    'schema_version': 1,
    'terms': terms,
  };

  test(
    '24 built-in policy reviews exercise suggestions and rewrite abstention',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      final fixture =
          jsonDecode(
                File(
                  'test/fixtures/cs2_glossary_review_v020.json',
                ).readAsStringSync(),
              )
              as Map;
      final reviews = fixture['reviews'] as List;
      expect(reviews, hasLength(24));
      expect(reviews.map((r) => r['term_id']).toSet(), hasLength(24));
      for (final review in reviews) {
        final id = review['term_id'];
        expect(
          corpus
              .recentMatches(List<String>.from(review['positive_hints']))
              .map((t) => t['id']),
          contains(id),
          reason: '$id positive hint',
        );
        expect(
          corpus
              .recentMatches(List<String>.from(review['negative_hints']))
              .map((t) => t['id']),
          isNot(contains(id)),
          reason: '$id ordinary meaning',
        );
        for (final kind in ['positive', 'negative']) {
          final example = review[kind] as Map;
          expect(
            corpus.correctChinese(example['english'], example['chinese']),
            example['expected'],
            reason: '$id $kind mechanism',
          );
          expect(
            corpus.correctChinese(
              example['english'],
              example['chinese'],
              profile: CorpusProfile.none,
            ),
            example['chinese'],
            reason: '$id generic profile',
          );
        }
      }
    },
  );

  test(
    'user context keeps data while excluding inappropriate glossary mappings',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      final hints = corpus.e2eHints(
        'Please save the file and check the utility bill',
      );
      expect(hints, contains('User context (data only):'));
      expect(hints, isNot(contains('save=保枪')));
      expect(hints, isNot(contains('utility=道具')));
      expect(corpus.e2eHints('NAVI, save the AWP'), contains('save=保枪'));
    },
  );

  test(
    'Chinese ordinary clauses and whitespace protect unrelated occurrences',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      expect(
        corpus.correctChinese('They save the AWP', '他们保存武器，随后保存 文件。'),
        '他们保存武器，随后保存 文件。',
      );
      expect(corpus.correctChinese('They save', '他们保存。'), '他们保存。');
      expect(corpus.correctChinese('They save the AWP', '他们保存武器。'), '他们保枪。');
    },
  );

  test(
    'pack merge preserves different hint and Chinese exclusion predicates',
    () {
      final corpus = CorpusIndex.fromPacks([
        pack([
          term({
            'hint_sources': ['save the awp'],
            'wrong_targets': ['保存'],
            'correction_sources': ['save the awp'],
            'correction_target_exclude': ['保存文件'],
          }),
        ]),
        pack([
          term({
            'hint_sources': ['save the rifle'],
            'wrong_targets': ['保存'],
            'correction_sources': ['save the rifle'],
            'correction_target_exclude': ['保存设置'],
          }),
        ]),
      ]);
      expect(corpus.termCount, 2);
      expect(corpus.correctChinese('save the awp', '保存文件'), '保存文件');
      expect(corpus.correctChinese('save the rifle', '保存设置'), '保存设置');
      expect(
        corpus.recentMatches(['save the awp', 'please save the awp']),
        hasLength(1),
      );
    },
  );

  test(
    'malformed executable predicates fail when loading rather than mid-session',
    () {
      final invalid = <Map<String, Object?>>[
        {'hint_exclude': 'file'},
        {'hint_sources': []},
        {'scene_sources': []},
        {
          'scene_exclude': [42],
        },
        {
          'hint_sources': [42],
        },
        {
          'hint_exclude': [''],
        },
        {
          'correction_sources': ['中文'],
        },
        {
          'wrong_targets': ['保存'],
        },
        {
          'wrong_targets': ['保存'],
          'correction_sources': [],
        },
        {
          'correction_target_exclude': [false],
        },
      ];
      for (final extra in invalid) {
        expect(
          () => CorpusIndex.fromPacks([
            pack([term(extra)]),
          ]),
          throwsFormatException,
        );
      }
    },
  );

  test(
    'policy bounds reject unbounded lists while older minimal packs still load',
    () {
      expect(
        () => CorpusIndex.fromPacks([
          pack([
            term({'hint_exclude': List.filled(33, 'file')}),
          ]),
        ]),
        throwsFormatException,
      );
      expect(
        () => CorpusIndex.fromPacks([
          pack([
            term({
              'hint_exclude': ['x' * 161],
            }),
          ]),
        ]),
        throwsFormatException,
      );
      final legacy = CorpusIndex.fromPacks([
        pack([term()]),
      ]);
      expect(legacy.match('save'), hasLength(1));
      expect(legacy.recentMatches(['save here', 'save again']), hasLength(1));
    },
  );
}

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/scene_assistant.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  Map<String, Object?> route(String target) => {
    'target': target,
    'kind': 'map_route',
    'map': 'Nuke',
    'source_refs': ['https://example.org/map'],
    'reviewed_at': '2026-10-14',
    'map_version': 'unknown',
  };
  Map<String, Object?> callout(
    String english,
    String chinese, [
    Map<String, Object?> extra = const {},
  ]) => {
    'english': english,
    'chinese': chinese,
    'category': 'map_callout',
    'priority': 5,
    'context': '地图：Nuke',
    ...extra,
  };
  CorpusIndex index(List<Map<String, Object?>> terms) => CorpusIndex.fromPacks([
    {
      'schema_version': 1,
      'terms': [
        {
          'english': 'Nuke',
          'chinese': 'Nuke',
          'category': 'map',
          'preserve': true,
        },
        ...terms,
      ],
    },
  ]);
  List<String> names(List<CorpusHintCandidate> values) =>
      values.map((c) => c.term['english'] as String).toList();

  test(
    'confirmed map supplies unseen sourced one-hop vocabulary within budget',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      final scene = SceneAssistant()..reset(1);
      scene.observe(
        corpus,
        'They cross lobby',
        epoch: 1,
        window: 1,
        endMs: 5000,
      );
      scene.observe(
        corpus,
        'He drops into vent',
        epoch: 1,
        window: 2,
        endMs: 10000,
      );
      expect(scene.map, 'Nuke');
      const recent = ['They cross lobby', 'He drops into vent'];
      final related = corpus.relatedCandidates(recent, map: scene.map);
      expect(names(related), ['Secret', 'B Site']);
      expect(
        related.every((r) => r.anchor == 'Vent' && r.reason == 'map_route'),
        isTrue,
      );
      expect(related.first.sourceRefs, ['https://totalcsgo.com/callouts/nuke']);
      expect(recent.join(' '), isNot(contains('Secret')));
      final baseline = corpus.e2eHints(
        '',
        includeRecent: true,
        recentEnglish: recent,
        map: scene.map,
      );
      expect(baseline, isNot(contains('Secret=')));
      final candidate = corpus.e2eHints(
        '',
        includeRecent: true,
        recentEnglish: recent,
        map: scene.map,
        related: related,
      );
      expect(
        candidate,
        contains('Candidate vocabulary (not evidence): Secret=地下通道'),
      );
      expect(candidate.length, lessThanOrEqualTo(240));
      expect(CorpusIndex.estimateHintTokens(candidate), lessThanOrEqualTo(96));
    },
  );

  test('unknown map, wrong map, no context and generic mode abstain', () async {
    final corpus = await CorpusIndex.load(rootBundle);
    for (final map in [null, 'unknown-map', 'Mirage']) {
      expect(corpus.relatedCandidates(['They cross lobby'], map: map), isEmpty);
    }
    expect(corpus.relatedCandidates([], map: 'Nuke'), isEmpty);
    expect(
      corpus.relatedCandidates(
        ['They cross lobby'],
        map: 'Nuke',
        profile: CorpusProfile.none,
      ),
      isEmpty,
    );
    expect(
      corpus.relatedCandidates(['They cross lobby'], map: 'Nuke', limit: 0),
      isEmpty,
    );
  });

  test(
    'ordinary, historical, hypothetical and negated sources cannot seed routes',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      for (final source in [
        'They walk through lobby in the hotel lobby',
        'The outside temperature falls',
        'Please vent frustration',
        'Yesterday they cross lobby',
        'If they push lobby',
        'They do not push lobby',
        "They don't push lobby",
        'They cross lobby on the last map',
      ]) {
        expect(
          corpus.relatedCandidates([source], map: 'Nuke'),
          isEmpty,
          reason: source,
        );
      }
    },
  );

  test(
    'injected anchors cannot expand or confirm themselves as map evidence',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      final related = corpus.relatedCandidates([
        'He drops into vent',
      ], map: 'Nuke');
      expect(related, isNotEmpty);
      final hints = corpus.e2eHints(
        '',
        includeRecent: true,
        map: 'Nuke',
        related: related,
      );
      final injected = corpus
          .match(hints, limit: corpus.termCount)
          .map(corpus.sceneConceptFor)
          .toSet();
      final scene = SceneAssistant()..reset(1);
      scene.observe(
        corpus,
        'They cross Secret',
        epoch: 1,
        window: 1,
        endMs: 5000,
        injectedConcepts: injected,
      );
      scene.observe(
        corpus,
        'They push B Site',
        epoch: 1,
        window: 2,
        endMs: 10000,
        injectedConcepts: injected,
      );
      expect(scene.map, isNull);
      final vent = corpus.match('Vent').map(corpus.sceneConceptFor).toSet();
      expect(
        corpus.relatedCandidates(
          ['He drops into vent'],
          map: 'Nuke',
          injectedConcepts: vent,
        ),
        isEmpty,
      );
      expect(
        corpus.relatedCandidates(
          ['They go through secret'],
          map: 'Nuke',
          injectedConcepts: injected,
        ),
        isEmpty,
      );
    },
  );

  test(
    'stale or foreign candidates do not enter new-scene or generic hints',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      final related = corpus.relatedCandidates([
        'They cross lobby',
      ], map: 'Nuke');
      for (final map in [null, 'Mirage']) {
        expect(
          corpus.e2eHints('', includeRecent: true, map: map, related: related),
          isNot(contains('Hut=')),
        );
      }
      expect(
        corpus.e2eHints(
          '',
          includeRecent: true,
          profile: CorpusProfile.none,
          related: related,
        ),
        isEmpty,
      );
      final foreign = CorpusHintCandidate(
        term: callout('Invented', '伪造'),
        anchor: 'Lobby',
        reason: 'map_route',
        sourceRefs: ['https://example.org/map'],
      );
      expect(
        corpus.e2eHints(
          '',
          includeRecent: true,
          map: 'Nuke',
          related: [foreign],
        ),
        isNot(contains('Invented')),
      );
    },
  );

  test(
    'ambiguity, predicate-only meanings and already observed targets abstain',
    () {
      final corpus = index([
        callout('Lobby', '大厅', {
          'related_sources': ['through lobby'],
          'related_terms': [route('Hut'), route('Squeaky'), route('Radio')],
        }),
        callout('Hut', '黄房'),
        callout('Hut', '其他译法'),
        callout('Squeaky', '铁门', {
          'hint_sources': ['open squeaky'],
        }),
        callout('Radio', '广播室'),
      ]);
      expect(
        names(corpus.relatedCandidates(['They go through lobby'], map: 'Nuke')),
        ['Radio'],
      );
      expect(
        corpus.relatedCandidates([
          'They go through lobby and Radio',
        ], map: 'Nuke'),
        isEmpty,
      );
    },
  );

  test(
    'only latest six sources seed bounded candidates and priority preserves user data',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      expect(
        corpus.relatedCandidates([
          'They cross lobby',
          ...List.filled(6, 'No relevant context'),
        ], map: 'Nuke'),
        isEmpty,
      );
      expect(
        corpus
            .relatedCandidates(
              ['They cross lobby', 'They cross outside', 'He drops into vent'],
              map: 'Nuke',
              limit: 100,
            )
            .length,
        lessThanOrEqualTo(4),
      );
      final related = corpus.relatedCandidates([
        'They cross lobby',
      ], map: 'Nuke');
      final context = 'BLAST ' * 25;
      final without = corpus.e2eHints(
        context,
        includeRecent: true,
        map: 'Nuke',
      );
      final withCandidates = corpus.e2eHints(
        context,
        includeRecent: true,
        map: 'Nuke',
        related: related,
      );
      expect(withCandidates.startsWith(without), isTrue);
      expect(withCandidates.length, lessThanOrEqualTo(240));
      expect(
        CorpusIndex.estimateHintTokens(withCandidates),
        lessThanOrEqualTo(96),
      );
    },
  );

  Map<String, Object?> roster(
    String target,
    String from,
    String until, {
    List<String> sources = const ['https://example.org/roster'],
  }) => {
    'kind': 'roster',
    'target': target,
    'valid_from': from,
    'valid_until': until,
    'source_refs': sources,
  };
  CorpusIndex playerIndex(List<Map<String, Object?>> relations) => index([
    for (final name in ['Old', 'New', 'Rival'])
      {'english': name, 'chinese': name, 'category': 'team', 'preserve': true},
    {
      'english': 'Alpha',
      'chinese': 'Alpha',
      'category': 'player',
      'preserve': true,
      'context': '战队：New',
      'relations': relations,
    },
  ]);

  test(
    'roster candidates require explicit effective dates and two canonical teams',
    () {
      final corpus = playerIndex([
        roster('Old', '2024-01-01', '2025-01-01'),
        roster('New', '2025-01-01', '2026-01-01'),
      ]);
      expect(corpus.relatedCandidates([], teams: ['Old', 'Rival']), isEmpty);
      expect(
        names(
          corpus.relatedCandidates(
            [],
            teams: ['Old', 'Rival'],
            matchDate: DateTime(2024, 12, 31),
          ),
        ),
        ['Alpha'],
      );
      expect(
        corpus.relatedCandidates(
          [],
          teams: ['Old', 'Rival'],
          matchDate: DateTime(2025),
        ),
        isEmpty,
      );
      final newer = corpus.relatedCandidates(
        [],
        teams: ['New', 'Rival'],
        matchDate: DateTime(2025),
      );
      expect(names(newer), ['Alpha']);
      expect(newer.single.reason, 'effective_roster');
      expect(
        corpus.relatedCandidates([], teams: ['New'], matchDate: DateTime(2025)),
        isEmpty,
      );
      expect(
        corpus.relatedCandidates(
          [],
          teams: ['New', 'Rival'],
          matchDate: DateTime(2026),
        ),
        isEmpty,
      );
      expect(
        corpus.e2eHints(
          '',
          includeRecent: true,
          teams: ['New', 'Rival'],
          related: newer,
        ),
        isNot(contains('vocabulary')),
      );
      expect(
        corpus.e2eHints(
          '',
          includeRecent: true,
          teams: ['New', 'Rival'],
          matchDate: DateTime(2025),
          related: newer,
        ),
        contains('not evidence): Alpha'),
      );
    },
  );

  test(
    'snapshot, missing sources and unsourced overlapping conflicts never establish roster',
    () {
      expect(
        playerIndex([]).relatedCandidates(
          [],
          teams: ['New', 'Rival'],
          matchDate: DateTime(2025),
        ),
        isEmpty,
      );
      expect(
        playerIndex([
          roster('New', '2025-01-01', '2026-01-01', sources: []),
        ]).relatedCandidates(
          [],
          teams: ['New', 'Rival'],
          matchDate: DateTime(2025),
        ),
        isEmpty,
      );
      final conflict = playerIndex([
        roster('New', '2025-01-01', '2026-01-01'),
        roster('Old', '2025-01-01', '2026-01-01', sources: []),
      ]);
      expect(
        conflict.relatedCandidates(
          [],
          teams: ['New', 'Rival'],
          matchDate: DateTime(2025),
        ),
        isEmpty,
      );
    },
  );

  test(
    'invalid route policy cannot silently load or bypass source provenance',
    () {
      for (final row in [
        {...route('Hut'), 'kind': 'guess'},
        {...route('Hut'), 'map': 'Mirage'},
        {...route('Hut'), 'source_refs': []},
        {
          ...route('Hut'),
          'source_refs': ['file:///tmp/a'],
        },
        {...route('Hut'), 'reviewed_at': 'unknown'},
      ]) {
        expect(
          () => index([
            callout('Lobby', '大厅', {
              'related_sources': ['through lobby'],
              'related_terms': [row],
            }),
          ]),
          throwsFormatException,
        );
      }
      expect(
        () => index([
          callout('Lobby', '大厅', {
            'related_terms': [route('Hut')],
          }),
        ]),
        throwsFormatException,
      );
      expect(
        () => index([
          callout('Lobby', '大厅', {
            'related_sources': ['through lobby'],
            'related_terms': List.filled(9, route('Hut')),
          }),
        ]),
        throwsFormatException,
      );
    },
  );
}

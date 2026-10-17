import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/scene_assistant.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('strategic default cannot block valid Nuke callout evidence', () async {
    final bundled = await CorpusIndex.load(rootBundle);
    final state = SceneAssistant()..reset(1);
    state.observe(
      bundled,
      'They play default',
      epoch: 1,
      window: 1,
      endMs: 5000,
    );
    state.observe(
      bundled,
      'They cross lobby',
      epoch: 1,
      window: 2,
      endMs: 10000,
    );
    state.observe(
      bundled,
      'He drops into vent',
      epoch: 1,
      window: 3,
      endMs: 15000,
    );
    expect(state.map, 'Nuke');
  });
  final corpus = CorpusIndex.fromPacks([
    {
      'schema_version': 1,
      'terms': [
        for (final row in [
          ['Lobby', 'Nuke'],
          ['Vent', 'Nuke'],
          ['Vent', 'Cache'],
          ['Palace', 'Mirage'],
          ['Connector', 'Mirage'],
        ])
          {
            'english': row[0],
            'chinese': row[0],
            'category': 'map_callout',
            'context': '地图：${row[1]}',
            'aliases': row[0] == 'Vent' ? ['Vents'] : [],
            'priority': 5,
          },
        for (final map in ['Nuke', 'Mirage'])
          {'english': map, 'chinese': map, 'category': 'map'},
        for (final team in ['NAVI', 'FaZe'])
          {
            'english': team,
            'chinese': team,
            'category': 'team',
            'preserve': true,
          },
        {
          'english': 'ropz',
          'chinese': 'ropz',
          'category': 'player',
          'context': '战队：Vitality',
        },
      ],
    },
  ]);
  late SceneAssistant scene;
  void observe(
    String text,
    int window, {
    int? at,
    Set<String> injected = const {},
  }) => scene.observe(
    corpus,
    text,
    epoch: 1,
    window: window,
    endMs: at ?? window * 5000,
    injectedConcepts: injected,
  );
  setUp(() => scene = SceneAssistant()..reset(1));

  // Synthetic relationships, not assertions about an actual team's roster.
  final rosterCorpus = CorpusIndex.fromPacks([
    {
      'schema_version': 1,
      'provenance': {'snapshot': '2024-01-01'},
      'terms': [
        for (final team in ['TeamA', 'TeamB', 'TeamC'])
          {'english': team, 'chinese': team, 'category': 'team'},
        for (final row in [
          ['p1', 'TeamA'],
          ['p2', 'TeamA'],
          ['q1', 'TeamB'],
          ['q2', 'TeamB'],
        ])
          {
            'english': row[0],
            'chinese': row[0],
            'category': 'player',
            'context': '战队：${row[1]}',
          },
      ],
    },
  ]);

  void rosterObserve(
    String text,
    int window, {
    int? at,
    Set<String> injected = const {},
  }) => scene.observe(
    rosterCorpus,
    text,
    epoch: 1,
    window: window,
    endMs: at ?? window * 5000,
    injectedConcepts: injected,
  );

  test('unknown academy affiliation never confirms the parent team', () {
    rosterObserve('p1 plays for TeamA academy', 1);
    rosterObserve('p2 from TeamA esports academy attacks', 2);
    rosterObserve('TeamB holds the site', 3);
    rosterObserve('TeamB gets the trade', 4);
    expect(scene.teams, isEmpty);
    scene.advanceClock(120000);
    rosterObserve('p1 moves outside', 5, at: 125000);
    rosterObserve('p2 finds a kill', 6, at: 130000);
    expect(scene.teams, isEmpty);
  });

  test('hypothetical affiliations cannot vote as direct current teams', () {
    rosterObserve('If p1 plays for TeamC', 1);
    rosterObserve('Imagine p2 from TeamC attacks', 2);
    rosterObserve('TeamB holds the site', 3);
    rosterObserve('TeamB gets the trade', 4);
    expect(scene.teams, isEmpty);
    scene.advanceClock(120000);
    rosterObserve('p1 moves outside', 5, at: 125000);
    rosterObserve('p2 finds a kill', 6, at: 130000);
    expect(scene.teamCandidates, ['TeamA']);
  });

  test('hypothetical map cues abstain while the current clause can vote', () {
    observe('If they enter lobby', 1);
    observe('Imagine they drop vent', 2);
    expect(scene.map, isNull);
    observe('Suppose he drops vent but now they cross lobby', 3);
    observe('Now the vent is occupied', 4);
    expect(scene.map, 'Nuke');
  });

  test('ordinary tactical predictions retain direct current-team evidence', () {
    observe('NAVI could win this round', 1);
    observe('FaZe might save their rifles', 2);
    observe('NAVI could trade here', 3);
    observe('FaZe can still defend', 4);
    expect(scene.teams, ['FaZe', 'NAVI']);
  });

  void learnMemberships() {
    rosterObserve('p1 plays for TeamA', 1);
    rosterObserve('p2 from TeamA takes the kill', 2);
    rosterObserve('q1 is playing for TeamB', 3);
    rosterObserve('q2 of TeamB defends', 4);
  }

  test(
    'current affiliation denial retracts learned support and stale snapshot',
    () {
      learnMemberships();
      expect(scene.teams, ['TeamA', 'TeamB']);
      rosterObserve('p1 no longer plays for TeamA', 5);
      rosterObserve('p2 is not playing for TeamA', 6);
      expect(scene.teams, isEmpty);
      scene.advanceClock(120000);
      rosterObserve('p1 moves outside', 7, at: 125000);
      rosterObserve('p2 finds a kill', 8, at: 130000);
      expect(scene.teamCandidates, isEmpty);
      expect(scene.teams, isEmpty);
    },
  );

  test('later explicit current affiliations can recover from retraction', () {
    learnMemberships();
    rosterObserve('p1 no longer plays for TeamA', 5);
    rosterObserve('p2 is not playing for TeamA', 6);
    expect(scene.teams, isEmpty);
    rosterObserve('p1 is playing for TeamA again', 7);
    rosterObserve('p2 from TeamA takes a kill', 8);
    expect(scene.teams, ['TeamA', 'TeamB']);
  });

  test(
    'unknown academy denial must not retract a learned senior affiliation',
    () {
      learnMemberships();
      rosterObserve('p1 no longer plays for TeamA academy', 5);
      rosterObserve('p2 not playing for TeamA esports youth', 6);
      expect(scene.teams, ['TeamA', 'TeamB']);
    },
  );

  test('historical and hypothetical denials cannot retract current facts', () {
    learnMemberships();
    rosterObserve('Previously p1 was not playing for TeamA', 5);
    rosterObserve('If p2 no longer plays for TeamA', 6);
    expect(scene.teams, ['TeamA', 'TeamB']);
    scene.advanceClock(120000);
    rosterObserve('p1 moves outside', 8, at: 125000);
    rosterObserve('p2 finds a kill', 9, at: 130000);
    rosterObserve('q1 holds the site', 10, at: 135000);
    rosterObserve('q2 gets a trade', 11, at: 140000);
    expect(scene.teams, ['TeamA', 'TeamB']);
  });

  test(
    'explicit denial releases a hinted affiliation without guessing another',
    () {
      learnMemberships();
      rosterObserve(
        'p1 no longer plays for TeamA',
        5,
        injected: {'p1', 'teama'},
      );
      expect(scene.teams, isEmpty);
      expect(scene.teams, isNot(contains('TeamC')));
      scene.advanceClock(120000);
      rosterObserve('p1 moves outside', 6, at: 125000);
      rosterObserve('p2 finds a kill', 7, at: 130000);
      expect(scene.teamCandidates, isEmpty);
    },
  );

  test(
    'a contradictory affiliation in one window cannot undo its own denial',
    () {
      learnMemberships();
      rosterObserve('p1 not playing for TeamA but p1 plays for TeamA', 5);
      rosterObserve('p2 not playing for TeamA but p2 plays for TeamA', 6);
      expect(scene.teams, isEmpty);
      scene.advanceClock(120000);
      rosterObserve('p1 moves outside', 7, at: 125000);
      rosterObserve('p2 finds a kill', 8, at: 130000);
      expect(scene.teamCandidates, isEmpty);
    },
  );

  test(
    'two independent player cohorts yield snapshot candidates but never confirmation',
    () {
      rosterObserve('p1 moves outside', 1);
      rosterObserve('p2 finds a kill', 2);
      rosterObserve('q1 holds the site', 3);
      rosterObserve('q2 gets the trade', 4);
      expect(scene.teamCandidates, ['TeamA', 'TeamB']);
      expect(scene.teams, isEmpty);
      scene.advanceClock(120000);
      expect(scene.teamCandidates, isEmpty);
    },
  );

  test(
    'learned current affiliations support later player-only independent windows',
    () {
      learnMemberships();
      expect(scene.teams, ['TeamA', 'TeamB']);
      scene.advanceClock(120000);
      expect(scene.teams, isEmpty);
      rosterObserve('p1 moves outside', 5, at: 125000);
      rosterObserve('p2 finds a kill', 6, at: 130000);
      rosterObserve('q1 holds the site', 7, at: 135000);
      rosterObserve('q2 gets the trade', 8, at: 140000);
      expect(scene.teams, ['TeamA', 'TeamB']);
      scene.reset(2);
      expect(scene.teamCandidates, isEmpty);
      expect(scene.teams, isEmpty);
    },
  );

  test('stale snapshot cannot override a learned transfer', () {
    rosterObserve('p1 plays for TeamC', 1);
    rosterObserve('p2 from TeamC attacks', 2);
    scene.advanceClock(120000);
    rosterObserve('p1 moves outside', 3, at: 125000);
    rosterObserve('p2 finds a kill', 4, at: 130000);
    expect(scene.teamCandidates, ['TeamC']);
    expect(scene.teamCandidates, isNot(contains('TeamA')));
  });

  test(
    'conflicting affiliation is ambiguous rather than newest-claim-wins',
    () {
      rosterObserve('p1 plays for TeamA', 1);
      rosterObserve('p2 from TeamA attacks', 2);
      rosterObserve('p1 plays for TeamC', 3);
      scene.advanceClock(120000);
      rosterObserve('p1 moves outside', 4, at: 125000);
      rosterObserve('p2 finds a kill', 5, at: 130000);
      expect(scene.teamCandidates, isEmpty);
    },
  );

  test(
    'historical negated and injected affiliations never become learned facts',
    () {
      rosterObserve('Previously p1 plays for TeamC', 1);
      rosterObserve('p2 not playing for TeamC', 2);
      rosterObserve('p1 plays for TeamC', 3, injected: {'teamc'});
      rosterObserve('p2 from TeamC attacks', 4, injected: {'p2'});
      scene.advanceClock(120000);
      rosterObserve('p1 moves outside', 5, at: 125000);
      rosterObserve('p2 finds a kill', 6, at: 130000);
      expect(scene.teamCandidates, ['TeamA']);
      expect(scene.teams, isEmpty);
    },
  );

  test(
    'same window and one repeated player cannot establish a team cohort',
    () {
      rosterObserve('p1 and p2 move outside', 1);
      expect(scene.teamCandidates, isEmpty);
      scene.reset(1);
      rosterObserve('p1 moves outside', 1);
      rosterObserve('p1 finds a kill', 2);
      expect(scene.teamCandidates, isEmpty);
    },
  );

  test(
    'learned affiliations expire rather than becoming permanent roster facts',
    () {
      learnMemberships();
      scene.advanceClock(700000);
      rosterObserve('p1 moves outside', 5, at: 705000);
      rosterObserve('p2 finds a kill', 6, at: 710000);
      rosterObserve('q1 holds the site', 7, at: 715000);
      rosterObserve('q2 gets the trade', 8, at: 720000);
      expect(scene.teamCandidates, ['TeamA', 'TeamB']);
      expect(scene.teams, isEmpty);
    },
  );

  test('actual bundled Vent/Vents aliases keep the Cache/Nuke union', () async {
    final bundled = await CorpusIndex.load(rootBundle);
    final state = SceneAssistant()..reset(1);
    state.observe(
      bundled,
      'He jumps into the vent',
      epoch: 1,
      window: 1,
      endMs: 5000,
    );
    expect(state.map, isNull);
    state.observe(
      bundled,
      'They move through lobby',
      epoch: 1,
      window: 2,
      endMs: 10000,
    );
    expect(state.map, 'Nuke');
    final ventTerms = bundled.match('Vents', limit: bundled.termCount);
    final concepts = ventTerms
        .where((t) => t['category'] == 'map_callout')
        .map(bundled.sceneConceptFor)
        .toSet();
    expect(concepts, hasLength(1));
    state.reset(1);
    state.observe(
      bundled,
      'He crosses Vent and Vents',
      epoch: 1,
      window: 1,
      endMs: 5000,
    );
    state.observe(
      bundled,
      'A player jumps into vents',
      epoch: 1,
      window: 2,
      endMs: 10000,
    );
    expect(state.map, isNull);
  });

  test('independent concepts intersect preserved multi-map relationships', () {
    observe('They cross lobby', 1);
    expect(scene.map, isNull);
    observe('A player goes down the vents', 2);
    expect(scene.map, 'Nuke');
  });
  test(
    'aliases, repeated text, repeated windows and hinted concepts cannot self-confirm',
    () {
      observe('Lobby and vent and vents', 1);
      expect(scene.map, isNull);
      observe('Lobby and vent and vents', 2);
      expect(scene.map, isNull);
      scene.reset(1);
      observe('They cross lobby', 1);
      observe('He crosses vent', 1);
      expect(scene.map, isNull);
      observe('He crosses vent', 2, injected: {'vent'});
      expect(scene.map, isNull);
    },
  );
  test('negation and historical mentions do not vote', () {
    observe('They are not in lobby', 1);
    observe('Yesterday they went vent', 2);
    expect(scene.map, isNull);
    observe('Not in vent but now they cross lobby', 3);
    observe('Now the vent is occupied', 4);
    expect(scene.map, 'Nuke');
  });
  test(
    'explicit switch lifts old map immediately and new cues establish another',
    () {
      observe('They cross lobby', 1);
      observe('He drops vent', 2);
      observe('Next map is Mirage', 3);
      expect(scene.map, isNull);
      observe('He enters palace', 4);
      expect(scene.map, 'Mirage');
    },
  );
  test(
    'explicit denial releases even a previously hinted map and forbids immediate reconfirmation',
    () {
      observe('They cross lobby', 1);
      observe('He drops vent', 2);
      expect(scene.map, 'Nuke');
      observe('We are not on Nuke', 3, injected: {'nuke'});
      expect(scene.map, isNull);
      observe('Lobby is held', 4);
      observe('They cross vent', 5);
      expect(scene.map, isNull);
      observe('Now the map is Mirage', 6);
      observe('He enters palace', 7);
      expect(scene.map, 'Mirage');
    },
  );

  test('two conflicting windows recover even without explicit map name', () {
    observe('They cross lobby', 1);
    observe('He drops vent', 2);
    observe('He enters palace', 3);
    expect(scene.map, 'Nuke');
    observe('The connector is held', 4);
    expect(scene.map, 'Mirage');
  });
  test('audio clock expires evidence while queued outputs remain causal', () {
    scene.advanceClock(12000);
    observe('They cross lobby', 1, at: 5000);
    observe('He drops vent', 2, at: 10000);
    expect(scene.map, 'Nuke');
    scene.advanceClock(60000);
    expect(scene.map, isNull);
    observe('Lobby again', 3, at: 14000);
    expect(scene.map, isNull);
  });
  test(
    'roster snapshots never establish current team and epoch reset clears everything',
    () {
      observe('ropz is here', 1);
      observe('ropz gets another kill', 2);
      expect(scene.teams, isEmpty);
      observe('NAVI face FaZe', 3);
      expect(scene.teams, isEmpty);
      observe('FaZe attack NAVI again', 4);
      expect(scene.teams, ['FaZe', 'NAVI']);
      scene.reset(2);
      expect(scene.map, isNull);
      expect(scene.teams, isEmpty);
      observe('NAVI face FaZe', 5);
      expect(scene.teams, isEmpty);
    },
  );
  test(
    'hints respect map ambiguity and both character and proxy token budgets',
    () {
      final hints = corpus.e2eHints(
        '',
        recentEnglish: ['Vent is held', 'They cross vent'],
        includeRecent: true,
        map: 'Nuke',
        maximumTokens: 32,
      );
      expect(hints.length, lessThanOrEqualTo(240));
      expect(CorpusIndex.estimateHintTokens(hints), lessThanOrEqualTo(32));
      expect(hints, contains('Map: Nuke'));
      expect(
        corpus.e2eHints('', profile: CorpusProfile.none, map: 'Nuke'),
        isEmpty,
      );
    },
  );
}

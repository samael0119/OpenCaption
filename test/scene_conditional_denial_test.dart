import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/scene_assistant.dart';

void main() {
  final corpus = CorpusIndex.fromPacks([
    {
      'schema_version': 1,
      'terms': [
        for (final name in ['Lobby', 'Vent'])
          {
            'english': name,
            'chinese': name,
            'category': 'map_callout',
            'context': '地图：Nuke',
          },
        {'english': 'Nuke', 'chinese': '核子危机', 'category': 'map'},
        for (final team in ['TeamA', 'TeamB'])
          {'english': team, 'chinese': team, 'category': 'team'},
        for (final player in ['p1', 'p2', 'q1', 'q2'])
          {'english': player, 'chinese': player, 'category': 'player'},
      ],
    },
  ]);

  SceneAssistant confirmedMap() {
    final scene = SceneAssistant()..reset(1);
    scene.observe(corpus, 'They cross lobby', epoch: 1, window: 1, endMs: 5000);
    scene.observe(corpus, 'He drops vent', epoch: 1, window: 2, endMs: 10000);
    expect(scene.map, 'Nuke');
    return scene;
  }

  for (final sentence in [
    'If this is not Nuke, they will save',
    'Imagine they are not on Nuke',
    'Suppose this is not Nuke',
    'Supposing they are not playing Nuke',
    'Assuming they are not on Nuke',
    'Hypothetically they are not on Nuke',
    'They would not play Nuke',
    'They could be not on Nuke',
    'They might be not on Nuke',
    'Perhaps they are not on Nuke',
  ]) {
    test('non-factual denial preserves confirmed map: $sentence', () {
      final scene = confirmedMap();
      scene.observe(corpus, sentence, epoch: 1, window: 3, endMs: 15000);
      expect(scene.map, 'Nuke');
    });
  }

  test('explicit current denial still releases within one fragment', () {
    final scene = confirmedMap();
    scene.observe(
      corpus,
      'We are not on Nuke',
      epoch: 1,
      window: 3,
      endMs: 15000,
    );
    expect(scene.map, isNull);
  });

  test('current denial after conditional clause can still release', () {
    final scene = confirmedMap();
    scene.observe(
      corpus,
      'If we leave lobby, save the rifles but now we are not on Nuke',
      epoch: 1,
      window: 3,
      endMs: 15000,
    );
    expect(scene.map, isNull);
  });

  test('hypothetical denial cannot poison subsequent independent cues', () {
    final scene = confirmedMap();
    scene.observe(
      corpus,
      'Imagine this is not Nuke',
      epoch: 1,
      window: 3,
      endMs: 15000,
    );
    scene.observe(corpus, 'Lobby is occupied', epoch: 1, window: 4, endMs: 20000);
    scene.observe(corpus, 'Vent is clear', epoch: 1, window: 5, endMs: 25000);
    expect(scene.map, 'Nuke');
  });

  test('uncertain affiliation denial preserves learned current teams', () {
    final scene = SceneAssistant()..reset(1);
    final facts = [
      'p1 plays for TeamA',
      'p2 from TeamA takes the kill',
      'q1 plays for TeamB',
      'q2 from TeamB defends',
      'Perhaps p1 no longer plays for TeamA',
      'Perhaps p2 is not playing for TeamA',
    ];
    for (var i = 0; i < facts.length; i++) {
      scene.observe(
        corpus,
        facts[i],
        epoch: 1,
        window: i + 1,
        endMs: (i + 1) * 5000,
      );
      if (i == 3) expect(scene.teams, ['TeamA', 'TeamB']);
    }
    expect(scene.teams, ['TeamA', 'TeamB']);
  });
}

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/corpus.dart';
import 'package:opencaption/core/scene_assistant.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'correction choices contain named maps, not generic map vocabulary',
    () async {
      final corpus = await CorpusIndex.load(rootBundle);
      expect(corpus.sceneChoices('map'), contains('Nuke'));
      expect(corpus.sceneChoices('map'), isNot(contains('bombsite')));
      expect(corpus.sceneChoices('map'), isNot(contains('spawn')));
      expect(corpus.match('bombsite').single['chinese'], isNotEmpty);
    },
  );
  test('generic map nouns cannot revoke confirmed map evidence', () async {
    final corpus = await CorpusIndex.load(rootBundle);
    final scene = SceneAssistant()..reset(1);
    scene.observe(corpus, 'They cross lobby', epoch: 1, window: 1, endMs: 5000);
    scene.observe(
      corpus,
      'He drops into vent',
      epoch: 1,
      window: 2,
      endMs: 10000,
    );
    expect(scene.map, 'Nuke');
    scene.observe(
      corpus,
      'They plant on the bombsite',
      epoch: 1,
      window: 3,
      endMs: 15000,
    );
    expect(scene.map, 'Nuke');
    scene.observe(
      corpus,
      'We are not in spawn',
      epoch: 1,
      window: 4,
      endMs: 20000,
    );
    expect(scene.map, 'Nuke');
  });
  test(
    'invalid scene entity data is rejected and legacy named relationships remain compatible',
    () {
      final legacy = CorpusIndex.fromPacks([
        {
          'schema_version': 1,
          'terms': [
            {'english': 'Nuke', 'chinese': '核子危机', 'category': 'map'},
            {
              'english': 'Lobby',
              'chinese': '大厅',
              'category': 'map_callout',
              'context': '地图：Nuke',
            },
            {'english': 'bombsite', 'chinese': '包点', 'category': 'map'},
          ],
        },
      ]);
      expect(legacy.sceneChoices('map'), ['Nuke']);
      expect(
        () => CorpusIndex.fromPacks([
          {
            'schema_version': 1,
            'terms': [
              {
                'english': 'Nuke',
                'chinese': '核子危机',
                'category': 'map',
                'scene_entity': 'true',
              },
            ],
          },
        ]),
        throwsFormatException,
      );
    },
  );
}

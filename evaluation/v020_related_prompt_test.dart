// Render the actual core candidate template before freezing a negative guard.
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:opencaption/core/corpus.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('freeze actual compact baseline and related hint strings', () async {
    final path = File(
      'evaluation/results/v020-independent/related_prompt_snapshot.json',
    );
    expect(
      path.existsSync(),
      isFalse,
      reason: 'Do not regenerate after outputs',
    );
    final corpus = await CorpusIndex.load(rootBundle);
    const recent = ['They cross lobby', 'He drops into vent'];
    final candidates = corpus.relatedCandidates(recent, map: 'Nuke');
    final baseline = corpus.e2eHints(
      '',
      includeRecent: true,
      recentEnglish: recent,
      map: 'Nuke',
    );
    final related = corpus.e2eHints(
      '',
      includeRecent: true,
      recentEnglish: recent,
      map: 'Nuke',
      related: candidates,
    );
    expect(candidates.length, 2);
    expect(related, contains('Secret=地下通道'));
    expect(related, contains('B Site=B包点'));
    expect(related.length, lessThanOrEqualTo(240));
    expect(CorpusIndex.estimateHintTokens(related), lessThanOrEqualTo(96));
    path.writeAsStringSync(
      const JsonEncoder.withIndent('  ').convert({
        'baseline': baseline,
        'related': related,
        'core': 'CorpusIndex.e2eHints/relatedCandidates',
        'scope':
            'Constructed prior Nuke context, used as unrelated negative-control data only',
        'candidate_ids': candidates.map((c) => c.term['id']).toList(),
        'baseline_chars': baseline.length,
        'related_chars': related.length,
        'baseline_proxy_tokens': CorpusIndex.estimateHintTokens(baseline),
        'related_proxy_tokens': CorpusIndex.estimateHintTokens(related),
      }),
    );
  });
}

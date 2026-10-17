import unittest

from s0_probe import cuts, SceneIndex


class CausalBoundaryTests(unittest.TestCase):
    def test_every_sample_survives_non_frame_aligned_tail(self):
        sample_count = 16000 * 11 + 17
        rows = cuts([.9] * ((sample_count + 511) // 512), sample_count)
        self.assertEqual(sum(r['end'] - r['start'] for r in rows), sample_count)
        self.assertEqual([r['end'] - r['start'] for r in rows[:2]], [80000, 80000])
        self.assertEqual(rows[-1]['end'], sample_count)

    def test_future_probabilities_cannot_move_an_existing_cut(self):
        prefix = [.9] * 10 + [.01] * 30
        samples = len(prefix) * 512
        earlier = cuts(prefix, samples)
        extended = cuts(prefix + [.9] * 200, samples + 200 * 512)
        committed = [r for r in earlier if r['reason'] != 'tail']
        self.assertEqual(committed, extended[:len(committed)])

    def test_short_answer_does_not_wait_for_minimum_window(self):
        rows = cuts([.9] * 8 + [0.] * 60, 68 * 512)
        self.assertEqual(rows[0]['reason'], 'pause')
        self.assertLess(rows[0]['end'] / 16, 1200)

    def test_quiet_audio_is_not_discarded(self):
        rows = cuts([0.] * 400, 400 * 512)
        self.assertEqual(sum(r['end'] - r['start'] for r in rows), 400 * 512)


class DomainRelationTests(unittest.TestCase):
    def test_same_translation_preserves_all_map_relations(self):
        index = SceneIndex()
        maps = {term['context'] for term in index.aliases['a site']}
        self.assertEqual(len(maps), 7)
        self.assertIn('地图：Nuke', maps)
        self.assertIn('地图：Ancient', maps)

    def test_common_callout_remains_ambiguous(self):
        found = SceneIndex().observe('CT and A Main')
        self.assertGreaterEqual(len(found['maps']), 2)
        self.assertEqual(found['teams'], {})

    def test_generic_map_vocabulary_is_not_an_explicit_map_identity(self):
        self.assertEqual(SceneIndex().observe('bombsite')['maps'], {})


if __name__ == '__main__':
    unittest.main()

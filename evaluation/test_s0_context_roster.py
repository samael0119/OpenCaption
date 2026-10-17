import unittest

from s0_context_roster import IdentityIndex


class IdentityEvidenceTests(unittest.TestCase):
    def test_common_words_are_not_rewritten_as_players(self):
        index = IdentityIndex()
        text = 'a little bit, a wonderful idea, frozen water'
        self.assertEqual(index.normalize(text), text)
        self.assertTrue(all(h['strength'] == 'weak' for h in index.mentions(text)))

    def test_unique_curated_alias_can_restore_id_spelling(self):
        self.assertEqual(IdentityIndex().normalize('Shiro holds the angle'), 'sh1ro holds the angle')

    def test_roster_without_date_remains_only_a_candidate(self):
        self.assertEqual(IdentityIndex().affiliation('karrigan')['state'], 'snapshot_candidate_only')

    def test_future_snapshot_cannot_establish_historical_membership(self):
        self.assertIsNone(IdentityIndex().affiliation('karrigan', '2025-12-01')['team'])

    def test_match_reference_is_separate_from_automatic_inference(self):
        result = IdentityIndex().affiliation('karrigan', match_fixture={'karrigan': 'FaZe'})
        self.assertEqual(result['team'], 'FaZe')
        self.assertEqual(result['state'], 'match_specific_reference')


if __name__ == '__main__':
    unittest.main()

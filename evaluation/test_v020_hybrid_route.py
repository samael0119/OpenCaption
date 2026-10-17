import unittest
from v020_hybrid_route import route, may_start


class HybridPolicyTest(unittest.TestCase):
    def test_empty_speech_and_music_both_fallback(self):
        self.assertEqual(route('  ', 'old speech'), ('old speech', 'fallback'))
        self.assertEqual(route('', 'old music hallucination'), ('old music hallucination', 'fallback'))

    def test_nonempty_errors_are_not_oracle_corrected(self):
        self.assertEqual(route('RUM', 'Run'), ('RUM', 'asr'))

    def test_weekly_boundary(self):
        self.assertTrue(may_start(60))
        self.assertFalse(may_start(60.01))
        self.assertFalse(may_start(None))
        self.assertFalse(may_start(float('nan')))


if __name__ == '__main__': unittest.main()

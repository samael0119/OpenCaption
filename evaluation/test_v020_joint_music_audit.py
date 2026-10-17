"""Protect against labelling a speech-contaminated interval as pure music."""
import unittest
from v020_joint_music_audit import pieces, eligible


class MusicIntervalBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.playlist = [dict(path='speech', start_sample=0, samples=5, added_zero_samples=2),
                         dict(path='music', start_sample=7, samples=5, added_zero_samples=2)]

    def split(self, start, end):
        return pieces(start, end, self.playlist, 14, {'music'})

    def test_leading_previous_zero_and_music_is_eligible(self):
        parts = self.split(5, 13)
        self.assertTrue(eligible(parts))
        self.assertEqual(sum(part['end_sample'] - part['start_sample'] for part in parts), 8)

    def test_even_one_previous_speech_sample_excludes_interval(self):
        self.assertFalse(eligible(self.split(4, 13)))

    def test_cycle_wrap_into_speech_is_excluded(self):
        self.assertFalse(eligible(self.split(11, 15)))
        self.assertTrue(eligible(self.split(21, 28)))

    def test_added_zero_alone_does_not_count_as_music(self):
        self.assertFalse(eligible(self.split(12, 14)))

    def test_missing_playlist_sample_fails_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            pieces(6, 8, [self.playlist[1]], 14, {'music'})


if __name__ == '__main__':
    unittest.main()

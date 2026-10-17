import array
import unittest
from v020_gain_candidate import boost


class GainSafetyTest(unittest.TestCase):
    def test_exact_zero_not_turned_into_speech(self):
        result,gain=boost(array.array('h',[0]*160))
        self.assertEqual(gain,1);self.assertFalse(any(result))

    def test_weak_speech_preserves_frames_and_signs(self):
        original=array.array('h',[0,10,-10,0,100,-100])
        result,gain=boost(original)
        self.assertEqual(gain,16);self.assertEqual(list(result),[0,160,-160,0,1600,-1600])
        self.assertEqual(len(result),len(original))

    def test_headroom_prevents_clipping(self):
        result,gain=boost(array.array('h',[20000,-20000,0]))
        self.assertLess(gain,16);self.assertLessEqual(max(map(abs,result)),29491)

    def test_full_scale_samples_not_modified(self):
        original=array.array('h',[-32768,32767,0])
        result,gain=boost(original)
        self.assertEqual(gain,1);self.assertEqual(result,original)


if __name__=='__main__':unittest.main()

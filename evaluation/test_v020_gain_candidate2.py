import array
import unittest
from v020_gain_candidate2 import restricted,peak200


class RestrictedGainTest(unittest.TestCase):
    def test_zero_stays_exact(self):
        result,gain=restricted(array.array('h',[0]*32000))
        self.assertEqual(gain,1);self.assertFalse(any(result))

    def test_boundary_256_and_strong_input_stay_unchanged(self):
        for peak in [256,257,20000,32767]:
            source=array.array('h',[peak,-peak,0])
            result,gain=restricted(source)
            self.assertEqual(gain,1);self.assertEqual(source,result)

    def test_255_boosts_without_dropping_samples(self):
        source=array.array('h',[0,255,-255,0])
        result,gain=restricted(source)
        self.assertEqual(gain,16);self.assertEqual(list(result),[0,4080,-4080,0])

    def test_counterexample_peak_and_zero_layout(self):
        source=array.array('h',[0,0,20000,-20000,0])
        quiet=peak200(source)
        self.assertEqual(list(quiet),[0,0,200,-200,0])
        result,gain=restricted(quiet)
        self.assertEqual(len(result),len(source));self.assertEqual(gain,16)


if __name__=='__main__':unittest.main()

import unittest
from v020_mt6_casing import lower_input
from test_v020_mt6_run import MT6Guards
class CasingGuards(unittest.TestCase):
    def test_exact_transform_and_counterexamples(self):
        for s in ['BY HARRY QUILTER M A',"I HOPE HE DOESN'T WORK TOO HARD SAID SHAGGY"]:
            self.assertEqual(lower_input(s),s.lower())
    def test_no_other_input_regime(self):
        for s in ['Harry Quilter','中文','123']:
            with self.assertRaises(ValueError):lower_input(s)
if __name__=='__main__':unittest.main()

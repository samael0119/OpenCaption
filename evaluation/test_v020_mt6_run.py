import unittest
from v020_mt6_run import authorized,model_input


class FakeSP:
    def encode(self,text,out_type):return text.split()


class MT6Guards(unittest.TestCase):
    def test_prefix_and_eos(self):
        self.assertEqual(model_input('hello   world',FakeSP()),['>>cmn_Hans<<','hello','world'])
    def test_no_truncation(self):
        with self.assertRaises(ValueError):model_input('word '*512,FakeSP())
    def test_no_silent_normalization_changes(self):
        for text in ['hello\nworld','中文']:
            with self.assertRaises(ValueError):model_input(text,FakeSP())
    def test_quota_and_pause(self):
        s={'status':'active','current_round':6};a={'status':'ACTIVE'};q={'usedPercent':60,'windowDurationMins':10080,'observed_at_unix':1000}
        authorized(s,a,q,1000)
        for changed in [dict(q,usedPercent=60.01),dict(q,usedPercent=None),dict(q,observed_at_unix=800)]:
            with self.assertRaises(RuntimeError):authorized(s,a,changed,1000)
        with self.assertRaises(RuntimeError):authorized(s,{'status':'PAUSED'},q,1000)


if __name__=='__main__':unittest.main()

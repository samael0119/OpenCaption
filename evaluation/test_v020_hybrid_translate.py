import unittest
from v020_hybrid_translate import authorized


class AuthorizationTest(unittest.TestCase):
    def check(self,used=60,age=0,status='ACTIVE'):
        authorized({'status':'active','current_round':5},{'status':status},
                   {'usedPercent':used,'windowDurationMins':10080,'observed_at_unix':1000-age},1000)
    def test_boundary(self):
        self.check()
        with self.assertRaises(RuntimeError): self.check(60.1)
    def test_unknown_and_stale(self):
        for used,age in [(None,0),(20,121),(20,-1)]:
            with self.assertRaises(RuntimeError): self.check(used,age)
    def test_pause(self):
        with self.assertRaises(RuntimeError): self.check(status='PAUSED')


if __name__=='__main__': unittest.main()

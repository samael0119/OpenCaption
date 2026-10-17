import array
import unittest

from v020_round2_noise import authorized, filter_pcm, DELAY


class NoiseSafetyTest(unittest.TestCase):
    def test_zero_is_zero_and_complete(self):
        x=array.array('h',[0]*32000)
        y,_=filter_pcm(x)
        self.assertEqual(x,y)

    def test_measured_delay_and_end_impulse_are_preserved(self):
        x=array.array('h',[0]*32000);x[10000]=20000
        raw,_=filter_pcm(x,compensate=False)
        self.assertEqual(max(range(len(raw)),key=lambda i:abs(raw[i])),10000+DELAY)
        x=array.array('h',[0]*32000);x[-1]=20000
        y,_=filter_pcm(x)
        self.assertEqual(len(y),len(x))
        self.assertEqual(max(range(len(y)),key=lambda i:abs(y[i])),len(x)-1)
        self.assertGreater(abs(y[-1]),10000)

    def test_weak_tail_not_rejected(self):
        x=array.array('h',[0]*32000);x[-400:]=array.array('h',[100,-100]*200)
        y,_=filter_pcm(x)
        self.assertEqual(len(y),len(x))
        self.assertTrue(any(y[-400:]))

    def test_historical_counts_do_not_stop_current_round(self):
        authorized(dict(status='active',current_round=2,current_round_status='in_progress',
            consecutive_complete_rounds_without_gain=1,consecutive_evaluation_packages_without_verified_gain=3,
            actual_work_seconds_since_verified_gain=999999),dict(status='ACTIVE'))

    def test_real_pause_and_complete_round_limit_stop(self):
        for status,rounds,auto in [('paused',1,'ACTIVE'),('active',3,'ACTIVE'),('active',1,'PAUSED')]:
            with self.assertRaises(RuntimeError):
                authorized(dict(status=status,current_round=2,current_round_status='in_progress',
                    consecutive_complete_rounds_without_gain=rounds),dict(status=auto))


if __name__=='__main__':
    unittest.main()

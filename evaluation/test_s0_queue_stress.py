import random
import unittest

from s0_queue_stress import Segment,replay


class BoundedQueueTests(unittest.TestCase):
    def test_normal_service_preserves_every_interval(self):
        rows=[Segment(i+1,i*5000,(i+1)*5000,2800) for i in range(8)]
        value=replay(rows)
        self.assertEqual(len(value['delivered']),8)
        self.assertEqual(value['dropped'],[])

    def test_pending_replacement_reports_complete_discarded_interval(self):
        rows=[Segment(i+1,i*5000,(i+1)*5000,30000 if i==0 else 1000) for i in range(5)]
        value=replay(rows,max_age_ms=2500)
        self.assertEqual([r['id'] for r in value['delivered']],[1])
        self.assertEqual([(r['start_ms'],r['end_ms']) for r in value['dropped']],[(5000,10000),(10000,15000),(15000,20000),(20000,25000)])
        self.assertEqual(value['dropped'][-1]['reason'],'expired')

    def test_expired_audio_cannot_begin_and_fault_removal_recovers(self):
        rows=[Segment(i+1,i*5000,(i+1)*5000,2800) for i in range(24)]
        value=replay(rows,extra_service=lambda s:4000 if s.end_ms<=30000 else 0)
        self.assertTrue(value['dropped'])
        self.assertTrue(all(r['queue_age_ms']<=2500 for r in value['delivered']))
        self.assertEqual([r['id'] for r in value['delivered'] if r['end_ms']>40000],list(range(9,25)))

    def test_varied_traces_preserve_ownership_age_and_single_active(self):
        rng=random.Random(20261013)
        for _ in range(100):
            end=0;rows=[]
            for i in range(30):
                start=end;end+=rng.randrange(300,5001)
                rows.append(Segment(i,start,end,rng.randrange(0,12001)))
            value=replay(rows)
            self.assertLessEqual(value['max_pending'],1)
            self.assertEqual(len(value['delivered'])+len(value['dropped']),30)
            self.assertTrue(all(r['queue_age_ms']<=2500 for r in value['delivered']))


if __name__=='__main__':
    unittest.main()

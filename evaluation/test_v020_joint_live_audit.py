import copy
import unittest
from v020_joint_live_summary import audit


class TransportAudit(unittest.TestCase):
    def fixture(self):
        resources={'memory.swap.current':'0','memory.peak':'4096','memory.events':'oom_kill 0'}
        events=[dict(type='capture_event',event='OFFER',fields=['1','0','1000','tail','false','1']),
                dict(type='capture_event',event='ACT',fields=['1000','1001'],resources=resources),
                dict(type='capture_event',event='CAPEND',fields=['1000','50','1.2','1001'])]
        result=dict(type='result',window=1,start_ms=0,end_ms=1000,source_samples=16000,
                    input_samples=32000,started_ms=1001,submitted_ms=1001,raw='NONE',hints='',status='no_speech')
        complete=dict(type='complete',requests=1)
        model=[dict(type='request_start',window=1),*events,result,complete]
        widget={**result,'type':'widget_result','widget_exception':False}
        return model,[*copy.deepcopy(events),widget,copy.deepcopy(complete)]

    def test_owned_complete_transport_is_not_quality_acceptance(self):
        result=audit(*self.fixture(),1)
        self.assertTrue(result['complete'])
        self.assertFalse(result['independent_quality_acceptance'])
        self.assertFalse(result['measured_screen_latency'])

    def test_lost_activity_even_with_complete_marker_fails(self):
        model,ui=self.fixture();ui.pop(1)
        with self.assertRaisesRegex(ValueError,'events lost'):audit(model,ui,1)

    def test_widget_loss_and_oom_fail(self):
        model,ui=self.fixture();ui[-2]['widget_exception']=True
        with self.assertRaisesRegex(ValueError,'Widget exception'):audit(model,ui,1)
        model,ui=self.fixture();model[2]['resources']['memory.events']='oom_kill 1'
        with self.assertRaisesRegex(ValueError,'OOMKill'):audit(model,ui,1)

    def test_incomplete_even_after_all_results_fails(self):
        model,ui=self.fixture();ui.pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):audit(model,ui,1)


if __name__=='__main__':unittest.main()

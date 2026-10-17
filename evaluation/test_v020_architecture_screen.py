import unittest
from v020_architecture_screen import authorize,chunks,metrics,CYCLE

class Guards(unittest.TestCase):
    def test_paused_or_old_cycle_cannot_run(self):
        for state,auto in [({'cycle_id':CYCLE,'status':'active'},{'status':'PAUSED'}),
                           ({'cycle_id':'old','status':'active'},{'status':'ACTIVE'}),
                           ({'cycle_id':CYCLE,'status':'active','consecutive_complete_rounds_without_gain':3},{'status':'ACTIVE'})]:
            with self.assertRaises(RuntimeError): authorize(state,auto)
        authorize({'cycle_id':CYCLE,'status':'active','consecutive_complete_rounds_without_gain':0},{'status':'ACTIVE'})

    def test_stream_feed_preserves_tail_and_zero(self):
        source=[0,1,-1,32767,-32768,0,42]
        self.assertEqual([x for _,chunk in chunks(source,3) for x in chunk],source)
        self.assertEqual(list(chunks(source,3))[-1],(6,[42]))

    def test_empty_voice_is_loss(self):
        score=metrics('no','')
        self.assertFalse(score['strict_match']);self.assertEqual(score['word_errors'],1)

    def test_music_description_not_silently_filtered(self):
        score=metrics('','(gentle music)')
        self.assertTrue(score['nonempty']);self.assertEqual(score['word_errors'],2)

    def test_negation_cannot_pass_as_partial_match(self):
        self.assertFalse(metrics('do not move','do move')['strict_match'])

if __name__=='__main__': unittest.main()

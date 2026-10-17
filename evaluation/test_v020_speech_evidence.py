import unittest
from v020_speech_evidence_summary import candidate, summarize


RULE = dict(min_samples=32000, min_rms=.02, max_vad_exclusive=.01)


class SpeechEvidenceTest(unittest.TestCase):
    def test_short_quiet_or_unknown_audio_is_never_candidate_veto(self):
        self.assertFalse(candidate(dict(samples=16000,rms=.2,max_vad=.001),RULE))
        self.assertFalse(candidate(dict(samples=80000,rms=.001,max_vad=.001),RULE))
        self.assertFalse(candidate(dict(samples=80000,rms=.2,max_vad=float('nan')),RULE))
        self.assertFalse(candidate(dict(rms=.2,max_vad=.001),RULE))
        self.assertTrue(candidate(dict(samples=80000,rms=.2,max_vad=.001),RULE))

    def test_full_evidence_never_claims_product_acceptance(self):
        plan = dict(rule=RULE,cases=[dict(id='music',label='music')],scope='diagnostic')
        lines = [f'{m}\tmusic\tmusic\t80000\t.2\t.001\t.0001\t0\t10' for m in ['reset','continuous']]
        result = summarize(lines+['#complete\t2'],plan)
        self.assertTrue(result['integrity_pass'])
        self.assertFalse(result['product_music_acceptance'])
        self.assertFalse(summarize(lines,plan)['integrity_pass'])

    def test_duplicate_and_mislabeled_evidence_fail_integrity(self):
        plan = dict(rule=RULE,cases=[dict(id='voice',label='speech')],scope='diagnostic')
        line = 'reset\tvoice\tmusic\t80000\t.2\t.001\t.0001\t0\t10'
        self.assertFalse(summarize([line,line,'#complete\t2'],plan)['integrity_pass'])


if __name__ == '__main__':
    unittest.main()

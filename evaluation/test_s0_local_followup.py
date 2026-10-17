import unittest

from s0_local_followup import candidate_parse, exact_zero_pcm, scale_pcm, relevant_callouts
from s0_probe import SceneIndex


class SentinelAdapterTests(unittest.TestCase):
    def test_exact_balanced_sentinels_are_no_speech(self):
        for raw in ['English: [NONE]\nChinese: [NONE]','[NONE]\nand 中文：[NONE]']:
            self.assertEqual(candidate_parse(raw).status,'no_speech')

    def test_one_sentinel_or_missing_language_is_not_a_caption(self):
        for raw in ['English: hello\nChinese: [NONE]','English: [NONE]\nChinese: 你好',
                    'Chinese: [NONE]','English: [NONE]']:
            self.assertEqual(candidate_parse(raw).status,'invalid')

    def test_explanations_and_embedded_sentinels_cannot_be_accepted(self):
        for raw in ['Explanation: no voice\nEnglish: [NONE]\nChinese: [NONE]',
                    'English: [NONE]\nChinese: [NONE]\nNo speech detected',
                    'English: the word [NONE]\nChinese: 空',
                    'English: [NONE]\nChinese: [NONE]。']:
            self.assertEqual(candidate_parse(raw).status,'invalid')

    def test_valid_speech_is_unchanged_and_single_none_remains_valid(self):
        value=candidate_parse('English: a little bit\nChinese: 一点点')
        self.assertEqual((value.status,value.english,value.chinese),('subtitle','a little bit','一点点'))
        self.assertEqual(candidate_parse('[NONE]').status,'no_speech')


class ZeroPcmRoutingTests(unittest.TestCase):
    def test_only_exact_zeros_bypass(self):
        self.assertTrue(exact_zero_pcm(bytes(32000)))
        self.assertFalse(exact_zero_pcm(b'\x01\x00'+bytes(31998)))
        self.assertFalse(exact_zero_pcm(b'\xff\xff'+bytes(31998)))

    def test_invalid_pcm_is_not_a_silence_decision(self):
        for pcm in [b'',b'\x00']:
            with self.assertRaises(ValueError):exact_zero_pcm(pcm)

    def test_attenuated_nonzero_voice_is_not_gated(self):
        pcm=(10000).to_bytes(2,'little',signed=True)*16000
        self.assertFalse(exact_zero_pcm(scale_pcm(pcm,-30)))


class RelationRetrievalTests(unittest.TestCase):
    def test_shared_alias_is_filtered_by_supported_map(self):
        index=SceneIndex()
        terms=relevant_callouts(index,'Nuke',['up the vents'])
        self.assertEqual(len(terms),1)
        self.assertEqual(terms[0]['context'],'地图：Nuke')

    def test_unknown_map_does_not_guess_or_retrieve_everything(self):
        index=SceneIndex()
        self.assertEqual(relevant_callouts(index,None,['up the vents']),[])
        self.assertEqual(relevant_callouts(index,'Nuke',['something unrelated']),[])

    def test_combat_headshot_is_not_a_map_location_or_negated_point(self):
        index=SceneIndex()
        terms=relevant_callouts(index,'Nuke',['delivers the headshot','up the vent'])
        self.assertEqual([t['english'] for t in terms],['Vent'])
        self.assertEqual(relevant_callouts(index,'Nuke',['not up the vent']),[])


if __name__=='__main__':
    unittest.main()

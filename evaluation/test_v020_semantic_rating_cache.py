import unittest

from v020_semantic_rating_cache import frozen_judgment, preserved_count, raw_digest


class SemanticCacheTest(unittest.TestCase):
    def record(self):
        return dict(case_id=1, actual_raw='English: x\nChinese: y',
            raw_sha256=raw_digest('English: x\nChinese: y'), semantic_units=['fact'],
            english_ratings=['preserved'], chinese_ratings=['uncertain'])

    def test_identical_output_reuses_uncertain_and_does_not_count_it(self):
        r=self.record();result=frozen_judgment(1,r['actual_raw'],['fact'],[r,r])
        self.assertEqual(result['zh'],['uncertain'])
        self.assertEqual(preserved_count(result['zh']),0)

    def test_conflicting_prior_scores_cannot_choose_higher(self):
        a=self.record();b=dict(a,chinese_ratings=['preserved'])
        with self.assertRaises(ValueError):
            frozen_judgment(1,a['actual_raw'],['fact'],[a,b])

    def test_changed_reference_is_rejected(self):
        r=self.record()
        with self.assertRaises(ValueError):
            frozen_judgment(1,r['actual_raw'],['new fact'],[r])

    def test_unseen_candidate_or_case_is_not_fabricated_gold(self):
        r=self.record()
        self.assertIsNone(frozen_judgment(1,'new raw',['fact'],[r]))
        self.assertIsNone(frozen_judgment(2,r['actual_raw'],['fact'],[r]))


if __name__=='__main__':
    unittest.main()

import unittest
from v020_short_answer_validation import score, request_plan, resume_prefix


class ShortAnswerScoreTest(unittest.TestCase):
    def test_frozen_request_plan_keeps_pair_order_and_all_task_denominators(self):
        self.assertEqual(request_plan([{'id':'a'},{'id':'b'}]), [
            ('a','bilingual',''),('a','bilingual','CS2 broadcast.'),
            ('b','bilingual','CS2 broadcast.'),('b','bilingual',''),
            ('a','english','CS2 broadcast.'),('b','english','CS2 broadcast.'),
            ('a','auto_zh','CS2 broadcast.'),('b','auto_zh','CS2 broadcast.')])

    def test_resume_accepts_only_an_exact_frozen_prefix(self):
        plan=request_plan([{'id':'a'}]); classes={'parser':'sha'}
        meta=dict(type='metadata',classes=classes,case_manifest_sha256='gold',context=768,output_tokens=128,threads=4)
        row=dict(type='request',case_id='a',task='bilingual',hints='')
        self.assertEqual(resume_prefix([meta,row],classes,'gold',plan),[row])
        for rows in ([meta,row,row],[meta,dict(row,hints='CS2 broadcast.')],
                     [meta,row,dict(type='complete')],[meta,row,dict(type='resume',already_recorded=0)]):
            with self.assertRaises(RuntimeError): resume_prefix(rows,classes,'gold',plan)
        with self.assertRaises(RuntimeError): resume_prefix([meta,row],{'parser':'changed'},'gold',plan)
        with self.assertRaises(RuntimeError): resume_prefix([meta,row],classes,'different',plan)

    def test_numeric_equivalence_is_declared_not_substring_scored(self):
        case = {'label':'one', 'reference_zh_options':['1','一']}
        row = {'task':'bilingual', 'status':'subtitle', 'english':'1!', 'chinese':'一。'}
        self.assertTrue(score(row, case)['source_keyword_ok'])
        self.assertTrue(score(row, case)['translation_keyword_ok'])
        row['english'] = 'Someone'
        self.assertFalse(score(row, case)['source_keyword_ok'])

    def test_invalid_reply_cannot_get_quality_credit(self):
        row = {'task':'bilingual', 'status':'invalid', 'english':'one', 'chinese':'一'}
        result = score(row, {'label':'one','reference_zh_options':['1','一']})
        self.assertFalse(result['source_keyword_ok'])
        self.assertFalse(result['translation_keyword_ok'])

    def test_negation_and_task_denominator_remain_distinct(self):
        case = {'label':'no', 'reference_zh_options':['不','不是','否']}
        row = {'task':'bilingual', 'status':'subtitle', 'english':'No.', 'chinese':'是'}
        self.assertTrue(score(row, case)['source_keyword_ok'])
        self.assertFalse(score(row, case)['translation_keyword_ok'])
        row['task'] = 'english'
        self.assertIsNone(score(row, case)['translation_keyword_ok'])


if __name__ == '__main__':
    unittest.main()

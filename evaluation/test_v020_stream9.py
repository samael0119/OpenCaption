"""Twelve bounded instrumentation checks; not semantic quality evidence."""
import unittest
from v020_stream9 import text_chunk,reconstructions

def msg(s):return dict(role='assistant',content=[dict(type='text',text=s)])
class Instrument(unittest.TestCase):
 def test_split_label(self):self.assertEqual(reconstructions([msg('Eng'),msg('lish: A')])['delta'],'English: A')
 def test_empty(self):self.assertEqual(text_chunk(msg('')),'')
 def test_chinese_chunks(self):self.assertEqual(reconstructions([msg('Chinese: 你'),msg('好。')])['delta'],'Chinese: 你好。')
 def test_none(self):self.assertEqual(text_chunk(msg('[NONE]')),'[NONE]')
 def test_later_pair(self):self.assertIn('Chinese: 不',reconstructions([msg('English: A\nChinese: 好。'),msg('\nEnglish: B\nChinese: 不。')])['delta'])
 def test_quotes(self):self.assertEqual(text_chunk(msg('“不。”她说。')),'“不。”她说。')
 def test_decimal(self):self.assertEqual(text_chunk(msg('3.14不是3。')),'3.14不是3。')
 def test_unknown(self):
  with self.assertRaises(ValueError):text_chunk(dict(content=[dict(type='audio',text='x')]))
 def test_error(self):
  with self.assertRaises(ValueError):text_chunk(dict(content=[dict(error='failed')]))
 def test_cancellation_no_completion(self):self.assertEqual(reconstructions([])['delta'],'')
 def test_truncation_no_fake_suffix(self):self.assertEqual(text_chunk(msg('Chinese: 未完成')),'Chinese: 未完成')
 def test_cumulative_hypothesis(self):self.assertTrue(reconstructions([msg('A'),msg('AB')])['cumulative_monotonic'])
if __name__=='__main__':unittest.main()

import unittest
from v020_bridge_transport import split_response


class BridgeFramingTest(unittest.TestCase):
    def test_empty_chinese_column_is_retained_for_english_task(self):
        self.assertEqual(split_response('subtitle\tb25l\t\n'), ['subtitle','b25l',''])
        self.assertEqual(split_response('subtitle\tb25l\t\r\n'), ['subtitle','b25l',''])

    def test_empty_middle_column_and_no_speech_are_distinct(self):
        self.assertEqual(split_response('subtitle\t\t5Lit\n'), ['subtitle','','5Lit'])
        self.assertEqual(split_response('no_speech\n'), ['no_speech'])

    def test_eof_is_an_error_and_not_a_caption(self):
        with self.assertRaises(RuntimeError): split_response('')
        with self.assertRaises(RuntimeError): split_response('\n')


if __name__ == '__main__': unittest.main()

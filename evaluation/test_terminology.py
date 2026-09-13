import unittest
from terminology import Terminology


class TerminologyTest(unittest.TestCase):
    def test_guarded_replacements(self):
        rules = Terminology()
        self.assertEqual(rules.correct('They save the AWP', '他们保存武器'), '他们保枪')
        self.assertEqual(rules.correct('They force buy', '他们强制购买'), '他们强起')
        self.assertEqual(rules.correct('Save the file', '保存文件'), '保存文件')
        self.assertEqual(rules.correct('They force him back', '强制购买'), '强制购买')

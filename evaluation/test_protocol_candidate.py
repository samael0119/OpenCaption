import unittest
from protocol_candidate import parse_candidate


class CandidateTests(unittest.TestCase):
    def test_recovers_unlabeled_pair(self):
        result = parse_candidate("Hold the site.\n守住包点。")
        self.assertEqual(result.status, "subtitle")
        self.assertEqual(result.chinese, "守住包点。")

    def test_label_variants(self):
        for prefix in ("and Chinese: ", "和中文：", "和：", "and "):
            self.assertEqual(parse_candidate("Hold the site.\n" + prefix + "守住包点。").chinese, "守住包点。")
        self.assertEqual(parse_candidate("With his teammate\n和队友一起").chinese, "和队友一起")

    def test_rejects_non_bilingual_and_reasoning(self):
        for raw in ("English: Nice shot\nChinese: Nice shot", "Nice shot", "Nice shot\nGood shot",
                    "<think>Hmm</think>\nEnglish: Go\nChinese: 走", "Analysis: I should translate\n翻译一下",
                    "[NONE]\n没有", "English: Go\nChinese: [NONE]走"):
            self.assertEqual(parse_candidate(raw).status, "invalid", raw)

    def test_sentinel(self):
        self.assertEqual(parse_candidate("[NONE]").status, "no_speech")

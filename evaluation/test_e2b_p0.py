import unittest

from e2b_p0_stream import audit, closed_source
from e2e_latency_log import summarize


class EarlySourceTest(unittest.TestCase):
    def test_waits_for_complete_label(self):
        self.assertIsNone(closed_source("English: NiKo ha", True))
        self.assertIsNone(closed_source("English: NiKo has it.\nChine", True))
        self.assertEqual(closed_source("English: NiKo has it.\nChinese:", True), "NiKo has it.")

    def test_repeated_line_must_match(self):
        tagged = "English: NiKo has it.\n中文："
        self.assertIsNone(closed_source("Someone else has it.\n" + tagged, True))
        self.assertIsNone(closed_source("NiKo has it.\n" + tagged, False))
        self.assertEqual(closed_source("NiKo has it.\n" + tagged, True), "NiKo has it.")
        self.assertIsNone(closed_source("English: [NONE]\nChinese: [NONE]", True))

    def test_a_candidate_can_precede_an_invalid_final(self):
        leading = "English: They all go B.\nChinese:"
        final = leading + " no valid translation"
        result = audit(
            {"sync": {"raw": final, "ms": 1200},
             "stream": {"ms": 1250, "chunks": [(400, leading), (1100, " no valid translation")]}},
            lambda _: ("invalid", ["chinese_invalid"]),
            allow_repeated_line=True,
        )
        self.assertEqual(result["candidate_ms"], 400)
        self.assertFalse(result["candidate_matches_final"])
        self.assertIsNone(result["stream_source_ready_ms"])


class AndroidTimingTest(unittest.TestCase):
    def test_clock_join_uses_epoch_and_unions_overlapping_gaps(self):
        lines = [
            "t [audio] capture_begin epoch=2 capture_start_elapsed_ms=1000",
            "t [audio] e2e_cut_timing epoch=2 window=1 start_ms=0 end_ms=5000 cut_elapsed_ms=6010 queued_elapsed_ms=6015",
            "t [worker] e2e_window_timing epoch=2 window=1 status=subtitle queue_ms=5 inference_ms=920 parse_ms=2",
            "t [main] e2e_dispatch_timing epoch=2 window=1 elapsed_ms=6950",
            "t [main] e2e_overlay_draw_timing epoch=2 window=1 elapsed_ms=6970 source=true translation=false",
            "t [main] e2e_overlay_draw_timing epoch=3 window=1 elapsed_ms=13970 source=true translation=true",
            "t [worker] e2e_gap epoch=2 start_ms=5000 end_ms=6500 reason=queue_replaced",
            "t [worker] e2e_gap epoch=2 start_ms=6000 end_ms=7000 reason=queue_expired",
            "t [worker] e2e_gap epoch=3 start_ms=0 end_ms=1000 reason=queue_replaced",
        ]
        result = summarize(lines)
        self.assertEqual(result["gap_union_ms"], 3000)
        self.assertEqual(result["metrics"]["cut_to_overlay_draw_source"]["p50_ms"], 960)
        self.assertEqual(result["metrics"]["capture_to_first_overlay_draw_source"]["p50_ms"], 5970)
        self.assertNotIn("cut_to_overlay_draw_translation", result["metrics"])


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path
import tempfile
from v020_product_queue_summary import analyze, cue_times, read_intervals


class QueueSummaryTest(unittest.TestCase):
    def test_partial_human_unit_does_not_count_as_fully_delivered(self):
        rows = [dict(state="delivered",start_ms=0,end_ms=1000,submitted_ms=1000,started_ms=1000,at_ms=1200),
                dict(state="replaced",start_ms=1000,end_ms=2000,submitted_ms=2000,started_ms=-1,at_ms=3000)]
        result = analyze(rows, [(500, 1500)], 2000)
        self.assertEqual(result["fully_eligible_units"], 0)
        self.assertEqual(result["reference_units"][0]["eligible_fraction"], .5)
        self.assertIsNone(result["reference_units"][0]["simulated_completion_after_cue_ms"])
        self.assertEqual(result["dropped_ms"], 1000)

    def test_missing_audio_cannot_be_hidden_by_retained_rows(self):
        row = dict(state="delivered",start_ms=0,end_ms=1000,submitted_ms=1000,started_ms=1000,at_ms=1200)
        with self.assertRaises(ValueError):
            analyze([row], [(0,1000)], 2000)
        with self.assertRaises(ValueError):
            analyze([row,row], [(0,1000)], 1000)

    def test_cue_times_reject_invalid_or_outside_intervals(self):
        self.assertEqual(cue_times("1\n00:00:01,200 --> 00:00:02,500\n文字"), [(1200,2500)])
        with self.assertRaises(ValueError):
            cue_times("00:00:02,500 --> 00:00:01,200")
        row = dict(state="delivered",start_ms=0,end_ms=1000,submitted_ms=1000,started_ms=1000,at_ms=1200)
        with self.assertRaises(ValueError):
            analyze([row], [(0,2000)], 1000)

    def test_failed_or_old_junit_output_cannot_supply_new_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"suite.xml"
            path.write_text('<testsuite name="dev.opencaption.opencaption.E2eQueueReplayTest" failures="1" errors="0"/>')
            with self.assertRaises(ValueError):
                read_intervals(path)
            path.write_text('<testsuite name="dev.opencaption.opencaption.E2eQueueReplayTest" failures="0" errors="0"><testcase name="measuredNormalAndInjectedSlowTracesAccountForEveryAudioInterval"/></testsuite>')
            with self.assertRaises(ValueError):
                read_intervals(path)


if __name__ == "__main__":
    unittest.main()

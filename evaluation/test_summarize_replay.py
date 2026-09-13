import json
import tempfile
import unittest
from pathlib import Path

from summarize_replay import summarize


class ReplaySummaryTest(unittest.TestCase):
    def test_fifo_accumulates_and_resets_between_passes(self):
        rows = [dict(type="window", source="clip.wav", index=i,
                     start_ms=(i - 1) * 2500, end_ms=(i - 1) * 2500 + 3000,
                     inference_ms=3500, status="subtitle", **{"pass": p})
                for p, i in [(1, 1), (1, 2), (2, 1)]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows))
            result = summarize(path)
        self.assertEqual(result["simulated_fifo_max_wait_ms"], 1000)
        self.assertEqual(result["simulated_fifo_mean_window_start_to_output_ms"], 6833)
        self.assertEqual(result["p95_inference_ms"], 3500)


if __name__ == "__main__":
    unittest.main()

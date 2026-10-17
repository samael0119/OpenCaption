import unittest
from pathlib import Path
import tempfile
from v020_resource_monitor import model_pids
from v020_stability_summary import summarize, resources


def fixture():
    rows = [dict(type='metadata', origin_monotonic=100., input_seconds=3600)]
    rows += [dict(type='request', slot=i, target_monotonic=105.+i*5,
                  kind='instrumental_music' if i%7==0 else 'published_read_speech',
                  case_id=str(i%28), status='subtitle', inference_ms=2000.,
                  lag_ms=.1, peak_rss_kib=2000000) for i in range(720)]
    rows += [dict(type='complete', requests=720, input_seconds=3600, actual_elapsed_seconds=3602.)]
    return rows


class StabilitySummaryTest(unittest.TestCase):
    def test_sampler_excludes_timeout_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            for pid, command in [(1, b'/usr/bin/timeout'), (2, b'/usr/bin/python3')]:
                entry = proc / str(pid)
                entry.mkdir()
                (entry/'cmdline').write_bytes(command+b'\0evaluation/v020_runtime_validation.py\0stability\0')
            self.assertEqual(model_pids(proc), [2])

    def test_complete_clock_and_unique_sample_count(self):
        result = summarize(fixture())
        self.assertTrue(result['integrity_pass'])
        self.assertEqual(result['unique_cases'], 28)
        self.assertEqual(result['music_visible_hallucinations'], 103)

    def test_inflight_is_never_complete(self):
        self.assertFalse(summarize(fixture()[:-1])['integrity_pass'])
        self.assertFalse(summarize(fixture(), partial=True)['integrity_pass'])

    def test_short_clock_and_missing_slots_rejected(self):
        for field, value in [('actual_elapsed_seconds', 3599), ('requests', 719)]:
            rows = fixture()
            rows[-1][field] = value
            self.assertFalse(summarize(rows)['integrity_pass'])
        rows = fixture()
        rows[10]['slot'] = 0
        self.assertFalse(summarize(rows)['integrity_pass'])

    def test_misleading_schedule_is_rejected(self):
        rows = fixture()
        rows[20]['target_monotonic'] += 10
        self.assertIn('target_schedule_mismatch', summarize(rows)['issues'])

    def test_nonfinite_elapsed_is_rejected(self):
        rows = fixture()
        rows[-1]['actual_elapsed_seconds'] = float('nan')
        self.assertFalse(summarize(rows)['integrity_pass'])

    def test_resource_limits_and_swap_failure_are_visible(self):
        rows = [dict(type='sample', pid=1, monotonic=i*15, rss_kib=100+i,
                     swap_kib=i, memory_swap_current_bytes=0, memory_max_bytes=6144*1024**2,
                     memory_swap_max_bytes=0, events={'oom_kill':0}) for i in range(2)]
        result = resources(rows)['processes']['1']
        self.assertTrue(result['hard_limits_ok'])
        self.assertTrue(result['swap_seen'])
        self.assertEqual(result['sampled_seconds'], 15)


if __name__ == '__main__':
    unittest.main()

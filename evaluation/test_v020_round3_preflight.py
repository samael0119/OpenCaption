import unittest

from v020_round3_preflight import authorized, requested_config, compare_configs


class ExecutionPathSafetyTest(unittest.TestCase):
    def test_only_flag_changes_and_auto_none_is_not_false(self):
        a=requested_config('auto');b=requested_config('disabled')
        self.assertIsNone(a['enable_speculative_decoding'])
        self.assertIs(b['enable_speculative_decoding'],False)
        self.assertEqual(compare_configs(a,b),['enable_speculative_decoding'])
        self.assertEqual(b['max_num_tokens'],768)

    def test_context_cannot_silently_fall_back_when_disabled(self):
        a=requested_config('auto');b=requested_config('disabled');b['max_num_tokens']=None
        with self.assertRaises(ValueError): compare_configs(a,b)

    def test_sampler_cannot_be_changed_with_execution_path(self):
        a=requested_config('auto');b=requested_config('disabled');b['top_k']=2
        with self.assertRaises(ValueError): compare_configs(a,b)

    def test_legacy_small_candidate_counts_do_not_block_round3(self):
        authorized(dict(status='active',current_round=3,
            consecutive_complete_rounds_without_gain=2,
            consecutive_evaluation_packages_without_verified_gain=3,
            actual_work_seconds_since_verified_gain=999999),dict(status='ACTIVE'))

    def test_pause_and_three_complete_rounds_still_stop(self):
        for state,auto in [(dict(status='paused',current_round=3),'ACTIVE'),
            (dict(status='active',current_round=3,consecutive_complete_rounds_without_gain=3),'ACTIVE'),
            (dict(status='active',current_round=3),'PAUSED')]:
            with self.assertRaises(RuntimeError): authorized(state,dict(status=auto))


if __name__=='__main__':
    unittest.main()

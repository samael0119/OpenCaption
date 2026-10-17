"""Budget persistence and human pause guards; no inference."""
import unittest
from v020_coupling_candidate import authorized, reserve_candidate, DIRECTION


class CouplingGuardTest(unittest.TestCase):
    def test_material_gap_does_not_block_development(self):
        authorized({'status': 'active', 'gates': {'G2': 'in_progress'},
                    'materials_packages_used': 2, 'materials_packages_limit': 2}, {'status': 'ACTIVE'})

    def test_human_pause_blocks(self):
        with self.assertRaises(RuntimeError):
            authorized({'status': 'active', 'gates': {'G2': 'in_progress'}}, {'status': 'PAUSED'})

    def test_one_reservation_consumes_one_candidate(self):
        state = reserve_candidate({'candidate_attempts': {DIRECTION: 0}})
        self.assertEqual(state['candidate_attempts'][DIRECTION], 1)

    def test_existing_reservation_not_reset(self):
        state = reserve_candidate({'candidate_attempts': {DIRECTION: 1}})
        self.assertEqual(state['candidate_attempts'][DIRECTION], 2)

    def test_third_candidate_rejected(self):
        with self.assertRaises(RuntimeError):
            reserve_candidate({'candidate_attempts': {DIRECTION: 2}})

    def test_overall_no_gain_budget_still_blocks(self):
        with self.assertRaises(RuntimeError):
            authorized({'status': 'active', 'gates': {'G2': 'in_progress'},
                        'consecutive_evaluation_packages_without_verified_gain': 3}, {'status': 'ACTIVE'})


if __name__ == '__main__':
    unittest.main()

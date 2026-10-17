"""Meaningful pause/budget guards for unattended inference, without a model."""
import unittest
from v020_convergence_g1 import authorized


class AuthorizationTest(unittest.TestCase):
    def state(self, **overrides):
        return dict(status='active', gates={'G1': 'in_progress'}, **overrides)

    def test_resumed_g1_does_not_require_long_stability(self):
        authorized(self.state(), {'status': 'ACTIVE'})

    def test_automation_pause_blocks_inference(self):
        with self.assertRaises(RuntimeError):
            authorized(self.state(), {'status': 'PAUSED'})

    def test_non_current_gate_blocks_inference(self):
        with self.assertRaises(RuntimeError):
            authorized({'status': 'active', 'gates': {'G1': 'pending'}}, {'status': 'ACTIVE'})

    def test_state_pause_blocks_inference(self):
        with self.assertRaises(RuntimeError):
            authorized({'status': 'paused', 'gates': {'G1': 'in_progress'}}, {'status': 'ACTIVE'})

    def test_work_limit_blocks_inference(self):
        with self.assertRaises(RuntimeError):
            authorized(self.state(actual_work_seconds_since_verified_gain=21600), {'status': 'ACTIVE'})

    def test_evaluation_limit_blocks_inference(self):
        with self.assertRaises(RuntimeError):
            authorized(self.state(consecutive_evaluation_packages_without_verified_gain=3), {'status': 'ACTIVE'})


if __name__ == '__main__':
    unittest.main()

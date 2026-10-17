import unittest
from v020_joint_live_summary import partition


class OwnershipAudit(unittest.TestCase):
    def test_merge_keeps_complete_partition(self):
        partition([(0, 3200), (3200, 8200), (8200, 9000)], 9000)

    def test_missing_and_overlap_do_not_pass(self):
        for rows in [[(0, 3000), (4000, 9000)], [(0, 5000), (4000, 9000)], [(0, 8000)]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                partition(rows, 9000)


if __name__ == '__main__':
    unittest.main()

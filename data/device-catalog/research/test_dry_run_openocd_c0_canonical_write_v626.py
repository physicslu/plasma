import json
import unittest

import dry_run_openocd_c0_canonical_write_v626 as d


class TestOpenOCDC0CanonicalWriteDryRunV626(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delta, cls.post, cls.summary = d.build()

    def test_exact_four_row_transaction(self):
        self.assertEqual(self.summary["canonical_preimage"]["row_count"],7657)
        self.assertEqual(self.summary["canonical_postimage"]["row_count"],7661)
        self.assertEqual(self.summary["delta_invariants"],{
            "added_rows":4,
            "removed_rows":0,
            "mutated_existing_rows":0,
            "duplicate_keys":0,
        })

    def test_preimage_lease(self):
        self.assertEqual(
            self.summary["canonical_preimage"]["git_blob_sha"],
            "0ef056e3363e20bb527590c4a4cc1cc0d7afb810",
        )

    def test_frozen_postimage(self):
        self.assertEqual(
            self.summary["canonical_postimage"]["git_blob_sha"],
            "81e44f6a6df902f3b206d06bfac38e37ec74630b",
        )
        self.assertEqual(
            self.summary["canonical_postimage"]["sha256"],
            "39bb6f17765b8c95fdf1cdfa9831ac1c71ef3edd08ae899fcf6f67eae4234751",
        )
        self.assertEqual(self.summary["canonical_postimage"]["byte_count"],1583487)
        self.assertEqual(self.summary["postimage_lock_state"],"FROZEN")

    def test_source_delta_is_v625_exact(self):
        self.assertEqual(
            self.summary["source_delta"]["sha256"],
            "5d6f2b022a0efab409f57dece8cfcb06dace9cbf93c4a533beef9b4ecbf84b24",
        )
        self.assertEqual(self.summary["source_delta"]["row_count"],4)

    def test_inventory_write_does_not_change_production_state(self):
        self.assertEqual(self.summary["production_state_unchanged"]["mapped"],4054)
        self.assertEqual(self.summary["production_state_unchanged"]["no_mapping"],575)
        self.assertEqual(
            self.summary["production_state_unchanged"]["active_openocd_route_exact_count"],3975
        )

    def test_actual_write_requires_source_materialization_and_approval(self):
        reqs=self.summary["actual_write_requirements"]
        self.assertTrue(reqs["materialize_source_delta_same_transaction"])
        self.assertTrue(reqs["owner_approval_required"])

    def test_no_write_authority(self):
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))


if __name__=="__main__":
    unittest.main()

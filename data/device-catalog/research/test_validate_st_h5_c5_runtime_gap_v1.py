import copy
import unittest

import validate_st_h5_c5_runtime_gap_v1 as v

class TestStH5C5RuntimeGapV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = v.read_json(v.EVIDENCE)

    def test_frozen_362_cohort_reconciles(self):
        result = v.validate()
        self.assertEqual((result["h5_runtime_blocked"], result["c5_runtime_blocked"]), (190, 172))
        self.assertEqual((result["mapped"], result["no_mapping"]), (4164, 465))
        self.assertFalse(result["hardware_runtime_ready"])
        self.assertFalse(result["production_write_authorized"])

    def test_unauthorized_h5_promotion_fails_closed(self):
        payload = copy.deepcopy(self.evidence)
        payload["production_gates"]["h5_erase_program_verify_qualified"] = True
        with self.assertRaisesRegex(ValueError, "fail closed"):
            v.validate(payload)

    def test_unauthorized_c5_runtime_promotion_fails_closed(self):
        payload = copy.deepcopy(self.evidence)
        payload["production_gates"]["c5_pinned_local_loader_table_deployed"] = True
        with self.assertRaisesRegex(ValueError, "fail closed"):
            v.validate(payload)

    def test_catalog_count_must_be_rebaselined_explicitly(self):
        payload = copy.deepcopy(self.evidence)
        payload["catalog_baseline"]["mapped"] += 1
        with self.assertRaisesRegex(ValueError, "mapping partition"):
            v.validate(payload)

    def test_candidate_fork_pin_must_not_drift(self):
        payload = copy.deepcopy(self.evidence)
        payload["candidate_st_fork"]["commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "vendor fork pin"):
            v.validate(payload)

if __name__ == "__main__":
    unittest.main()

"""Negative gate tests for ST C5 backend source candidate."""
from __future__ import annotations
import copy
import json
import unittest
import validate_st_c5_backend_source_v08 as check

class BackendGateTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(check.REPORT.read_text(encoding="utf-8"))

    def rejected(self, mutation):
        value = copy.deepcopy(self.snapshot)
        mutation(value)
        with self.assertRaises(ValueError):
            check.validate(report=value)

    def test_locked_candidate_remains_blocked(self):
        self.assertEqual(172, check.validate()["observed_exact_C5_codes"])

    def test_cannot_claim_loader_mapping(self):
        self.rejected(lambda o: o["st_openocd_fork"]["target_config"].update(
            {"loader_table_has_pinned_paths": True}))

    def test_no_production_admission(self):
        self.rejected(lambda o: o["gate_state"].update({"production_write_authorized": True}))

    def test_backend_compile_not_assumed(self):
        self.rejected(lambda o: o["gate_state"].update(
            {"actual_plasma_backend_stldr_compiled_verified": True}))

    def test_cubeprog_license_cannot_promote_prod_backend(self):
        self.rejected(lambda o: o["alternate_tool_boundary"].update(
            {"may_be_treated_as_plasma_production_backend": True}))

    def test_st_fork_script_pin(self):
        self.rejected(lambda o: o["st_openocd_fork"]["target_config"].update(
            {"git_blob_sha": "0" * 40}))

if __name__ == "__main__":
    unittest.main()

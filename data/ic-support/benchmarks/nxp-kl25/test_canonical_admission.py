from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for name in ("post_review_disposition", "canonical_admission"):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
import canonical_admission as admission
import post_review_disposition as disposition


class CanonicalAdmissionTests(unittest.TestCase):
    def test_accept_does_not_imply_projection_or_execution(self):
        self.assertFalse(disposition.CONTRACT["trust_boundary"]["accept_implies_canonical_admission"])
        self.assertEqual(admission.CONTRACT["trust_boundary"]["software_executor_operation_admission"], "PER_OPERATION_ONLY")

    def test_operation_scope_is_frozen(self):
        self.assertEqual(admission.CONTRACT["candidate_operation_set"], ["READ", "VERIFY", "PROGRAM", "ERASE_SECTOR"])
        self.assertIn("MDM_MASS_ERASE", admission.CONTRACT["forbidden_operations"])
        self.assertIn("FLASH_CONFIGURATION_FIELD_SECTOR_ERASE", admission.CONTRACT["forbidden_operations"])

    def test_exact_target_uses_datasheet(self):
        evidence = admission.CONTRACT["required_target_evidence"]
        self.assertEqual(evidence["source_id"], "nxp_kl25_ds_rev5")
        self.assertEqual(evidence["pdf_page_number"], 2)


if __name__ == "__main__":
    unittest.main()

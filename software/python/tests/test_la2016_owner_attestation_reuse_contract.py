#!/usr/bin/env python3
"""Offline contracts for reusing Owner LA2016 passive-input safety evidence.

Never opens USB, runs Sigrok, or performs hardware observation.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
LA_RUNBOOK = ROOT / "docs/development/la2016-tool-operations.md"
PATH3_GUIDE = ROOT / "docs/development/plasma-path3-direct-hardware-tools.md"


class OwnerAttestationReuseContract(unittest.TestCase):
    def test_passive_capture_reuses_valid_owner_evidence_without_new_gate(self):
        for path in (LA_RUNBOOK, PATH3_GUIDE):
            with self.subTest(file=path.name):
                doc = path.read_text(encoding="utf-8")
                self.assertIn("OWNER_ELECTRICAL_ATTESTATION_REUSE", doc)
                self.assertIn("不要求每次", doc)
                self.assertIn("共地", doc)
                self.assertIn("NOT_RUN", doc)

    def test_true_hazards_and_device_boundaries_are_preserved(self):
        runbook = LA_RUNBOOK.read_text(encoding="utf-8")
        path3 = PATH3_GUIDE.read_text(encoding="utf-8")
        self.assertIn("實際發現超出輸入規格的電壓", runbook)
        self.assertIn("真實電氣危險", path3)
        for doc in (runbook, path3):
            with self.subTest(source="runbook" if doc == runbook else "path3"):
                self.assertIn("Linux DAC/ACL", doc)
                self.assertIn("PWM1", doc)
                self.assertIn("Driver", doc)
        self.assertIn("Root Guard", path3)

    def test_previous_work_order_failure_not_claimed_as_hardware_pass(self):
        for path in (LA_RUNBOOK, PATH3_GUIDE):
            doc = path.read_text(encoding="utf-8")
            self.assertIn("40495187390", doc)
            self.assertIn("零次擷取", doc)
            self.assertIn("NOT_RUN", doc)


if __name__ == "__main__":
    unittest.main()

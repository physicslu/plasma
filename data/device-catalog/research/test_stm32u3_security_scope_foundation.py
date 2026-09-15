#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from validate_stm32u3_security_scope_foundation import validate

HERE = Path(__file__).resolve().parent
FOUNDATION = json.loads((HERE / "stm32u3-security-scope-foundation.json").read_text(encoding="utf-8"))
UPSTREAM = json.loads((HERE / "stm32-trustzone-cohort-succession-after-l5-blocker.json").read_text(encoding="utf-8"))


class SecurityScopeFoundationTests(unittest.TestCase):
    def test_frozen_foundation_passes(self) -> None:
        validate(copy.deepcopy(FOUNDATION), copy.deepcopy(UPSTREAM))

    def test_wrong_upstream_family_fails(self) -> None:
        upstream = copy.deepcopy(UPSTREAM)
        upstream["succession_policy"]["selected_series"] = "STM32U5"
        with self.assertRaises(ValueError):
            validate(copy.deepcopy(FOUNDATION), upstream)

    def test_u3_rdp2_may_not_be_declared_unconditionally_terminal(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["u3_specific_security_invariants"]["rdp2_is_unconditionally_terminal"] = True
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_oem_key_state_may_not_be_inferred(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["u3_specific_security_invariants"]["plasma_may_not_infer_oem_key_state"] = False
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_oem_unlock_execution_remains_blocked(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["research_partition"]["oem_unlock_execution_allowed"] = True
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_runtime_claim_cannot_be_enabled(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["research_partition"]["runtime_programming_supported"] = True
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_non_manufacturer_source_fails(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["manufacturer_sources"][0]["url"] = "https://example.com/stm32u3"
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_production_count_drift_fails(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["exact_icpn_count"] = 1863
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from validate_stm32l5_security_scope_foundation import validate

HERE = Path(__file__).resolve().parent
FOUNDATION = json.loads((HERE / "stm32l5-security-scope-foundation.json").read_text(encoding="utf-8"))
UPSTREAM = json.loads((HERE / "stm32-trustzone-cohort-gate1-qualification.json").read_text(encoding="utf-8"))


class SecurityScopeFoundationTests(unittest.TestCase):
    def test_frozen_foundation_passes(self) -> None:
        validate(copy.deepcopy(FOUNDATION), copy.deepcopy(UPSTREAM))

    def test_wrong_selected_family_fails(self) -> None:
        upstream = copy.deepcopy(UPSTREAM)
        upstream["selected_for_next_research"] = "STM32U5"
        with self.assertRaises(ValueError):
            validate(copy.deepcopy(FOUNDATION), upstream)

    def test_runtime_claim_cannot_be_enabled(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["research_partition"]["runtime_programming_supported"] = True
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_destructive_security_operation_cannot_be_enabled(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["research_partition"]["mass_erase_allowed"] = True
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_non_manufacturer_source_fails(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["manufacturer_sources"][0]["url"] = "https://example.com/stm32l5"
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))

    def test_security_control_removal_fails(self) -> None:
        payload = copy.deepcopy(FOUNDATION)
        payload["security_sensitive_controls"].remove("TZEN")
        with self.assertRaises(ValueError):
            validate(payload, copy.deepcopy(UPSTREAM))


if __name__ == "__main__":
    unittest.main(verbosity=2)

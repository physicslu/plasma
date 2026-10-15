from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "st_phase1_information_v1.py"
SPEC = importlib.util.spec_from_file_location("st_phase1_information_v1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def exact(records, icpn):
    return next(row for row in records if row["icpn"] == icpn)


class STPhase1InformationBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.summary = MODULE.build()

    def test_reconciles_full_production_and_field_denominators(self):
        records, summary = self.records, self.summary

        self.assertEqual(len(records), 4629)
        self.assertEqual(summary["exact_icpn_count"], 4629)
        self.assertEqual(summary["existing_source_backed_basic_bindings"], 1622)
        self.assertEqual(summary["legacy_m1_blocked_exact_icpns"], 3007)

        for field in MODULE.FIELDS:
            states = summary["field_coverage"][field]
            self.assertEqual(set(states), set(MODULE.STATES))
            self.assertEqual(sum(states.values()), 4629)

        # Existing M1 evidence becomes field-level evidence, not a package gate.
        self.assertEqual(summary["field_coverage"]["ram"]["VERIFIED"], 1622)
        self.assertEqual(summary["field_coverage"]["working_vdd"]["VERIFIED"], 1622)
        self.assertEqual(summary["field_coverage"]["ram"]["UNKNOWN"], 3007)
        self.assertEqual(summary["field_coverage"]["working_vdd"]["UNKNOWN"], 3007)

        # Exact Production identity fields remain independently useful for all ST rows.
        for field in (
            "manufacturer",
            "icpn",
            "base_device",
            "package",
            "pin_count",
            "flash",
            "temperature",
        ):
            self.assertEqual(summary["field_coverage"][field]["VERIFIED"], 4629)

    def test_preserves_known_fields_when_other_fields_are_unknown(self):
        f407 = exact(self.records, "STM32F407VGT6")
        self.assertEqual(f407["fields"]["flash"]["value"], "1024 KiB")
        self.assertEqual(f407["fields"]["flash"]["state"], "VERIFIED")
        self.assertEqual(f407["fields"]["ram"]["state"], "UNKNOWN")
        self.assertEqual(f407["fields"]["working_vdd"]["state"], "UNKNOWN")
        self.assertEqual(
            f407["legacy_m1_context"]["disposition"], "blocked_evidence_gap"
        )

        # H5's conditional temperature text was a legacy M1 model blocker. Phase 1
        # preserves the original manufacturer wording instead of flattening it.
        h5 = exact(self.records, "STM32H503CBT7")
        self.assertEqual(h5["fields"]["temperature"]["state"], "VERIFIED")
        self.assertIn(
            "up to 125 at low dissipation", h5["fields"]["temperature"]["value"]
        )
        self.assertEqual(h5["fields"]["ram"]["state"], "UNKNOWN")

    def test_projects_existing_ram_vdd_without_programming_claims(self):
        f103 = exact(self.records, "STM32F103C8T6")
        self.assertEqual(f103["fields"]["ram"]["value"], "20 KiB")
        self.assertEqual(f103["fields"]["ram"]["state"], "VERIFIED")
        self.assertEqual(
            f103["fields"]["working_vdd"]["value"], {"min": 2, "max": 3.6}
        )
        self.assertEqual(f103["fields"]["working_vdd"]["state"], "VERIFIED")

        for row in self.records:
            self.assertEqual(row["phase"], "IC_INFORMATION")
            self.assertFalse(row["non_claims"]["production_admission_changed"])
            self.assertFalse(row["non_claims"]["openocd_software_supported"])
            self.assertFalse(row["non_claims"]["programming_profile_authority"])
            self.assertFalse(row["non_claims"]["external_vpp_evaluated"])
            self.assertFalse(row["non_claims"]["hardware_runtime_ready"])
            self.assertFalse(row["non_claims"]["physical_programming_qualified"])
            self.assertNotIn("vpp", row["fields"])


if __name__ == "__main__":
    unittest.main()

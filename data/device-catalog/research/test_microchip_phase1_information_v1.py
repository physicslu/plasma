#!/usr/bin/env python3
"""Phase 1 only: Microchip manufacturer information evidence regression."""
from __future__ import annotations
from copy import deepcopy
import json
import unittest

from microchip_phase1_information_v1 import DEFAULT_PATH, check


class MicrochipPhase1InformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))

    def test_two_exact_microchip_ordering_rows_remain_research_only(self):
        result = check(self.dataset)
        self.assertEqual(result["research_exact_identity_observations"], 2)
        self.assertEqual(result["internal_admission_states"], {"NOT_ADMITTED": 2})
        self.assertEqual(result["production_rows_written"], 0)
        self.assertIsNone(result["software_supported_count"])
        self.assertFalse(result["phase2_or_phase3_activity"])

    def test_per_field_denominator_and_gaps(self):
        report = check(self.dataset)
        coverage = report["per_field_coverage"]
        for field, counts in coverage.items():
            with self.subTest(field=field):
                self.assertEqual(sum(counts.values()), 2)
        self.assertEqual(coverage["icpn"]["VERIFIED"], 2)
        self.assertEqual(coverage["package"]["VERIFIED"], 2)
        self.assertEqual(coverage["pin_count"]["VERIFIED"], 2)
        self.assertEqual(coverage["temperature"]["VERIFIED"], 2)
        self.assertEqual(coverage["flash"]["PARTIAL"], 2)
        self.assertEqual(coverage["vdd"]["PARTIAL"], 2)
        self.assertEqual(coverage["io_supply"]["UNKNOWN"], 2)
        self.assertEqual(coverage["vdda"]["UNKNOWN"], 2)
        self.assertEqual(coverage["base_device"]["UNKNOWN"], 2)
        self.assertEqual(report["sources_with_original_raw_bytes"], 0)

    def test_temperature_changes_with_exact_ordering_suffix(self):
        by_icpn = {r["icpn"]: r for r in self.dataset["records"]}
        self.assertEqual(
            by_icpn["ATSAMD21G18A-MU"]["fields"]["temperature"]["value"],
            {"min": -40, "max": 85})
        self.assertEqual(
            by_icpn["ATSAMD21G18A-MF"]["fields"]["temperature"]["value"],
            {"min": -40, "max": 125})
        check(self.dataset)

    def test_cannot_elevate_family_flash_to_exact_verified(self):
        invalid = deepcopy(self.dataset)
        invalid["records"][0]["fields"]["flash"]["status"] = "VERIFIED"
        with self.assertRaisesRegex(ValueError, "family-level fact"):
            check(invalid)

    def test_unknown_is_not_numeric_zero(self):
        invalid = deepcopy(self.dataset)
        invalid["records"][0]["fields"]["io_supply"]["value"] = 0
        with self.assertRaisesRegex(ValueError, "unknown/conflict falsely populated"):
            check(invalid)

    def test_unknown_base_device_not_parsed_from_icpn(self):
        invalid = deepcopy(self.dataset)
        invalid["records"][0]["fields"]["base_device"]["value"] = "ATSAMD21G18A"
        with self.assertRaisesRegex(ValueError, "unknown/conflict falsely populated"):
            check(invalid)

    def test_duplicate_icpn_cannot_silently_override_conflicting_row(self):
        invalid = deepcopy(self.dataset)
        invalid["records"][1]["icpn"] = invalid["records"][0]["icpn"]
        with self.assertRaisesRegex(ValueError, "duplicate/conflicting exact ICPN"):
            check(invalid)

    def test_missing_field_or_source_fails_closed(self):
        invalid = deepcopy(self.dataset)
        del invalid["records"][0]["fields"]["ram"]
        with self.assertRaisesRegex(ValueError, "missing/extra"):
            check(invalid)
        invalid = deepcopy(self.dataset)
        invalid["records"][0]["fields"]["package"]["source_id"] = "untrusted"
        with self.assertRaisesRegex(ValueError, "traceable"):
            check(invalid)

    def test_original_capture_sha_must_not_be_fabricated(self):
        invalid = deepcopy(self.dataset)
        invalid["source_records"][0]["raw_capture_retained"] = True
        with self.assertRaisesRegex(ValueError, "integrity falsely"):
            check(invalid)

    def test_forged_phase2_phase3_or_production_claim_rejected(self):
        for name in ("phase2_programming_authorized",
                     "phase3_compatibility_authorized",
                     "production_write_authorized",
                     "catalog_publication_authorized",
                     "software_supported_claimed", "hardware_verified_claimed"):
            invalid = deepcopy(self.dataset)
            invalid[name] = True
            with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, "unauthorized claim"):
                check(invalid)

    def test_programming_or_runtime_fields_cannot_be_inserted(self):
        invalid = deepcopy(self.dataset)
        invalid["records"][0]["openocd_software_support"] = "SUPPORTED"
        with self.assertRaisesRegex(ValueError, "programming fields forbidden"):
            check(invalid)

    def test_source_scope_cannot_be_misrepresented(self):
        invalid = deepcopy(self.dataset)
        invalid["records"][0]["fields"]["temperature"]["evidence_scope"] = (
            "base_device_family_parametrics")
        with self.assertRaisesRegex(ValueError, "family-level fact"):
            check(invalid)


if __name__ == "__main__":
    unittest.main()

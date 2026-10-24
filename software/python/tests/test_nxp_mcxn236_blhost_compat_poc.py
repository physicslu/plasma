"""No-DUT MCXN236VKLT L2 compatibility experiment and fail-closed regression."""
from __future__ import annotations

import unittest

from plasma_web import nxp_mcxn236_blhost_compat_poc as poc
from plasma_web.programming_qualification import get_default_programming_qualification_registry


GOOD_PROPERTIES = {
    "flash_start": 0,
    "flash_size_in_bytes": 1024 * 1024,
    "flash_sector_size": 8192,
    "security_state": "OPEN",
    "available_commands": (
        "get-property", "flash-erase-region", "write-memory", "read-memory",
    ),
}


class CompatibilityTests(unittest.TestCase):
    def test_version_and_source_are_pinned_and_pdf_not_falsely_locked(self):
        self.assertEqual(poc.EXACT_ICPN, "MCXN236VKLT")
        self.assertEqual(poc.SEC_VERSION, "26.06")
        self.assertEqual(poc.SPSDK_VERSION, "3.10.0")
        self.assertEqual(len(poc.SEC_RELEASE_SHA256), 64)
        self.assertIn("MCXN23x.pdf", poc.DATASHEET_URL)
        self.assertFalse(poc.PROTECTED_REGION_MAP_QUALIFIED)

    def test_does_not_override_live_qualification_or_l1_dependency(self):
        registry = get_default_programming_qualification_registry()
        before = registry.describe("NXP", poc.EXACT_ICPN)
        self.assertNotEqual(before["catalog_level"], 2)
        status = poc.canonical_admission_status(registry)
        self.assertEqual(status["has_l1_prerequisite"], before["catalog_level"] == 1)
        self.assertFalse(status["l2_qualified"])
        self.assertFalse(status["execution_authorized"])
        self.assertEqual(before, registry.describe("NXP", poc.EXACT_ICPN))

    def test_absent_admission_is_blocked_not_promoted_by_poc(self):
        class FakeRegistry:
            def describe(self, *_args):
                return {"catalog_level": 0, "state": "UNKNOWN"}

        status = poc.canonical_admission_status(FakeRegistry())
        self.assertEqual(status["software_state"], "BLOCKED")
        self.assertFalse(status["has_l1_prerequisite"])

    def test_good_synthetic_rom_properties_are_still_only_candidate(self):
        result = poc.mock_probe_properties(GOOD_PROPERTIES)
        self.assertEqual(result["software_state"], "CANDIDATE")
        self.assertFalse(result["exact_icpn_confirmed"])
        self.assertFalse(result["physical_programming_qualified"])
        self.assertTrue(result["mock_only"])

    def test_identity_is_not_inferred_from_equal_flash_size(self):
        wrong = {**GOOD_PROPERTIES, "reported_product": "MCXN235"}
        self.assertFalse(poc.mock_probe_properties(wrong)["exact_icpn_confirmed"])

    def test_invalid_geometry_and_security_fail_closed(self):
        cases = (
            ("flash_start", 0x1000),
            ("flash_size_in_bytes", 512 * 1024),
            ("flash_sector_size", 4096),
            ("security_state", "CLOSED"),
            ("security_state", None),
            ("flash_size_in_bytes", True),
            ("flash_size_in_bytes", 1024 * 1024 + 1),
        )
        for field, bad in cases:
            with self.subTest(field=field, bad=bad):
                with self.assertRaises(poc.CompatibilityBlocked):
                    poc.mock_probe_properties({**GOOD_PROPERTIES, field: bad})

    def test_missing_rom_operation_blocks(self):
        for op in GOOD_PROPERTIES["available_commands"]:
            remaining = tuple(c for c in GOOD_PROPERTIES["available_commands"] if c != op)
            with self.subTest(op=op):
                with self.assertRaises(poc.CompatibilityBlocked):
                    poc.mock_probe_properties({**GOOD_PROPERTIES, "available_commands": remaining})

    def test_full_sector_erase_and_page_program_only_mock(self):
        erase = poc.plan_mock_operation("erase", 0x2000, 8192)
        self.assertEqual((erase.start, erase.length, erase.memory_id), (0x2000, 8192, 0))
        self.assertTrue(erase.mock_only)
        write = poc.plan_mock_operation("program", 0x2000, 128)
        self.assertTrue(write.mock_only)
        self.assertTrue(poc.plan_mock_operation("read", 0x2000, 7).mock_only)
        self.assertTrue(poc.plan_mock_operation("verify", 0x2000, 7).mock_only)
        self.assertTrue(poc.plan_mock_operation("program", 1024 * 1024 - 128, 128).mock_only)

    def test_partial_sector_page_and_out_of_bounds_fail_closed(self):
        for op, start, length in (
            ("erase", 1, 8192),
            ("erase", 8192, 8191),
            ("program", 127, 128),
            ("program", 128, 129),
            ("program", 1024 * 1024 - 64, 128),
            ("erase", 1024 * 1024 - 8192, 16384),
            ("read", 1024 * 1024, 1),
            ("verify", 0, 0),
            ("program", -128, 128),
            ("read", 0, True),
            ("erase", False, 8192),
        ):
            with self.subTest(op=op, start=start, length=length):
                with self.assertRaises(poc.CompatibilityBlocked):
                    poc.plan_mock_operation(op, start, length)

    def test_dangerous_operations_and_mock_failure_blocked(self):
        for op in ("mass-erase", "flash-erase-all", "fuse-program", "unlock",
                   "configure-memory", "hsm-provision", "reset"):
            with self.subTest(operation=op):
                with self.assertRaises(poc.CompatibilityBlocked):
                    poc.plan_mock_operation(op, 0, 8192)
        for reply in (None, {}, {"operation": "erase", "status": "SUCCESS"},
                      {"operation": "erase", "status": "TIMEOUT", "complete": True},
                      {"operation": "erase", "status": "SUCCESS", "complete": False},
                      {"operation": "program", "status": "SUCCESS", "complete": True}):
            with self.subTest(reply=reply):
                with self.assertRaises(poc.CompatibilityBlocked):
                    poc.validate_mock_reply("erase", reply)
        poc.validate_mock_reply("erase", {"operation": "erase", "status": "SUCCESS", "complete": True})
        with self.assertRaises(poc.CompatibilityBlocked):
            poc.compare_mock_readback(b"\x01\x02", b"\x01\x03")
        poc.compare_mock_readback(b"\x01\x02", b"\x01\x02")

    def test_qualification_gap_never_supported_or_registered(self):
        result = poc.qualification_gap()
        self.assertEqual(result["software_state"], "CANDIDATE")
        self.assertFalse(result["registered_provider"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["installed_runtime_attested"])
        self.assertFalse(result["physical_programming_qualified"])
        self.assertIn("MCXN_31_CANONICAL_L1_NOT_ADMITTED", result["missing"])
        self.assertEqual(result["operations_qualified"], ())


if __name__ == "__main__":
    unittest.main()

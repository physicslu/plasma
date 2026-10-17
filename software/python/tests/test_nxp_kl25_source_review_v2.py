"""Offline KL25 v2 source audit: source facts never imply executable L2."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_web.device_catalog import DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.nxp_kl25_qualification import (
    NxpKl25QualificationProvider,
    get_default_nxp_kl25_qualification_provider,
)
from plasma_web.programming_qualification import get_default_programming_qualification_registry

ROOT = Path(__file__).resolve().parents[3]
REL = "data/device-catalog/research/nxp-kl25-current-source-review-v2.json"


class Kl25CurrentSourceReviewV2Tests(unittest.TestCase):
    def test_source_audit_is_pinned_and_cannot_be_treated_as_l2(self) -> None:
        evidence = json.loads((ROOT / REL).read_text(encoding="utf-8"))
        self.assertEqual(evidence["provider"]["source_commit"],
                         "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c")
        self.assertEqual(evidence["provider"]["target_config"], "tcl/target/kl25.cfg")
        self.assertEqual(evidence["historical_non_authority"]["gate58_state"], "REJECTED_REVIEW")
        self.assertFalse(evidence["historical_non_authority"]["operation_admission_transferable"])
        self.assertEqual(evidence["result"]["programming_qualification_state"], "CANDIDATE")
        self.assertEqual(evidence["result"]["supported_exact_icpn_count_new"], 0)
        self.assertEqual(len(evidence["observations"]), 8)
        self.assertTrue(all(not allowed for allowed in evidence["gates"].values()))
        self.assertEqual(set(evidence["source_files"]), {
            "tcl/target/kl25.cfg",
            "tcl/target/klx.cfg",
            "tcl/target/swj-dp.tcl",
            "src/flash/nor/kinetis.c",
        })
        provider = get_default_nxp_kl25_qualification_provider()
        self.assertIsNotNone(provider)
        raw = provider.describe("NXP", "MKL25Z128VLK4")
        self.assertEqual(raw["software_state"], "CANDIDATE")
        self.assertIsNone(raw["programming"])
        self.assertTrue(all(v["state"] == "UNKNOWN" for v in raw["operations"].values()))
        level = get_default_programming_qualification_registry().describe(
            "NXP", "MKL25Z128VLK4")
        self.assertEqual(level["catalog_level"], 1)
        self.assertFalse(level["job_selectable"])
        self.assertFalse(level["execution_authorized"])
        self.assertFalse(level["installed_runtime_attested"])

    def test_evidence_blob_drift_is_rejected(self) -> None:
        from plasma_web import nxp_kl25_qualification as module
        with patch.object(module, "BLOBS", {
            **module.BLOBS, REL: "0" * 40,
        }):
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "Git blob mismatch"):
                NxpKl25QualificationProvider(get_default_device_catalog(), ROOT)

    def test_spoofed_runtime_or_qualification_cannot_promote(self) -> None:
        from plasma_web import nxp_kl25_qualification as module
        real = module._read_locked
        for edit in (
            lambda x: x["result"].update(
                programming_qualification_state="SUPPORTED",
                catalog_level=2, job_selectable=True),
            lambda x: x["gates"].update(swd_session_and_debug_id_pass=True),
            lambda x: x["protected_flash"].update(
                program_intersection_requires_rejection=False),
            lambda x: x["source_files"]["src/flash/nor/kinetis.c"].update(
                git_blob="0" * 40),
        ):
            def fake_read(root, rel):
                raw = real(root, rel)
                if rel == REL:
                    doc = json.loads(raw)
                    edit(doc)
                    return json.dumps(doc).encode("utf-8")
                return raw
            with self.subTest(edit=edit.__code__.co_firstlineno):
                with patch.object(module, "_read_locked", side_effect=fake_read):
                    with self.assertRaises(DeviceCatalogIntegrityError):
                        NxpKl25QualificationProvider(get_default_device_catalog(), ROOT)

    def test_source_review_fcf_boundary_policy_is_closed(self) -> None:
        doc = json.loads((ROOT / REL).read_text(encoding="utf-8"))
        guarded = doc["protected_flash"]
        legacy = json.loads((
            ROOT / "data/ic-support/benchmarks/nxp-kl25/backend-implementation-lock.json"
        ).read_text(encoding="utf-8"))
        constraints = legacy["admitted_constraints"]
        lower = guarded["sector_start"]
        upper = guarded["sector_end_exclusive"]
        self.assertEqual((lower, upper), (0x400, 0x800))
        self.assertEqual(
            (lower, upper),
            (int(constraints["flash_configuration_field_sector_start"], 0),
             int(constraints["flash_configuration_field_sector_start"], 0)
             + constraints["flash_configuration_field_sector_size_bytes"]),
        )
        self.assertEqual(guarded["erase_sector_bytes"], 1024)
        self.assertEqual(guarded["program_longword_bytes"], 4)
        self.assertTrue(guarded["program_intersection_requires_rejection"])
        self.assertTrue(guarded["erase_containing_sector_requires_rejection"])
        self.assertFalse(guarded["fcf_rewrite_qualified"])

        # This is evidence-range validation, not a substitute for the actual
        # KL25OpenOCDPlanCompiler regression tests run by full Python CI.
        overlaps = lambda start, size: start < upper and start + size > lower
        for offset, size in ((0x400, 4), (0x410, 4), (0x7fc, 4),
                             (0x3fc, 8), (0x3fc, 0x405), (0x0, 0x401),
                             (0x0, 0x800), (0x7fc, 8)):
            with self.subTest(offset=offset, size=size):
                self.assertTrue(overlaps(offset, size))
        for offset, size in ((0, 0x400), (0x3fc, 4), (0x800, 4),
                             (0x800, 0x1000)):
            with self.subTest(offset=offset, size=size):
                self.assertFalse(overlaps(offset, size))


if __name__ == "__main__":
    unittest.main()

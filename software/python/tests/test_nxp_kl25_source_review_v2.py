"""Offline KL25 v2 source audit: source facts never imply executable L2."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_core.errors import PlasmaError
from plasma_interfaces.kl25_openocd_plan import (
    KL25OpenOCDPlanCompiler, load_backend_lock,
)
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

    def test_program_fcf_sector_boundary_rejects_every_overlapping_region(self) -> None:
        doc = json.loads((ROOT / REL).read_text(encoding="utf-8"))
        guarded = doc["protected_flash"]
        lock = load_backend_lock()["admitted_constraints"]
        self.assertEqual((guarded["sector_start"], guarded["sector_end_exclusive"]),
                         (0x400, 0x800))
        self.assertEqual(guarded["erase_sector_bytes"], 1024)
        self.assertEqual(guarded["program_longword_bytes"], 4)
        for offset, size in ((0x400, 4), (0x410, 4), (0x7fc, 4),
                             (0x3fc, 8), (0x3fc, 0x405), (0x0, 0x401),
                             (0x0, 0x800), (0x7fc, 8)):
            with self.subTest(offset=offset, size=size):
                with self.assertRaisesRegex(PlasmaError, "Configuration Field sector"):
                    KL25OpenOCDPlanCompiler._reject_fcf_intersection(offset, size, lock)
        for offset, size in ((0, 0x400), (0x3fc, 4), (0x800, 4),
                             (0x800, 0x1000)):
            with self.subTest(allowed_offset=offset):
                KL25OpenOCDPlanCompiler._reject_fcf_intersection(offset, size, lock)


if __name__ == "__main__":
    unittest.main()

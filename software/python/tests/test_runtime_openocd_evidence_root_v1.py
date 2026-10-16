"""Installed-wheel regression for ST H5/C5 source-only display metadata.

Requires canonical full checkout in normal tests; tests never touch PPU/HIL.
Production exact ICPNs and software execution policy stay independent.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_web.device_catalog import DeviceCatalogIntegrityError
from plasma_web.gateway import _device_search_payload
from plasma_web.programming_qualification import get_default_programming_qualification_registry
from plasma_web.backend_candidate_registry import (
    ROOT as CANDIDATE_ROOT,
    get_default_backend_candidate_registry,
)
from plasma_web.backend_source_reference import (
    ROOT as SOURCE_ROOT,
    default_pinned_upstream,
)
from plasma_web.openocd_provider_registry import (
    ROOT as PROVIDER_ROOT,
    get_default_openocd_provider_registry,
)
from plasma_web.runtime_evidence_root import (
    RUNTIME_EVIDENCE_ROOT_ENV,
    default_runtime_evidence_root,
    source_files_available,
)

REPO = Path(__file__).resolve().parents[3]
EXPECTED_PROVIDERS = {
    "openocd-upstream": 4176,
    "openocd-st-h5-research": 190,
    "openocd-st-c5-stldr-research": 172,
}


class OpenOCDEvidenceRootTests(unittest.TestCase):
    def test_legacy_module_roots_are_same_canonical_checkout_not_venv(self) -> None:
        root = default_runtime_evidence_root()
        self.assertEqual(root, REPO)
        self.assertEqual((CANDIDATE_ROOT, SOURCE_ROOT, PROVIDER_ROOT), (REPO,) * 3)
        self.assertNotIn("site-packages", str(root))

    def test_all_source_only_providers_available_without_upgrading_backend(self) -> None:
        candidates = get_default_backend_candidate_registry()
        providers = get_default_openocd_provider_registry()
        upstream = default_pinned_upstream()
        self.assertEqual(candidates.size, 362)
        self.assertTrue(candidates.evidence_available)
        self.assertIsNotNone(providers)
        assert providers is not None
        self.assertEqual(providers.inventory, EXPECTED_PROVIDERS)
        self.assertIsNotNone(upstream)
        self.assertEqual(upstream["source_commit"], "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c")
        for exact, provider_id in (
            ("STM32H503CBT6", "openocd-st-h5-research"),
            ("STM32C531CBT6", "openocd-st-c5-stldr-research"),
        ):
            with self.subTest(part=exact):
                search = _device_search_payload(exact, limit=1)
                level_counts = get_default_programming_qualification_registry().summary["catalog_level_counts"]
                self.assertEqual(
                    search["catalog_size"],
                    sum(level_counts[str(level)] for level in (1, 2, 3)),
                )
                self.assertEqual(search["count"], 1)
                row = search["results"][0]
                self.assertEqual(row["icpn"], exact)
                self.assertEqual(row["backend"]["mapping_status"], "no_mapping")
                self.assertEqual(row["backend_candidate"]["provider_id"], provider_id)
                self.assertEqual(row["backend_source_reference"]["provider_id"], provider_id)
                self.assertEqual([p["provider_id"] for p in row["backend_providers"]], [provider_id])
                self.assertFalse(row["backend_candidate"]["production_binding_authorized"])
                self.assertFalse(row["backend_candidate"]["hardware_runtime_ready"])
                for provider in row["backend_providers"]:
                    self.assertFalse(provider["executable"])
                    self.assertFalse(provider["hardware_runtime_ready"])
                    self.assertFalse(provider["production_write_authorized"])
                    self.assertIsNone(provider["installed_binary_sha256"])
                self.assertEqual(row["physical_validation"]["socket_status"], "no_evidence")
        nxp = _device_search_payload("NXP", limit=1)
        self.assertEqual(nxp["levels"], [1, 2, 3])
        self.assertEqual(nxp["total_count"], 12)

    def test_explicit_empty_and_partially_missing_roots_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {RUNTIME_EVIDENCE_ROOT_ENV: str(root)}):
                self.assertEqual(default_runtime_evidence_root(), root)
                with self.assertRaisesRegex(DeviceCatalogIntegrityError, "incomplete OpenOCD"):
                    source_files_available(root, ("release/openocd.json",))
                release = root / "release/openocd.json"
                release.parent.mkdir()
                release.write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(DeviceCatalogIntegrityError, "incomplete OpenOCD"):
                    source_files_available(root, (
                        "release/openocd.json",
                        "data/device-catalog/research/st-h5-offline-flash-matrix-v1.json",
                    ))

    def test_relative_root_rejected_and_custom_manifest_requires_explicit_evidence_root(self) -> None:
        with patch.dict(os.environ, {RUNTIME_EVIDENCE_ROOT_ENV: "./research"}, clear=False):
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "absolute path"):
                default_runtime_evidence_root()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"PLASMA_DEVICE_CATALOG_MANIFEST": str(Path(tmp) / "catalog.json")},
        ):
            with patch.dict(os.environ, {RUNTIME_EVIDENCE_ROOT_ENV: ""}):
                self.assertIsNone(default_runtime_evidence_root())
                self.assertFalse(source_files_available(None, ("release/openocd.json",)))

    def test_legitimate_slim_bundle_has_no_fake_research_information(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {RUNTIME_EVIDENCE_ROOT_ENV: ""}):
                self.assertFalse(source_files_available(root, (
                    "release/openocd.json",
                    "data/device-catalog/research/st-h5-c5-runtime-gap-v1.json",
                )))
            f = root / "release/openocd.json"
            f.parent.mkdir()
            f.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {RUNTIME_EVIDENCE_ROOT_ENV: ""}):
                with self.assertRaisesRegex(DeviceCatalogIntegrityError, "incomplete OpenOCD"):
                    source_files_available(root, (
                        "release/openocd.json",
                        "data/device-catalog/research/st-h5-c5-runtime-gap-v1.json",
                    ))

    def test_render_start_declares_and_checks_full_metadata_before_public_start(self) -> None:
        script = (REPO / "scripts/render-start.sh").read_text(encoding="utf-8")
        self.assertIn('export PLASMA_RUNTIME_EVIDENCE_ROOT="${runtime_evidence_root}"', script)
        self.assertIn("get_default_backend_candidate_registry().size != 362", script)
        self.assertIn("get_default_openocd_provider_registry()", script)
        self.assertIn("STM32H503CBT6", script)
        self.assertIn("STM32C531CBT6", script)
        self.assertIn('if nxp_search.get("total_count", 0) < 1', script)


if __name__ == "__main__":
    unittest.main()

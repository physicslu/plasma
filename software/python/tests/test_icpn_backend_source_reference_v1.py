"""IC Selector backend provider metadata is source-only, never runtime attestation."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_web.backend_candidate_registry import BackendCandidateRegistry
from plasma_web.backend_source_reference import (
    backend_source_reference, load_pinned_upstream,
)
from plasma_web.device_catalog import DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.gateway import _device_search_payload


class BackendSourceReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.candidates = BackendCandidateRegistry(cls.catalog)
        cls.upstream = load_pinned_upstream()

    def row(self, icpn):
        result = self.catalog.resolve("STMicroelectronics", icpn)
        self.assertIsNotNone(result)
        return result

    def test_mapped_upstream_uses_repo_release_and_no_installed_claim(self):
        row = self.row("STM32F103C8T6")
        r = backend_source_reference(row, self.candidates.lookup(row), self.upstream)
        self.assertEqual(r["provider_id"], "openocd-upstream")
        self.assertEqual(r["mapping_status"], "mapped")
        self.assertEqual(r["source_version"], "0.12.0")
        self.assertEqual(r["source_commit"], "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c")
        self.assertEqual(r["pinned_release_runtime_id"], "0.12.0-9ea7f3d647c8")
        self.assertEqual(r["evidence_scope"], "catalog_mapping_only")
        self.assertIsNone(r["installed_runtime_id"])
        self.assertIsNone(r["installed_binary_sha256"])
        self.assertIsNone(r["flash_driver"])
        self.assertFalse(r["hardware_runtime_ready"])

    def test_st_h5_c5_are_source_candidates_not_installed_runtimes(self):
        for part, driver in (("STM32H503CBT6", "stm32h5x"),
                             ("STM32C531CBT6", "stldr")):
            row = self.row(part)
            r = backend_source_reference(row, self.candidates.lookup(row), self.upstream)
            self.assertEqual(r["provider_name"], "ST OpenOCD")
            self.assertEqual(r["mapping_status"], "candidate")
            self.assertEqual(r["flash_driver"], driver)
            self.assertEqual(r["source_commit"], "c8d973bdad9a6fddb51459eda109b3b95d23b57a")
            self.assertEqual(r["evidence_scope"], "source_pinned_research_only")
            self.assertIsNone(r["source_version"])
            self.assertIsNone(r["pinned_release_runtime_id"])
            self.assertIsNone(r["installed_runtime_id"])
            self.assertIsNone(r["installed_binary_sha256"])
            self.assertFalse(r["physical_programming_qualified"])

    def test_unmapped_families_without_candidate_are_not_invented(self):
        for part in ("STM32N657X0Q3", "STM32WB05KZV6", "STM32WL3"):
            row = self.catalog.resolve("STMicroelectronics", part)
            if row is not None and row.mapping_status == "no_mapping":
                self.assertIsNone(backend_source_reference(row, None, self.upstream))

    def test_slim_ppu_missing_optional_release_does_not_invent_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_pinned_upstream(Path(tmp)))
        row = self.row("STM32F103C8T6")
        r = backend_source_reference(row, None, None)
        self.assertEqual(r["provider_name"], "Upstream OpenOCD")
        self.assertIsNone(r["source_version"])
        self.assertIsNone(r["source_commit"])
        self.assertIsNone(r["installed_binary_sha256"])

    def test_corrupted_upstream_version_or_runtime_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp)/"release"/"openocd.json"
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps({
                "schema_version": 1, "engine": "openocd",
                "source_repository": "https://github.com/openocd-org/openocd.git",
                "source_commit": "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c",
                "version": "0.12.0", "runtime_id": "malicious-version",
                "hardware_runtime_ready": False,
            }), encoding="utf-8")
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "inconsistent"):
                load_pinned_upstream(Path(tmp))

    def test_inconsistent_st_candidate_permission_rejected(self):
        row = self.row("STM32H503CBT6")
        c = dict(self.candidates.lookup(row))
        c["executable"] = True
        with self.assertRaisesRegex(DeviceCatalogIntegrityError, "safely bounded"):
            backend_source_reference(row, c, self.upstream)

    def test_gateway_exposes_source_reference_without_authorizing_runtime(self):
        with (patch("plasma_web.gateway.get_default_device_catalog", return_value=self.catalog),
              patch("plasma_web.gateway.get_default_backend_candidate_registry", return_value=self.candidates),
              patch("plasma_web.gateway.default_pinned_upstream", return_value=self.upstream)):
            for icpn, provider in (("STM32F103C8T6", "openocd-upstream"),
                                   ("STM32H503CBT6", "openocd-st-h5-research"),
                                   ("STM32C531CBT6", "openocd-st-c5-stldr-research")):
                response = _device_search_payload(icpn, 1)
                record = response["results"][0]
                self.assertEqual(record["icpn"], icpn)
                self.assertEqual(record["backend_source_reference"]["provider_id"], provider)
                self.assertIsNone(record["backend_source_reference"]["installed_binary_sha256"])
                self.assertEqual(record["physical_validation"]["ppu_status"], "no_evidence")
                self.assertEqual(record["physical_validation"]["socket_status"], "no_evidence")


if __name__ == "__main__":
    unittest.main()

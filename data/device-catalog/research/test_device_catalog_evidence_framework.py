#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_evidence_framework import (  # noqa: E402
    EvidenceFrameworkError,
    build_manifest,
    validate_core_provenance,
    validate_manifest,
)


class EvidenceFrameworkTests(unittest.TestCase):
    def _package(self, root: Path, *, transport: str = "official_json") -> tuple[Path, set[str]]:
        evidence = root / "evidence"
        evidence.mkdir()
        (evidence / "payload.json").write_text('{"parts":["EXM32A1T6"]}\n', encoding="utf-8")
        provenance = {
            "schema_version": 1,
            "manufacturer": "ExampleSemiconductor",
            "source_repository": "physicslu/plasma",
            "executed_git_sha": "a" * 40,
            "evidence_id": "example-family-batch-1",
            "acquisition_transport": transport,
            "headed": False,
            "target_count": 1,
            "acquisition_success": 1,
            "acquisition_failure": 0,
            "exact_icpn_candidate_count": 1,
            "evaluator_result": "scale_ready",
            "scale_ready": True,
            "canonical_dataset_admission": False,
        }
        (evidence / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (evidence / "README.md").write_text("synthetic evidence fixture\n", encoding="utf-8")
        files = {"payload.json", "provenance.json", "README.md"}
        manifest = build_manifest(evidence, evidence_id=provenance["evidence_id"], retained_files=files)
        (evidence / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return evidence, files

    def test_vendor_and_transport_are_not_hardcoded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence, files = self._package(Path(temp), transport="official_json")
            manifest = validate_manifest(evidence, expected_files=files)
            provenance = json.loads((evidence / "provenance.json").read_text(encoding="utf-8"))
            report = validate_core_provenance(provenance, evidence_id=manifest["evidence_id"])
            self.assertEqual(report["manufacturer"], "ExampleSemiconductor")
            self.assertEqual(report["acquisition_transport"], "official_json")
            self.assertFalse(report["headed"])

    def test_raw_http_transport_is_also_opaque_to_framework(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence, files = self._package(Path(temp), transport="raw_http")
            manifest = validate_manifest(evidence, expected_files=files)
            provenance = json.loads((evidence / "provenance.json").read_text(encoding="utf-8"))
            report = validate_core_provenance(provenance, evidence_id=manifest["evidence_id"])
            self.assertEqual(report["acquisition_transport"], "raw_http")

    def test_digest_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence, files = self._package(Path(temp))
            with (evidence / "README.md").open("a", encoding="utf-8") as handle:
                handle.write("tamper\n")
            with self.assertRaisesRegex(EvidenceFrameworkError, "digest mismatch"):
                validate_manifest(evidence, expected_files=files)

    def test_unexpected_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence, files = self._package(Path(temp))
            (evidence / "extra.txt").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaisesRegex(EvidenceFrameworkError, "file set is not exact"):
                validate_manifest(evidence, expected_files=files)

    def test_acquisition_accounting_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence, files = self._package(Path(temp))
            manifest = validate_manifest(evidence, expected_files=files)
            provenance = json.loads((evidence / "provenance.json").read_text(encoding="utf-8"))
            provenance["acquisition_failure"] = 1
            with self.assertRaisesRegex(EvidenceFrameworkError, "accounting mismatch"):
                validate_core_provenance(provenance, evidence_id=manifest["evidence_id"])

    def test_retained_evidence_cannot_claim_canonical_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence, files = self._package(Path(temp))
            manifest = validate_manifest(evidence, expected_files=files)
            provenance = json.loads((evidence / "provenance.json").read_text(encoding="utf-8"))
            provenance["canonical_dataset_admission"] = True
            with self.assertRaisesRegex(EvidenceFrameworkError, "canonical_dataset_admission mismatch"):
                validate_core_provenance(provenance, evidence_id=manifest["evidence_id"])


if __name__ == "__main__":
    unittest.main()

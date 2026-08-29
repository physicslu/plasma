#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from validate_stm32f1_retained_evidence import (  # noqa: E402
    DEFAULT_EVIDENCE_DIR,
    RetainedEvidenceError,
    validate_retained_evidence,
)


class RetainedEvidenceTests(unittest.TestCase):
    def test_checked_in_package_passes(self) -> None:
        report = validate_retained_evidence(DEFAULT_EVIDENCE_DIR)
        self.assertEqual(report["targets"], 6)
        self.assertEqual(report["exact_icpn_candidates"], 26)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["candidate_drift"], 0)
        self.assertTrue(report["scale_ready"])
        self.assertFalse(report["canonical_dataset_admission"])

    def _copy_package(self, root: Path) -> Path:
        destination = root / "evidence"
        destination.mkdir()
        for source in DEFAULT_EVIDENCE_DIR.iterdir():
            (destination / source.name).write_bytes(source.read_bytes())
        return destination

    def _rewrite_manifest_digest(self, evidence_dir: Path, name: str) -> None:
        manifest_path = evidence_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256((evidence_dir / name).read_bytes()).hexdigest()
        for item in manifest["files"]:
            if item["path"] == name:
                item["sha256"] = digest
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_file_tampering_fails_digest_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence_dir = self._copy_package(Path(temp))
            with (evidence_dir / "README.md").open("a", encoding="utf-8") as stream:
                stream.write("tampered\n")
            with self.assertRaisesRegex(RetainedEvidenceError, "digest mismatch"):
                validate_retained_evidence(evidence_dir)

    def test_missing_retained_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence_dir = self._copy_package(Path(temp))
            (evidence_dir / "control-summary.json").unlink()
            with self.assertRaisesRegex(RetainedEvidenceError, "file set is not exact"):
                validate_retained_evidence(evidence_dir)

    def test_candidate_drift_fails_even_when_manifest_is_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence_dir = self._copy_package(Path(temp))
            summary_path = evidence_dir / "pilot-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["results"][0]["evidence"]["exact_icpns"][-1] = "STM32F100C8X6"
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rewrite_manifest_digest(evidence_dir, "pilot-summary.json")
            with self.assertRaisesRegex(RetainedEvidenceError, "deterministic reevaluation"):
                validate_retained_evidence(evidence_dir)

    def test_browser_raw_sha_claim_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence_dir = self._copy_package(Path(temp))
            summary_path = evidence_dir / "pilot-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["results"][0]["evidence"]["raw_sha256"] = "a" * 64
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rewrite_manifest_digest(evidence_dir, "pilot-summary.json")
            with self.assertRaisesRegex(RetainedEvidenceError, "must not contain raw_sha256"):
                validate_retained_evidence(evidence_dir)

    def test_wrong_executed_git_sha_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence_dir = self._copy_package(Path(temp))
            provenance_path = evidence_dir / "provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["executed_git_sha"] = "f" * 40
            provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rewrite_manifest_digest(evidence_dir, "provenance.json")
            with self.assertRaisesRegex(RetainedEvidenceError, "Git SHA mismatch"):
                validate_retained_evidence(evidence_dir)

    def test_canonical_admission_claim_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            evidence_dir = self._copy_package(Path(temp))
            provenance_path = evidence_dir / "provenance.json"
            provenance = copy.deepcopy(json.loads(provenance_path.read_text(encoding="utf-8")))
            provenance["canonical_dataset_admission"] = True
            provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rewrite_manifest_digest(evidence_dir, "provenance.json")
            with self.assertRaisesRegex(RetainedEvidenceError, "canonical_dataset_admission mismatch"):
                validate_retained_evidence(evidence_dir)


if __name__ == "__main__":
    unittest.main()

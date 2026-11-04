"""Offline contract tests for trusted source-pinned Z2 kit delivery."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "plasma_path2_trusted_z2_artifact",
    ROOT / "scripts/plasma_path2_trusted_z2_artifact.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
WORKFLOW = ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml"


class TrustedKitTests(unittest.TestCase):
    def good_run(self):
        return {
            "id": mod.RUN_ID, "head_sha": mod.RUN_HEAD_SHA, "status": "completed",
            "conclusion": "success", "event": "pull_request",
            "repository": {"full_name": mod.REPOSITORY},
            "pull_requests": [{"number": mod.SOURCE_PR}],
        }

    def good_listing(self):
        return {"artifacts": [{
            "id": mod.ARTIFACT_ID, "name": mod.ARTIFACT_NAME, "expired": False,
            "digest": "sha256:" + mod.ARTIFACT_ZIP_SHA256, "size_in_bytes": 1000,
            "workflow_run": {"id": mod.RUN_ID, "head_sha": mod.RUN_HEAD_SHA},
        }]}

    def test_exact_metadata_accepts_one_verified_artifact(self):
        receipt = mod.verify_metadata(self.good_run(), self.good_listing())
        self.assertEqual(receipt["result"], "TRUSTED_ARTIFACT_METADATA_PASS")
        self.assertEqual(receipt["producer_head_sha"], mod.RUN_HEAD_SHA)
        self.assertTrue(receipt["no_install"])

    def test_metadata_rejects_wrong_source_run_artifact_digest_and_expiry(self):
        for key, value in [
            ("head_sha", "f" * 40), ("conclusion", "failure"),
            ("event", "workflow_dispatch")]:
            run = self.good_run()
            run[key] = value
            with self.assertRaises(mod.AdmissionError):
                mod.verify_metadata(run, self.good_listing())
        for key, value in [
            ("id", 1), ("digest", "sha256:" + "0" * 64), ("expired", True),
            ("name", "other")]:
            listing = self.good_listing()
            listing["artifacts"][0][key] = value
            with self.assertRaises(mod.AdmissionError):
                mod.verify_metadata(self.good_run(), listing)
        listing = self.good_listing()
        listing["artifacts"][0]["workflow_run"]["head_sha"] = "a" * 40
        with self.assertRaises(mod.AdmissionError):
            mod.verify_metadata(self.good_run(), listing)

    def test_archive_requires_exact_bytes_sidecar_and_regular_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / (mod.ARTIFACT_NAME + ".tar.gz")
            sidecar = root / (archive.name + ".sha256")
            archive.write_bytes(b"verified test kit")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            sidecar.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
            with patch.object(mod, "KIT_SHA256", digest):
                self.assertEqual(
                    mod.verify_archive(root)["result"], "TRUSTED_ARTIFACT_BYTES_PASS")
                archive.write_bytes(b"modified")
                with self.assertRaisesRegex(mod.AdmissionError, "KIT_SHA256_MISMATCH"):
                    mod.verify_archive(root)
                archive.write_bytes(b"verified test kit")
                sidecar.write_text("bad", encoding="ascii")
                with self.assertRaisesRegex(mod.AdmissionError, "KIT_SIDECAR_MISMATCH"):
                    mod.verify_archive(root)
            (root / "link").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(mod.AdmissionError, "TRUSTED_ARTIFACT_DIR_INVALID"):
                mod.verify_archive(root / "link")

    def test_workflow_uses_credential_only_in_trusted_steps_and_pins_scope(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Qualify pinned Z2 Runtime Kit metadata (trusted)", content)
        self.assertIn("name: Download pinned Z2 Runtime Kit (trusted)", content)
        self.assertIn("name: Verify pinned Z2 Runtime Kit bytes (trusted)", content)
        self.assertIn("plasma_path2_trusted_z2_artifact.py verify-metadata", content)
        self.assertIn("plasma_path2_trusted_z2_artifact.py verify-archive", content)
        self.assertIn("github-token: ${{ github.token }}", content)
        self.assertIn("needs.development-authorize.outputs.pr_number == '1299'", content)
        self.assertIn("needs.development-authorize.outputs.pinned_sha == '9a6831c8cd863fa89ea4819d7c7cfc53b07b382d'", content)
        self.assertIn("PLASMA_Z2_KIT_ARTIFACT_DIR:", content)
        step = content.split("- name: Execute candidate CLI using trusted dispatcher", 1)[1].split("        run: |", 1)[0]
        self.assertNotIn("GH_TOKEN:", step)
        self.assertNotIn("GITHUB_TOKEN:", step)
        self.assertNotIn("secrets.", step)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Host-only adversarial tests for trusted CI artifact handoff."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "plasma_trusted_z2_ci_artifact", ROOT / "scripts/plasma_trusted_z2_ci_artifact.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

SOURCE = "e949d1bcbf0941eb034c76e842bd90cc943152dc"
RUN_ID = 42064496761
ARTIFACT_NAME = "plasma-z2-ps-kit-0.2.1-e949d1bcbf09"


def fixtures():
    run = {
        "id": RUN_ID, "status": "completed", "conclusion": "success",
        "event": "push", "head_branch": "main", "head_sha": SOURCE,
        "path": ".github/workflows/z2-ps-release.yml",
        "repository": {"full_name": "physicslu/plasma", "id": 1007530655},
        "head_repository": {"full_name": "physicslu/plasma"},
    }
    artifact = {
        "id": 13433061529, "name": ARTIFACT_NAME, "expired": False,
        "size_in_bytes": 118163764,
        "digest": "sha256:" + "a" * 64,
        "workflow_run": {
            "id": RUN_ID, "head_sha": SOURCE, "head_branch": "main",
            "repository_id": 1007530655,
        },
    }
    return run, {"total_count": 1, "artifacts": [artifact]}


class MetadataTests(unittest.TestCase):
    def test_admit_source_pinned_successful_main_run(self):
        run, listing = fixtures()
        record = mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)
        self.assertEqual(record["artifact_id"], 13433061529)
        self.assertEqual(record["source_sha"], SOURCE)
        self.assertEqual(record["zip_sha256"], "a" * 64)

    def test_fail_closed_for_untrusted_metadata(self):
        for key, value in (
            ("conclusion", "failure"), ("status", "in_progress"),
            ("event", "pull_request"), ("head_branch", "agent/branch"),
            ("head_sha", "0" * 40), ("path", ".github/workflows/other.yml"),
            ("id", RUN_ID + 1),
        ):
            run, listing = fixtures()
            run[key] = value
            with self.subTest(field=key), self.assertRaises(mod.ArtifactDenied):
                mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)
        for key, value in (
            ("expired", True), ("digest", "sha256:" + "0" * 63),
            ("size_in_bytes", 0), ("name", "arbitrary.zip"),
            ("id", 0),
        ):
            run, listing = fixtures()
            listing["artifacts"][0][key] = value
            with self.subTest(field=key), self.assertRaises(mod.ArtifactDenied):
                mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)
        for key, value in (
            ("head_sha", "0" * 40), ("repository_id", 1),
            ("id", RUN_ID + 1), ("head_branch", "feature"),
        ):
            run, listing = fixtures()
            listing["artifacts"][0]["workflow_run"][key] = value
            with self.subTest(producer=key), self.assertRaises(mod.ArtifactDenied):
                mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)

    def test_missing_ambiguous_or_paginated_artifacts(self):
        run, listing = fixtures()
        listing["artifacts"].append(dict(listing["artifacts"][0]))
        listing["total_count"] = 2
        with self.assertRaisesRegex(mod.ArtifactDenied, "KIT_ARTIFACT_NOT_UNIQUE"):
            mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)
        listing["artifacts"].pop()
        with self.assertRaisesRegex(mod.ArtifactDenied, "ARTIFACT_LIST_INCOMPLETE"):
            mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)

    def test_bad_source_and_run_type(self):
        run, listing = fixtures()
        for source, run_id in ((SOURCE[:12], RUN_ID), (SOURCE, True), (SOURCE, 0)):
            with self.subTest(source=source, run_id=run_id), self.assertRaises(mod.ArtifactDenied):
                mod.admit(run, listing, source_sha=source, run_id=run_id)


class PayloadTests(unittest.TestCase):
    @staticmethod
    def create_zip(path: Path, *, content: bytes = b"test kit payload",
                   sidecar: bytes | None = None, extra: bool = False,
                   symlink: bool = False):
        name = ARTIFACT_NAME + ".tar.gz"
        if sidecar is None:
            sidecar = f"{hashlib.sha256(content).hexdigest()}  {name}\n".encode()
        with zipfile.ZipFile(path, "w") as archive:
            if symlink:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, content)
            else:
                archive.writestr(name, content)
            archive.writestr(name + ".sha256", sidecar)
            if extra:
                archive.writestr("../outside", b"unsafe")

    @staticmethod
    def admission(path: Path):
        run, listing = fixtures()
        listing["artifacts"][0]["digest"] = "sha256:" + mod.sha256(path)
        return mod.admit(run, listing, source_sha=SOURCE, run_id=RUN_ID)

    def test_verified_zip_only_passes_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            zip_path = base / "artifact.zip"
            self.create_zip(zip_path)
            admission = self.admission(zip_path)
            with mock.patch.object(mod, "verify_kit_source") as check:
                record = mod.verify_download(zip_path, admission, base / "verified",
                                             helper=base / "fake.py")
            check.assert_called_once()
            self.assertEqual(record["status"], "TRUSTED_CI_ARTIFACT_VERIFIED")
            self.assertEqual(record["kit_sha256"], hashlib.sha256(b"test kit payload").hexdigest())
            self.assertTrue(Path(record["kit_path"]).is_file())
            self.assertTrue(Path(record["sidecar_path"]).is_file())

    def test_tampered_zip_fails_even_if_sidecar_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base / "artifact.zip"
            self.create_zip(path)
            admission = self.admission(path)
            self.create_zip(path, content=b"modified")
            with self.assertRaisesRegex(mod.ArtifactDenied, "ARTIFACT_ZIP_SHA256_MISMATCH"):
                mod.verify_download(path, admission, base / "verified",
                                    helper=base / "fake.py")
            self.assertFalse((base / "verified").exists())

    def test_missing_sidecar_extra_path_symlink_and_wrong_digest_fail(self):
        for variation in ("bad-sidecar", "extra-path", "symlink", "missing-sidecar"):
            with self.subTest(variation=variation), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                zip_path = base / "artifact.zip"
                if variation == "missing-sidecar":
                    with zipfile.ZipFile(zip_path, "w") as archive:
                        archive.writestr(ARTIFACT_NAME + ".tar.gz", b"test")
                else:
                    self.create_zip(
                        zip_path,
                        sidecar=b"0" * 64 + b"  wrong.tar.gz\n"
                        if variation == "bad-sidecar" else None,
                        extra=variation == "extra-path",
                        symlink=variation == "symlink")
                admission = self.admission(zip_path)
                with self.assertRaises(mod.ArtifactDenied):
                    mod.verify_download(zip_path, admission, base / "verified",
                                        helper=base / "fake.py")

    def test_forged_admission_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            zip_path = base / "artifact.zip"
            self.create_zip(zip_path)
            receipt = self.admission(zip_path)
            receipt["artifact_name"] = "arbitrary"
            with self.assertRaisesRegex(mod.ArtifactDenied, "ARTIFACT_ADMISSION_INVALID"):
                mod.verify_download(zip_path, receipt, base / "verified",
                                    helper=base / "fake.py")


    def test_nested_ppu_manifest_binds_full_source_sha_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            fake_helper = base / "fake-kit-verifier.py"
            release = base / "ppu.tar.gz"
            fake_helper.write_text(
                "from pathlib import Path\n"
                "from types import SimpleNamespace\n"
                "def verify_kit(artifact, *, sidecar, extract_to):\n"
                f"    return SimpleNamespace(root=Path({ARTIFACT_NAME!r}), "
                f"ppu_artifact=Path({str(release)!r}))\n",
                encoding="utf-8")
            for variant in ("pass", "wrong-source", "wrong-version", "wrong-target"):
                manifest = {
                    "git_sha": SOURCE, "role": "ppu",
                    "target": "linux-armv7l", "product_version": "0.2.1",
                }
                if variant == "wrong-source":
                    manifest["git_sha"] = "0" * 40
                elif variant == "wrong-version":
                    manifest["product_version"] = "0.9.9"
                elif variant == "wrong-target":
                    manifest["target"] = "linux-x86_64"
                payload = json.dumps(manifest).encode()
                with tarfile.open(release, "w:gz") as archive:
                    info = tarfile.TarInfo("plasma-release/release.json")
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
                kwargs = dict(
                    artifact=base / "fake-kit.tar.gz",
                    sidecar=base / "fake-kit.tar.gz.sha256",
                    source_sha=SOURCE,
                    artifact_name=ARTIFACT_NAME,
                    helper=fake_helper,
                )
                if variant == "pass":
                    mod.verify_kit_source(**kwargs)
                else:
                    with self.subTest(variant=variant), self.assertRaises(mod.ArtifactDenied):
                        mod.verify_kit_source(**kwargs)


    def test_path2_shares_main_only_ci_kit_verification_without_cli_secrets(self):
        workflow = (ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml").read_text()
        self.assertIn("Admit owner-pinned Z2 Runtime CI Kit (trusted Path 2)", workflow)
        self.assertIn("Verify owner-pinned Z2 Runtime CI Kit (trusted Path 2)", workflow)
        self.assertIn("trusted/scripts/plasma_trusted_z2_ci_artifact.py admit", workflow)
        self.assertIn("trusted/scripts/plasma_trusted_z2_ci_artifact.py verify", workflow)
        self.assertIn("outputs.pr_number == '0'", workflow)
        self.assertIn('PLASMA_Z2_KIT_SOURCE_SHA=$ARTIFACT_SOURCE_SHA', workflow)
        self.assertNotIn("outputs.pr_number == '1299'", workflow)
        stage = workflow.split(
            "- name: Execute candidate CLI using trusted dispatcher", 1)[1].split(
            "        run: |", 1)[0]
        self.assertNotIn("GH_TOKEN:", stage)
        self.assertNotIn("GITHUB_TOKEN:", stage)
        self.assertNotIn("secrets.", stage)


if __name__ == "__main__":
    unittest.main()

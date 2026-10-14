"""Operator-controlled filesystem evidence handoff — SYNTHETIC fixtures only.

All tests mocking original manufacturer semantics are unit tests for filesystem
transfer/custody. The workflow also runs a separate live original-source probe.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import microchip_phase1_local_vault_v1 as vault


def synthetic_portable_receipt(source):
    raw = Path(source).read_bytes()
    return {
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "source_file_count": 18,
        "offline_bundle_verification": "PASS",
        "source_originals_sha256_replayed": True,
        "original_mcp_dual_pagination_replayed": True,
        "durable_storage_verified": False,
        "independent_offsite_copy_verified": False,
        "production_write_authorized": False,
    }


class LocalFilesystemVaultTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.top = Path(temp.name)
        self.root = self.top / "operator-selected-vault"
        self.root.mkdir(mode=0o700)
        self.bundle = self.top / "original-evidence.zip"
        self.bundle.write_bytes(b"SYNTHETIC-NOT-MICROCHIP-ORIGINAL-EVIDENCE")
        self.key = "microchip-p0-20261014-r1"

    def test_local_copy_store_audit_and_independent_restore_no_offsite_claim(self):
        with patch.object(vault.portable, "verify",
                          side_effect=synthetic_portable_receipt) as checked:
            dep = vault.deposit(self.bundle, self.root, self.key)
            audited = vault.audit(self.root, self.key)
            restored_path = self.top / "restored-evidence.zip"
            rest = vault.restore(self.root, self.key, restored_path)
        self.assertEqual(dep, audited)
        self.assertEqual(dep["stored_bundle_sha256"],
                         hashlib.sha256(self.bundle.read_bytes()).hexdigest())
        self.assertEqual(restored_path.read_bytes(), self.bundle.read_bytes())
        self.assertEqual(rest["restore_result"], "PASS")
        self.assertEqual(rest["restore_sha256"], dep["stored_bundle_sha256"])
        self.assertTrue(rest["independent_restored_copy_cold_replayed"])
        for result in (dep, rest):
            self.assertFalse(result["durable_storage_verified"])
            self.assertFalse(result["independent_offsite_copy_verified"])
            self.assertFalse(result["immutable_object_lock_verified"])
            self.assertFalse(result["retention_policy_enforced"])
            self.assertFalse(result["production_write_authorized"])
        self.assertGreaterEqual(checked.call_count, 6)

    def test_second_deposit_and_restore_overwrite_forbidden(self):
        with patch.object(vault.portable, "verify",
                          side_effect=synthetic_portable_receipt):
            vault.deposit(self.bundle, self.root, self.key)
            with self.assertRaisesRegex(ValueError, "already exists"):
                vault.deposit(self.bundle, self.root, self.key)
            out = self.top / "output.zip"
            out.write_bytes(b"existing")
            with self.assertRaisesRegex(ValueError, "already exists"):
                vault.restore(self.root, self.key, out)
            self.assertEqual(out.read_bytes(), b"existing")

    def test_corrupt_stored_archive_rejected_by_receipt_verification(self):
        with patch.object(vault.portable, "verify",
                          side_effect=synthetic_portable_receipt):
            vault.deposit(self.bundle, self.root, self.key)
            target = self.root / self.key / "original-evidence.zip"
            target.write_bytes(b"CHANGED")
            with self.assertRaisesRegex(ValueError, "receipt/verified"):
                vault.audit(self.root, self.key)

    def test_corrupt_deposit_receipt_and_extra_files_rejected(self):
        with patch.object(vault.portable, "verify",
                          side_effect=synthetic_portable_receipt):
            vault.deposit(self.bundle, self.root, self.key)
            manifest = self.root / self.key / "local-deposit-receipt.json"
            value = json.loads(manifest.read_text())
            value["durable_storage_verified"] = True
            manifest.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "receipt/verified"):
                vault.audit(self.root, self.key)
            value["durable_storage_verified"] = False
            manifest.write_text(json.dumps(value))
            (self.root / self.key / "unknown.txt").write_text("unapproved")
            with self.assertRaisesRegex(ValueError, "unexpected files"):
                vault.audit(self.root, self.key)

    def test_key_slash_traversal_symlink_and_world_writable_root_rejected(self):
        for bad in ("../x", "/x", "abc/xyz", ".", "a"*65, "MixedCase",
                    ".hidden", "abc space"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "invalid evidence key"):
                vault.vault_dir(self.root, bad)
        redirect = self.top / "redirect"
        redirect.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "vault root"):
            vault.vault_dir(redirect, self.key)
        (self.root / "link").symlink_to(self.top, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked evidence key"):
            vault.vault_dir(self.root, "link", present=True)
        os.chmod(self.root, stat.S_IRWXU | stat.S_IWOTH)
        with self.assertRaisesRegex(ValueError, "world writable"):
            vault.vault_dir(self.root, self.key)

    def test_missing_or_invalid_source_cannot_deposit(self):
        bogus = self.top / "bogus.zip"
        bogus.write_bytes(b"NOT A ZIP")
        with self.assertRaises(Exception):
            vault.deposit(bogus, self.root, "bad-evidence")
        self.assertFalse((self.root / "bad-evidence").exists())
        with self.assertRaisesRegex(ValueError, "regular non-symlink"):
            vault.deposit(self.top / "missing.zip", self.root, "missing")
        link = self.top / "symlink.zip"
        link.symlink_to(self.bundle)
        with self.assertRaisesRegex(ValueError, "regular non-symlink"):
            vault.deposit(link, self.root, "link")

    def test_incomplete_deposit_does_not_publish_success_receipt(self):
        def fail_second_verify(path):
            if str(path).startswith(str(self.root)):
                raise ValueError("synthetic cold replay failed")
            return synthetic_portable_receipt(path)
        with patch.object(vault.portable, "verify", side_effect=fail_second_verify):
            with self.assertRaisesRegex(ValueError, "cold replay failed"):
                vault.deposit(self.bundle, self.root, self.key)
        self.assertFalse((self.root / self.key / "local-deposit-receipt.json").exists())
        with patch.object(vault.portable, "verify",
                          side_effect=synthetic_portable_receipt):
            with self.assertRaisesRegex(ValueError, "regular non-symlink"):
                vault.audit(self.root, self.key)

    def test_no_external_credential_or_destination_automatically_assumed(self):
        with self.assertRaisesRegex(ValueError, "vault root missing"):
            vault.vault_root(self.top / "not-created")
        self.assertIsNone(os.environ.get("MICROCHIP_VAULT_SECRET_FOR_UNIT_TEST"))


if __name__ == "__main__":
    unittest.main()

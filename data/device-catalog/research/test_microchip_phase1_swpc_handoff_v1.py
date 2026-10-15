"""Synthetic-only fail-closed tests for manual SWPC original-source handoff."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[3] / "scripts" / \
    "microchip-phase1-swpc-vault-handoff-v1.py"
spec = importlib.util.spec_from_file_location("swpc_vault_handoff", MODULE)
swpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swpc)


def fake_receipt(archive):
    raw = Path(archive).read_bytes()
    return {
        "schema_version": 1,
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "source_file_count": 18,
        "offline_bundle_verification": "PASS",
        "source_originals_sha256_replayed": True,
        "original_mcp_dual_pagination_replayed": True,
        "source_to_phase1_chart_report_replayed": True,
        "durable_storage_verified": False,
        "independent_offsite_copy_verified": False,
        "production_write_authorized": False,
    }


class SWPCHandoffTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.artifacts = self.root / "downloaded-original"
        self.vault = self.root / "operator-owned-vault"
        self.restore_dir = self.root / "restore"
        for d in (self.artifacts, self.vault, self.restore_dir):
            d.mkdir(mode=0o700)
        self.zipfile = self.artifacts / swpc.ARCHIVE
        self.zipfile.write_bytes(b"SYNTHETIC-ONLY-MOCK-NOT-ACTUAL-MICROCHIP-EVIDENCE")
        self.sha = hashlib.sha256(self.zipfile.read_bytes()).hexdigest()
        (self.artifacts / swpc.PIN).write_text(
            f"{self.sha}  {swpc.ARCHIVE}\n", encoding="utf-8")
        receipt = json.dumps(fake_receipt(self.zipfile), indent=2)
        for n in (swpc.PACK_RECEIPT, swpc.COLD_RECEIPT):
            (self.artifacts / n).write_text(receipt, encoding="utf-8")
        self.key = "microchip-p0-20261014-swpc-manual"

    def run_preflight(self, expected=None):
        return swpc.preflight(self.artifacts, self.vault, self.restore_dir,
                              self.key, self.sha if expected is None else expected)

    def test_preflight_read_only_and_explicit_no_durable_claim(self):
        with patch.object(swpc.portable, "verify",
                          side_effect=fake_receipt) as verified:
            result = self.run_preflight()
        self.assertEqual(result["preflight"], "PASS")
        self.assertEqual(result["execution_mode"], "DRY_RUN_NO_VAULT_WRITE")
        self.assertEqual(result["source_bundle_sha256"], self.sha)
        self.assertTrue(result["source_originals_sha256_replayed"])
        self.assertFalse(result["durable_storage_verified"])
        self.assertFalse(result["independent_offsite_copy_verified"])
        self.assertFalse(result["independent_physical_disk_verified"])
        self.assertFalse((self.vault / self.key).exists())
        self.assertEqual(verified.call_count, 1)

    def test_explicit_apply_then_vault_audit_and_independent_restore(self):
        with patch.object(swpc.portable, "verify", side_effect=fake_receipt):
            result = swpc.execute(self.artifacts, self.vault, self.restore_dir,
                                   self.key, self.sha)
        self.assertEqual(result["local_deposit"], "PASS")
        self.assertEqual(result["stored_bundle_audit"], "PASS")
        self.assertEqual(result["local_restore_and_offline_cold_replay"], "PASS")
        self.assertEqual(result["restored_bundle_sha256"], self.sha)
        self.assertEqual((self.vault / self.key /
                          swpc.local_vault.BUNDLE_NAME).read_bytes(),
                         self.zipfile.read_bytes())
        self.assertEqual((self.restore_dir /
                          f"{self.key}-restored.zip").read_bytes(),
                         self.zipfile.read_bytes())
        self.assertFalse(result["durable_storage_verified"])
        self.assertFalse(result["production_write_authorized"])

    def test_separately_pinned_sha_must_match_before_writes(self):
        with patch.object(swpc.portable, "verify",
                          side_effect=fake_receipt) as verified:
            with self.assertRaisesRegex(ValueError, "separately pinned"):
                self.run_preflight("0" * 64)
        self.assertFalse((self.vault / self.key).exists())
        self.assertEqual(verified.call_count, 0)

    def test_mismatched_receipt_and_sidecar_prevent_deposit(self):
        with patch.object(swpc.portable, "verify", side_effect=fake_receipt):
            (self.artifacts / swpc.COLD_RECEIPT).write_text(
                '{"wrong":"receipt"}')
            with self.assertRaisesRegex(ValueError, "receipts disagree"):
                self.run_preflight()
            (self.artifacts / swpc.COLD_RECEIPT).write_text(
                (self.artifacts / swpc.PACK_RECEIPT).read_text())
            (self.artifacts / swpc.PIN).write_text(
                "0"*64+"  portable-original-evidence.zip\n")
            with self.assertRaisesRegex(ValueError, "sidecar mismatch"):
                self.run_preflight()
        self.assertFalse((self.vault / self.key).exists())

    def test_no_symlinks_or_unsafe_output_targets(self):
        with patch.object(swpc.portable, "verify", side_effect=fake_receipt):
            relocated = self.artifacts / "old.zip"
            self.zipfile.rename(relocated)
            self.zipfile.symlink_to(relocated)
            with self.assertRaisesRegex(ValueError, "nonregular artifact"):
                self.run_preflight()
            self.zipfile.unlink()
            relocated.rename(self.zipfile)
            (self.vault / self.key).mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.run_preflight()
            (self.vault / self.key).rmdir()
            (self.restore_dir / f"{self.key}-restored.zip").write_text("EXISTS")
            with self.assertRaisesRegex(ValueError, "restore target already exists"):
                self.run_preflight()

    def test_source_bundle_cannot_claim_durable_storage(self):
        def bad_receipt(archive):
            res = fake_receipt(archive)
            res["durable_storage_verified"] = True
            return res
        receipt = json.dumps(bad_receipt(self.zipfile))
        for name in (swpc.PACK_RECEIPT, swpc.COLD_RECEIPT):
            (self.artifacts / name).write_text(receipt)
        with patch.object(swpc.portable, "verify", side_effect=bad_receipt):
            with self.assertRaisesRegex(ValueError, "untrusted research"):
                self.run_preflight()

    def test_invalid_sha_key_or_unprovisioned_vault_fail(self):
        with self.assertRaisesRegex(ValueError, "expected SHA-256"):
            self.run_preflight("not-valid")
        with patch.object(swpc.portable, "verify", side_effect=fake_receipt):
            with self.assertRaisesRegex(ValueError, "invalid evidence key"):
                swpc.preflight(self.artifacts, self.vault, self.restore_dir,
                               "../escape", self.sha)
            with self.assertRaisesRegex(ValueError, "vault root missing"):
                swpc.preflight(self.artifacts, self.root / "not-mounted",
                               self.restore_dir, self.key, self.sha)


if __name__ == "__main__":
    unittest.main()

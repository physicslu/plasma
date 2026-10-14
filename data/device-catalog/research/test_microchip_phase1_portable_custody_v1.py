"""Offline Microchip original evidence portable custody security regressions.

Fixtures are SYNTHETIC ONLY. Live CI independently reruns the real original
chart/MCP source replay to prove the bundle contains genuine source bytes.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import microchip_phase1_portable_custody_v1 as custody


class PortableSourceCustodyTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        for folder in ("chart", "mcp-e5", "mcp-pic32"):
            (self.root / folder).mkdir()
        (self.root / "chart/original-chart.html").write_bytes(
            b"<html>synthetic fixture only</html>")
        (self.root / "chart/manifest.json").write_text('{"synthetic":true}')
        for folder in ("mcp-e5", "mcp-pic32"):
            (self.root / folder / "manifest.json").write_text(
                '{"synthetic":true}')
            (self.root / folder / "response-00.txt").write_bytes(b"fake RPC")
        (self.root / "plan.json").write_text('{"synthetic":true}')
        (self.root / "report.json").write_text('{"synthetic":true}')
        self.archive = self.root / "bundle.zip"
        self.sources = {
            "chart": self.root / "chart",
            "mcp-e5": self.root / "mcp-e5",
            "mcp-pic32": self.root / "mcp-pic32",
            "plan": self.root / "plan.json",
            "report": self.root / "report.json",
        }
        self.fake_validation = {
            "chart_original_sha256": "a" * 64,
            "original_chart_bytes": 34,
            "pinned_openocd_commit": "b" * 40,
            "mcp_exact_source_candidates": {"sam-e5-d5": 10,
                                            "pic32mx": 14},
            "observed_p0_chart_denominator": 341,
        }

    def fake_replay(self, _root):
        return self.fake_validation

    def test_deterministic_hashes_no_durable_custody_claim(self):
        with patch.object(custody, "validate_tree", side_effect=self.fake_replay):
            receipt = custody.pack(self.sources, self.archive)
            again = custody.verify(self.archive)
            self.assertEqual(receipt, again)
            self.assertTrue(receipt["source_originals_sha256_replayed"])
            self.assertFalse(receipt["durable_storage_verified"])
            self.assertFalse(receipt["independent_offsite_copy_verified"])
            self.assertFalse(receipt["production_write_authorized"])
            independent = self.root / "second.zip"
            custody.pack(self.sources, independent)
        self.assertEqual(self.archive.read_bytes(), independent.read_bytes())
        self.assertEqual(receipt["bundle_sha256"],
                         hashlib.sha256(self.archive.read_bytes()).hexdigest())
        with zipfile.ZipFile(self.archive) as z:
            self.assertEqual(z.namelist(), sorted(z.namelist()))
            index = json.loads(z.read("bundle-index.json"))
        self.assertEqual(index["schema_version"], 1)
        self.assertFalse(index["durable_storage_verified"])
        self.assertEqual([f["name"] for f in index["files"]],
                         sorted(f["name"] for f in index["files"]))

    def test_archive_tampering_is_detected(self):
        with patch.object(custody, "validate_tree", side_effect=self.fake_replay):
            custody.pack(self.sources, self.archive)
            with zipfile.ZipFile(self.archive) as z:
                payload = {n: z.read(n) for n in z.namelist()}
            payload["chart/original-chart.html"] += b"TAMPER"
            changed = self.root / "tampered.zip"
            with zipfile.ZipFile(changed, "w") as z:
                for name, raw in payload.items():
                    z.writestr(name, raw, compress_type=zipfile.ZIP_STORED)
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                custody.verify(changed)

    def test_cannot_fake_durable_retention_or_production(self):
        with patch.object(custody, "validate_tree", side_effect=self.fake_replay):
            custody.pack(self.sources, self.archive)
            with zipfile.ZipFile(self.archive) as z:
                payload = {n: z.read(n) for n in z.namelist()}
            index = json.loads(payload["bundle-index.json"])
            index["durable_storage_verified"] = True
            payload["bundle-index.json"] = json.dumps(index).encode()
            forged = self.root / "forged.zip"
            with zipfile.ZipFile(forged, "w") as z:
                for name, raw in payload.items():
                    z.writestr(name, raw, compress_type=zipfile.ZIP_STORED)
            with self.assertRaisesRegex(ValueError, "false durable"):
                custody.verify(forged)

    def test_extra_nested_source_and_symlink_rejected(self):
        (self.root / "chart/other").mkdir()
        with self.assertRaisesRegex(ValueError, "nested/nonregular"):
            custody.raw_entries(self.sources)
        (self.root / "chart/other").rmdir()
        (self.root / "chart/evil-secret.txt").write_text("secret")
        with self.assertRaisesRegex(ValueError, "unexpected original-source"):
            custody.raw_entries(self.sources)
        (self.root / "chart/evil-secret.txt").unlink()
        (self.root / "chart/shortcut.txt").symlink_to("manifest.json")
        with self.assertRaisesRegex(ValueError, "nested/nonregular"):
            custody.raw_entries(self.sources)

    def test_wrong_source_role_and_path_traversal_rejected(self):
        self.assertFalse(custody.safe_name("../outside.txt"))
        self.assertFalse(custody.safe_name("chart/../../evil"))
        self.assertFalse(custody.safe_name("mcp-e5/.ssh/config"))
        self.assertFalse(custody.safe_name("mcp-e5/headers.txt"))
        self.assertFalse(custody.safe_name("mcp-e5/../../github-token"))
        self.assertTrue(custody.safe_name("mcp-e5/response-03.txt"))
        with self.assertRaisesRegex(ValueError, "all original source roots"):
            custody.raw_entries({"chart": self.root / "chart"})

    def test_missing_or_duplicate_zip_member_fails_closed(self):
        bad = self.root / "unsafe.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("chart/../../secret", "bad")
            z.writestr("bundle-index.json", "{}")
        with self.assertRaisesRegex(ValueError, "unsafe/duplicate/incomplete"):
            custody.verify(bad)
        dupe = self.root / "duplicate.zip"
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(dupe, "w") as z:
                z.writestr("plan.json", "{}")
                z.writestr("plan.json", "{}")
        with self.assertRaisesRegex(ValueError, "unsafe/duplicate/incomplete"):
            custody.verify(dupe)

    def test_full_manufacturer_semantic_replay_required_without_mocks(self):
        # Synthetic HTML is never allowed to pass an actual manufacturer
        # source validator. The mocks above test ZIP mechanics ONLY.
        with self.assertRaises(ValueError):
            custody.validate_tree(self.root)
        with self.assertRaises(ValueError):
            custody.pack(self.sources, self.archive)
        self.assertFalse(self.archive.exists())

    def test_archive_is_not_overwritten(self):
        with patch.object(custody, "validate_tree", side_effect=self.fake_replay):
            custody.pack(self.sources, self.archive)
            with self.assertRaisesRegex(ValueError, "destination already exists"):
                custody.pack(self.sources, self.archive)


if __name__ == "__main__":
    unittest.main()

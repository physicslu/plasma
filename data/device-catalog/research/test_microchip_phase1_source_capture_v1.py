#!/usr/bin/env python3
"""Offline replay/anti-forgery tests for ADR-0002 Phase 1 immutable captures."""
from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

from microchip_phase1_information_v1 import DEFAULT_PATH
from microchip_phase1_source_capture_v1 import (
    ALLOWED, capture, inspect_raw, sha256, validate_dataset_sources,
    verify_capture,
)


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._buf = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._buf.close()

    def read(self, count):
        return self._buf.read(count)


class Phase1OriginalBytesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))

    def test_exact_source_allowlist(self):
        self.assertTrue(validate_dataset_sources(self.dataset))
        data = deepcopy(self.dataset)
        data["source_records"][1]["url"] = "https://example.net/changed.pdf"
        with self.assertRaisesRegex(ValueError, "source"):
            validate_dataset_sources(data)

    def test_complete_capture_and_hash_replay_still_not_admission(self):
        html = (
            b"<!DOCTYPE html><html><body>"
            b"ATSAMD21G18A-MU ATSAMD21G18A-MF"
            b"</body></html>"
        )
        pdf = b"%PDF-1.7\nminimal test bytes\n%%EOF"
        def opener(req, timeout=None):
            if req.full_url.endswith(".pdf"):
                return FakeResponse(200, pdf)
            return FakeResponse(200, html)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "source-capture"
            report = capture(self.dataset, root, opener)
            self.assertEqual(report["source_count"], 2)
            self.assertEqual(report["source_byte_captures"], 2)
            self.assertTrue(report["original_byte_sha256_replay_passed"])
            self.assertFalse(report["internal_admission_ready"])
            self.assertFalse(report["manufacturer_fields_verified_from_capture"])
            manifest = json.loads((root / "manifest.json").read_text())
            by_id = {x["source_id"]: x for x in manifest["source_records"]}
            for source_id in ALLOWED:
                self.assertEqual(by_id[source_id]["state"], "SOURCE_BYTES_CAPTURED")
                self.assertEqual(
                    by_id[source_id]["original_bytes_sha256"],
                    sha256((root / by_id[source_id]["file"]).read_bytes()))
            # HTML text tokens alone never prove the structured exact SKU row.
            self.assertFalse(report["product_catalog_exact_rows_verified"])
            # Original byte modification must be detected.
            (root / by_id["microchip-atsamd21g18-product-page"]["file"]).write_bytes(
                b"<!doctype html><html>tampered</html>"
            )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_capture(self.dataset, root)

    def test_network_denied_is_blocker_never_fake_sha(self):
        def opener(req, timeout=None):
            raise urllib.error.URLError("offline fixture")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "capture"
            result = capture(self.dataset, root, opener)
            self.assertEqual(result["source_byte_captures"], 0)
            self.assertEqual(len(result["source_blockers"]), 2)
            self.assertFalse(result["internal_admission_ready"])
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertTrue(all(x["original_bytes_sha256"] is None
                                and x["file"] is None
                                for x in manifest["source_records"]))

    def test_masquerading_pdf_or_page_rejected(self):
        with self.assertRaisesRegex(ValueError, "PDF source"):
            inspect_raw("microchip-sam-d21-da1-family-datasheet-ds40001882h",
                        b"<html><body>access denied</body></html>")
        with self.assertRaisesRegex(ValueError, "product response not HTML"):
            inspect_raw("microchip-atsamd21g18-product-page", b"%PDF-1.7\n%%EOF")

    def test_source_capture_does_not_write_production(self):
        def opener(req, timeout=None):
            return FakeResponse(200, b"<html>ignored</html>")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "production" / "source"
            with self.assertRaisesRegex(ValueError, "Production output"):
                capture(self.dataset, root, opener)

    def test_forged_manifest_capability_rejected(self):
        def opener(req, timeout=None):
            raise urllib.error.URLError("blocked")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "capture"
            capture(self.dataset, root, opener)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["fields_verified_by_source_capture"] = True
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "unapproved"):
                verify_capture(self.dataset, root)


if __name__ == "__main__":
    unittest.main()

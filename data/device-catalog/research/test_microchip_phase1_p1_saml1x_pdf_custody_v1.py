#!/usr/bin/env python3
"""Fail-closed synthetic tests; ONLY live CI PDF capture is vendor evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import microchip_phase1_p1_saml1x_pdf_custody_v1 as pdf


def mock_original():
    return (b"%PDF-1.7\n" + b"safe synthetic fixture " * 700 +
            b"\n%%EOF\n")


def mock_reader(_path, page):
    if page == 14:
        return (
            "SAM L10/L11 Family Configuration Summary "
            "Table 1-1. SAM L10/L11 Device-Specific Features\n"
            + "\n".join(pdf.BASES) +
            "\nDatasheet DS60001513G-page 14\n"
        )
    if page == 16:
        return (
            "SAM L10/L11 Family Ordering Information\n"
            "ATSAML 11 D 14 A M U T KPH\n"
            "10 = Cortex-M23 CPU 11 = Cortex-M23 CPU with TrustZone "
            "D = 24 Pins E = 32 Pins "
            "14 = 16 KB 15 = 32 KB 16 = 64 KB "
            "TQFP VQFN SSOP WLCSP\n"
            "Datasheet DS60001513G-page 16\n"
        )
    raise ValueError("unexpected page")


class OriginalPdfEvidenceTest(unittest.TestCase):
    def test_valid_source_only_not_icpn_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "research"
            result = pdf.capture(root, getter=mock_original, reader=mock_reader)
            self.assertEqual(result["status"],
                             "SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED")
            self.assertEqual(result["original_pdf_sha256"],
                             hashlib.sha256(mock_original()).hexdigest())
            self.assertEqual(len(result["observations"]
                                 ["family_base_names_observed_on_page_14"]), 12)
            self.assertEqual(result["new_phase1_exact_variant_verified_fields"], 0)
            self.assertEqual(result["manufacturer_exact_icpn_count_from_pdf"], 0)
            self.assertFalse(result["software_supported_claimed"])
            self.assertFalse(result["production_write_authorized"])
            self.assertFalse(result["catalog_publication_authorized"])
            self.assertEqual(pdf.audit(root, mock_reader), result)

    def test_missing_vendor_source_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            def unreachable():
                raise OSError("publisher unavailable")
            root = Path(tmp) / "source"
            result = pdf.capture(root, getter=unreachable, reader=mock_reader)
            self.assertEqual(result["status"], "SOURCE_NOT_AVAILABLE")
            self.assertIsNone(result["original_pdf_sha256"])
            self.assertEqual(pdf.audit(root, mock_reader), result)

    def test_html_shell_rejected_before_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            result = pdf.capture(root, getter=lambda: b"<html>blocked</html>",
                                 reader=mock_reader)
            self.assertEqual(result["status"], "SOURCE_NOT_AVAILABLE")
            self.assertFalse((root / pdf.FILENAME).exists())

    def test_wrong_revision_captured_but_cannot_claim_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            def changed(_path, page):
                return mock_reader(_path, page).replace("DS60001513G",
                                                       "DS60001513F")
            result = pdf.capture(root, getter=mock_original, reader=changed)
            self.assertEqual(
                result["status"],
                "SOURCE_BYTES_CAPTURED_SEMANTICS_NOT_REPLAYABLE")
            self.assertTrue((root / pdf.FILENAME).is_file())
            self.assertIsNone(result["observations"])
            self.assertEqual(result["new_phase1_exact_variant_verified_fields"], 0)
            self.assertEqual(pdf.audit(root, changed), result)

    def test_missing_one_family_row_rejected(self):
        def missing(_path, page):
            return mock_reader(_path, page).replace("SAML11E16", "SAML11E99")
        with self.assertRaisesRegex(ValueError, "twelve"):
            pdf.page_evidence(missing(None, 14), missing(None, 16))

    def test_malformed_ordering_page_rejected(self):
        text = mock_reader(None, 16).replace("WLCSP", "")
        with self.assertRaisesRegex(ValueError, "ordering page"):
            pdf.page_evidence(mock_reader(None, 14), text)

    def test_pdf_original_byte_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            pdf.capture(root, getter=mock_original, reader=mock_reader)
            with (root / pdf.FILENAME).open("ab") as dst:
                dst.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                pdf.audit(root, mock_reader)

    def test_forged_verified_field_and_status_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            pdf.capture(root, getter=mock_original, reader=mock_reader)
            manifest = root / "manifest.json"
            original = json.loads(manifest.read_text(encoding="utf-8"))
            for changes in (
                {"new_phase1_exact_variant_verified_fields": 126},
                {"software_supported_claimed": True},
                {"production_write_authorized": True},
                {"pdf_ordering_conventions_are_exact_icpn_rows": True},
            ):
                changed = copy.deepcopy(original)
                changed.update(changes)
                manifest.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "prohibited"):
                    pdf.audit(root, mock_reader)

    def test_source_endpoint_pinned(self):
        self.assertTrue(pdf.allowed_redirect(pdf.URL))
        for url in (
            "http://ww1.microchip.com/downloads/example.pdf",
            "https://evil.example/downloads/example.pdf",
            "https://ww1.microchip.com.evil.example/downloads/doc.pdf",
            "https://user@ww1.microchip.com/downloads/doc.pdf",
            "https://ww1.microchip.com/invalid/document.pdf",
            "https://ww1.microchip.com/downloads/document.pdf?cmd=1",
        ):
            self.assertFalse(pdf.allowed_redirect(url), url)

    def test_incomplete_pdf_rejected(self):
        for raw in (b"%PDF-1.7" + b"x" * 12000,
                    b"%PDF-1.7\n%%EOF\n",
                    b"<html>" + b"r" * 12000 + b"%%EOF"):
            with self.assertRaises(ValueError):
                pdf.validate_pdf_bytes(raw)


if __name__ == "__main__":
    unittest.main()

"""Synthetic HTML parser/security tests. Synthetic fixtures are NOT original source evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import microchip_phase1_p0_samr30_online_original_v1 as source


def sample(lane):
    body = ['<html><body><table>',
            '<tr><th>Ordering Code</th><th>FLASH (bytes)</th>'
            '<th>SRAM (bytes)</th><th>Package</th>'
            '<th>Carrier Type</th></tr>']
    for icpn, cells in source.EXPECTED[lane].items():
        carrier = cells[3].replace("&", "&amp;")
        body.append("<tr>" +
                    "".join(f"<td>{x}</td>" for x in
                            (icpn, cells[0], cells[1], cells[2], carrier)) +
                    "</tr>")
    body.append("</table></body></html>")
    return "".join(body).encode("utf-8")


class SAMR30OriginalSourceTests(unittest.TestCase):
    def test_exact_four_rows_from_synthetic_layout_not_qualified(self):
        for lane in source.URLS:
            records = source.parse_original_html(sample(lane), lane)
            self.assertEqual(len(records), 2)
            for row in records:
                self.assertFalse(row["phase1_verified_authorized"])
                self.assertFalse(row["original_pdf_crosscheck_completed"])
                self.assertIn(row["icpn"], source.EXPECTED[lane])

    def test_captured_sources_are_replayed_again_from_saved_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"online-src"
            result=source.capture(root, getter=lambda _uri,lane:sample(lane))
            self.assertEqual(result["exact_rows_observed"], 4)
            self.assertEqual(result["phase1_exact_fields_verified"], 0)
            self.assertFalse(result["original_pdf_semantics_replayed"])
            self.assertEqual(source.replay(root),result)
            original=root/"manufacturer-samr30e-original.html"
            original.write_bytes(original.read_bytes()+b"not in official hash")
            with self.assertRaisesRegex(ValueError,"original HTML SHA mismatch"):
                source.replay(root)

    def test_bounded_missing_source_keeps_failed_manifest_and_no_fake_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"blocked"
            def getter(_,lane):
                if lane == "SAMR30G":
                    raise OSError("synthetic manufacturer HTTP block")
                return sample(lane)
            with self.assertRaisesRegex(ValueError,"SOURCE_NOT_AVAILABLE"):
                source.capture(root,getter=getter)
            m=json.loads((root/"manifest.json").read_text())
            self.assertFalse(m["live_original_source_observation_complete"])
            self.assertEqual(m["sources"][1]["status"],"SOURCE_NOT_AVAILABLE")
            self.assertFalse(m["phase1_icpn_fields_verified_by_this_source_only"])
            with self.assertRaisesRegex(ValueError,"untrusted original source-only receipt"):
                source.replay(root)

    def test_http200_html_shell_archived_but_never_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"source"
            def page(_uri,lane):
                if lane=="SAMR30E":
                    return b"<html><head><title>Microchip Manual</title></head><body><div id='app'></div></body></html>"
                return sample(lane)
            with self.assertRaisesRegex(ValueError,"SOURCE_NOT_AVAILABLE_OR_UNREPLAYABLE"):
                source.capture(root,getter=page)
            receipt=source.audit_original_receipt(root)
            self.assertFalse(receipt["live_original_source_observation_complete"])
            first=receipt["sources"][0]
            self.assertEqual(first["status"],"SOURCE_BYTES_CAPTURED_TABLE_NOT_REPLAYABLE")
            self.assertEqual(first["exact_ordering_row_count"],0)
            self.assertIsNotNone(first["original_sha256"])
            self.assertIsNotNone(first["file"])
            self.assertFalse(any(first["manufacturer_order_code_tokens_present"].values()))
            self.assertFalse(receipt["phase1_icpn_fields_verified_by_this_source_only"])
            original=root/first["file"]
            original.write_bytes(b"<html>TAMPER</html>")
            with self.assertRaisesRegex(ValueError,"original HTML SHA mismatch"):
                source.audit_original_receipt(root)

    def test_forged_exact_sku_row_or_duplicate_is_not_accepted(self):
        html=sample("SAMR30E").replace(b"256K",b"128K",1)
        with self.assertRaisesRegex(ValueError,"source table differs"):
            source.parse_original_html(html,"SAMR30E")
        duplicate=sample("SAMR30E").replace(b"</table>",b"<tr><td>ATSAMR30E18A-MU</td><td>256K</td><td>32K</td><td>QFN32</td><td>Tray</td></tr></table>")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            source.parse_original_html(duplicate,"SAMR30E")
        foreign=sample("SAMR30E").replace(b"ATSAMR30E18A-MU",b"ATSAMR30G18A-MU")
        with self.assertRaisesRegex(ValueError,"foreign ordering"):
            source.parse_original_html(foreign,"SAMR30E")

    def test_website_url_allowlist_and_manifest_claims(self):
        self.assertTrue(source.is_official_endpoint(source.URLS["SAMR30E"],"SAMR30E"))
        self.assertFalse(source.is_official_endpoint(
            "https://untrusted.example/oxy/doc","SAMR30E"))
        self.assertFalse(source.is_official_endpoint(
            source.URLS["SAMR30E"] + "?altered=yes","SAMR30E"))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"saved"
            source.capture(root, getter=lambda _uri,lane:sample(lane))
            m=json.loads((root/"manifest.json").read_text())
            m["pdf_semantic_crosscheck_completed"]=True
            (root/"manifest.json").write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,"cannot establish"):
                source.replay(root)


if __name__=="__main__":
    unittest.main()

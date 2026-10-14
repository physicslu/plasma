#!/usr/bin/env python3
"""Fully synthetic Microchip Product API original-byte replay tests."""
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError

import microchip_phase1_product_api_v1 as source


def synthetic_rows():
    rows = []
    # Synthetic strings are *not* original manufacturer order codes.
    identifiers = ["ATSAMD21G18A-MU", "ATSAMD21G18A-MF"] + [
        "ATSAMD21G18A-SYN%02d" % i for i in range(21)
    ] + ["OTHER_FUZZY_PART"]
    for name in identifiers:
        rows.append({
            "manufacturer": "Microchip Technology Inc.",
            "part_number": name, "sku": name,
            "base_part_number": "ATSAMD21G18",
            "package_type": "VQFN", "pin_count": "48",
            "lifecycle_status": "REL", "datasheet_url": "https://ww1.microchip.com/fake.pdf",
            "parametric_data_url": "https://www.microchipdirect.com/feed/json/test.json",
        })
    return rows


class Phase1ProductApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original"
        self.rows = synthetic_rows()

    def getter(self, url):
        params = parse_qs(urlparse(url).query)
        size = int(params["pagesize"][0])
        number = int(params["pagenumber"][0])
        total = len(self.rows)
        subset = self.rows[(number - 1) * size: number * size]
        response = {
            "totalRecords": total, "pagesize": size, "pagenumber": number,
            "totalPages": (total + size - 1) // size,
            "data": subset,
        }
        return json.dumps(response, separators=(",", ":")).encode()

    def test_capture_replay_and_identity_crosswalk(self):
        output = source.capture(self.root, source.PILOT_QUERY, getter=self.getter)
        self.assertEqual(output["source_total_results"], 24)
        self.assertEqual(output["exact_prefix_candidate_count"], 23)
        self.assertEqual(output["fuzzy_or_base_only_results_excluded"], 1)
        self.assertEqual(output["raw_response_files"], 3)
        self.assertTrue(output["independent_page_size_agreement"])
        self.assertEqual(output, source.replay(self.root, source.PILOT_QUERY))
        self.assertEqual([x["status"] for x in output["pilot_crosscheck"]],
                         ["OBSERVED", "OBSERVED"])
        self.assertTrue(all(set(x["fields"].values()) == {"AGREE"}
                            for x in output["pilot_crosscheck"]))
        self.assertEqual(output["internal_admission_count"], 0)
        self.assertIsNone(output["software_supported_count"])
        self.assertFalse(output["catalog_publication_authorized"])
        self.assertEqual(
            {x["source_file"] for x in output["exact_identity_candidates"] if x["icpn"] == "ATSAMD21G18A-MU"},
            {"api-size20-page1.json"},
        )

    def test_source_bytes_tampering_fails_closed(self):
        source.capture(self.root, source.PILOT_QUERY, getter=self.getter)
        p = self.root / "api-size20-page1.json"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            source.replay(self.root, source.PILOT_QUERY)

    def test_independent_pagination_mismatch_fails_closed(self):
        def modified_getter(url):
            raw = self.getter(url)
            if "pagesize=60" in url:
                value = json.loads(raw)
                value["data"][0]["package_type"] = "CONFLICTING"
                return json.dumps(value).encode()
            return raw
        with self.assertRaisesRegex(ValueError, "independent API pagination disagrees"):
            source.capture(self.root, source.PILOT_QUERY, getter=modified_getter)
        manifest = json.loads((self.root / "manifest.json").read_text())
        self.assertTrue(manifest["source_capture_complete"])
        with self.assertRaisesRegex(ValueError, "independent API pagination disagrees"):
            source.replay(self.root, source.PILOT_QUERY)

    def test_network_failure_preserves_incomplete_manifest(self):
        def fail(_url):
            raise OSError("official endpoint unavailable")
        with self.assertRaisesRegex(ValueError, "SOURCE_NOT_AVAILABLE"):
            source.capture(self.root, source.PILOT_QUERY, getter=fail)
        manifest = json.loads((self.root / "manifest.json").read_text())
        self.assertFalse(manifest["source_capture_complete"])
        self.assertIn("official endpoint unavailable", manifest["error"])
        with self.assertRaisesRegex(ValueError, "incomplete/untrusted"):
            source.replay(self.root, source.PILOT_QUERY)

    def test_malformed_or_zero_result_is_not_complete_inventory(self):
        self.assertRaisesRegex(
            ValueError, "empty/unbounded", source.parse_response,
            json.dumps({"totalRecords": 0, "pagesize": 20, "pagenumber": 1,
                        "totalPages": 0, "data": []}).encode(),
            source.PILOT_QUERY, 20, 1)
        with self.assertRaisesRegex(ValueError, "non-JSON"):
            source.parse_response(b"<html>403</html>", source.PILOT_QUERY, 20, 1)

    def test_duplicate_sku_and_invalid_pin_count_fail_closed(self):
        data = json.loads(self.getter(source.url_for(source.PILOT_QUERY, 20, 1)))
        data["data"][1]["part_number"] = data["data"][0]["part_number"]
        with self.assertRaisesRegex(ValueError, "duplicate commercial code"):
            source.parse_response(json.dumps(data).encode(), source.PILOT_QUERY, 20, 1)
        data = json.loads(self.getter(source.url_for(source.PILOT_QUERY, 20, 1)))
        data["data"][0]["pin_count"] = "unknown"
        with self.assertRaisesRegex(ValueError, "pin_count invalid"):
            source.parse_response(json.dumps(data).encode(), source.PILOT_QUERY, 20, 1)

    def test_url_query_and_redirect_allowlist(self):
        self.assertTrue(source.official_url(source.url_for(source.PILOT_QUERY, 20, 1)))
        self.assertFalse(source.official_url("https://evil.example/productInfo"))
        self.assertFalse(source.exact_query_prefix("ATSAMD21G18A", source.PILOT_QUERY))
        self.assertTrue(source.exact_query_prefix("ATSAMD21G18A-MU", source.PILOT_QUERY))
        self.assertFalse(source.exact_query_prefix("ATSAMD21G18A9-MU", source.PILOT_QUERY))
        with self.assertRaisesRegex(ValueError, "invalid bounded"):
            source.url_for("PIC32MX/evil", 20, 1)
        with self.assertRaisesRegex(ValueError, "unapproved page"):
            source.url_for(source.PILOT_QUERY, 999, 1)

    def test_conflict_is_reported_not_silently_promoted(self):
        output = source.capture(self.root, source.PILOT_QUERY, getter=self.getter)
        proposed = {x["icpn"]: x for x in output["exact_identity_candidates"]}
        proposed["ATSAMD21G18A-MU"]["package_raw"] = "OTHER"
        pilot = json.loads(source.PILOT.read_text(encoding="utf-8"))
        compared = source.pilot_comparison(list(proposed.values()), pilot)
        self.assertEqual(compared[1]["fields"]["package"], "CONFLICT")
        self.assertTrue(all(r["internal_admission_state"] == "NOT_ADMITTED"
                            for r in pilot["records"]))


if __name__ == "__main__":
    unittest.main()

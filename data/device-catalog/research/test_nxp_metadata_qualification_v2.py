#!/usr/bin/env python3
"""Offline fail-closed NXP manufacturer HTML and evidence-lock regressions."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nxp_qual_v2", HERE / "nxp_metadata_qualification_v2.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

EXACT = "K32L2A31VLH1A"
PAGE = """<html><body><h1>K32L2A31VLH1A</h1>
<div>Package</div><div>LQFP64: LQFP64, low profile quad flat; 64 terminals; 0.5 mm pitch</div>
<div>Buy Options</div><table>
<tr><td>Flash (kB)</td><td>256</td></tr>
<tr><td>Ambient Operating Temperature (Min to Max) (℃)</td><td>-40 to 105</td></tr>
</table></body></html>""".encode()


class ManufacturerEvidenceReplayContract(unittest.TestCase):
    def test_all_four_values_are_independently_in_manufacturer_html(self):
        fields = {"package_raw":"LQFP64", "package_terminals":64,
                  "flash_kb_raw":256, "ambient_temperature_raw":"-40 to 105"}
        mod.verify_html_exact_sku(EXACT, PAGE, fields)

    def test_requested_commercial_identity_must_be_exact_h1(self):
        with self.assertRaisesRegex(ValueError, "exact part heading"):
            mod.verify_html_exact_sku(EXACT+"R", PAGE, {})

    def test_package_and_terminals_must_match_manufacturer_body(self):
        with self.assertRaisesRegex(ValueError, "terminal/ball"):
            mod.verify_html_exact_sku(EXACT, PAGE, {"package_raw":"LQFP64",
                                                    "package_terminals":48})
        with self.assertRaisesRegex(ValueError, "package source mismatch"):
            mod.verify_html_exact_sku(EXACT, PAGE, {"package_raw":"QFN64"})

    def test_numeric_flash_mismatch_fails_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError, "flash value mismatch"):
            mod.verify_html_exact_sku(EXACT, PAGE, {"flash_kb_raw":512})

    def test_ambient_not_interchangeable_with_junction(self):
        with self.assertRaisesRegex(ValueError, "ambient temperature"):
            mod.verify_html_exact_sku(EXACT, PAGE,
                                      {"ambient_temperature_raw":"-40 to 125"})

    def test_bga_ball_evidence_is_not_a_lead_terminal(self):
        page = PAGE.replace(b"LQFP64", b"LFBGA196").replace(b"64 terminals", b"196 balls")
        mod.verify_html_exact_sku(EXACT, page,
                                  {"package_raw":"LFBGA196","package_terminals":196})

    def test_missing_field_stays_missing(self):
        mod.verify_html_exact_sku(EXACT, PAGE, {"flash_kb_raw":None,
                                                "ambient_temperature_raw":None})

    def test_source_shard_json_sha_mismatch_is_blocked(self):
        lock = json.loads(mod.LOCK.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            first = base / "nxp-part-metadata-shard-0"
            first.mkdir()
            (first/"metadata-shard.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "digest changed"):
                mod.verify_shard_lock(base, lock)

    def test_scope_denominator_cannot_be_fabricated(self):
        lock = json.loads(mod.LOCK.read_text(encoding="utf-8"))
        lock["claims"]["global_nxp_active_denominator"] = 353
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "scope/authority"):
                mod.verify_shard_lock(Path(folder), lock)


if __name__ == "__main__":
    unittest.main()

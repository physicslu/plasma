"""NXP Phase1 IC Selector visibility vs Production/Job fail-closed contract."""
from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from plasma_web.device_catalog import DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler, _parse_target_device
from plasma_web.nxp_phase1_selector import (
    EXPECTED_NEW_IDENTIFIED, PHASE1_CATALOG_ORIGIN, SOURCE_BLOBS,
    build_nxp_phase1_selector_catalog,
)

PART = "LPC11U68JBD48E"

class NxpPhase1ICSelectorVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production = get_default_device_catalog()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, uri):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        try:
            connection.request("GET", uri)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_phase1_exact_part_search_and_detail_source(self):
        status, response = self.request("/api/devices/search?q="+PART+"&visibility=phase1&limit=30")
        self.assertEqual(status, 200)
        self.assertEqual(response["visibility"], "phase1")
        self.assertEqual(response["total_count"], 1)
        item = response["results"][0]
        self.assertEqual((item["vendor"],item["identifier"],item["icpn"]),("NXP",PART,PART))
        self.assertEqual(item["catalog"]["scope"], "phase1_identified")
        self.assertEqual(item["phase1"], {"identity_state":"IDENTIFIED","information_complete":False})
        self.assertEqual(item["base_device"], "LPC11U68JBD48")
        self.assertEqual(item["package"], "LQFP48")
        self.assertEqual(item["flash_size"], "256 kB")
        self.assertEqual(item["backend"]["mapping_status"], "no_mapping")
        self.assertEqual(item["backend"]["target_config"], "")
        self.assertIsNone(item["selected_profile"])
        self.assertIsNone(item["openocd_software_qualification"])
        self.assertIsNone(item["backend_candidate"])
        self.assertEqual(item["physical_validation"]["ppu_status"], "no_evidence")
        self.assertEqual(item["physical_validation"]["socket_status"], "no_evidence")
        self.assertIn("935303821551", item["catalog_verification"]["source_reference"])
        self.assertTrue(item["catalog_verification"]["source_authority"].startswith("https://www.nxp.com/"))

    def test_legacy_production_search_semantics_unchanged(self):
        for extra in ("", "&visibility=production"):
            status, response = self.request("/api/devices/search?q="+PART+extra)
            self.assertEqual(status,200)
            self.assertEqual(response["catalog_size"], self.production.size)
            self.assertEqual(response["total_count"],0)
        status, data = self.request("/api/devices/search?q=STM32F103C8T6&limit=5")
        self.assertEqual(status,200)
        self.assertEqual(data["catalog_size"],self.production.size)
        self.assertEqual(data["results"][0]["catalog"]["scope"],"production_admitted")

    def test_production_plus_phase1_union_and_pagination(self):
        merged = build_nxp_phase1_selector_catalog(self.production)
        self.assertEqual(merged.size,self.production.size+EXPECTED_NEW_IDENTIFIED)
        self.assertEqual(EXPECTED_NEW_IDENTIFIED,73)
        self.assertEqual(sum(r.catalog_origin == PHASE1_CATALOG_ORIGIN for r in merged.records),73)
        for q in ("LPC11U68JBD48E","NXP"):
            status, response = self.request(f"/api/devices/search?q={q}&visibility=phase1&limit=5&offset=0")
            self.assertEqual(status,200)
            self.assertEqual(response["catalog_size"],merged.size)
            self.assertLessEqual(len(response["results"]),5)
            self.assertGreaterEqual(response["total_count"],1)
            self.assertEqual(response["count"],len(response["results"]))
        status, response = self.request("/api/devices/search?q=NXP&visibility=phase1&limit=5&offset=5")
        self.assertEqual(status,200)
        self.assertEqual(len(response["results"]),5)

    def test_phase1_research_not_source_reviewed_absent(self):
        for q in ("LPC1114FBD48/333J","LPC2148FBD64","THIS_IS_NOT_A_REAL_NXP_DEVICE"):
            status, response = self.request("/api/devices/search?q="+q+"&visibility=phase1")
            self.assertEqual(status,200)
            self.assertEqual(response["total_count"],0)

    def test_runtime_job_target_resolution_remains_production_only(self):
        with self.assertRaisesRegex(ValueError,"canonical Device Catalog record"):
            _parse_target_device({"vendor":"NXP","identifier":PART})
        self.assertIsNone(self.production.resolve("NXP",PART))

    def test_bad_visibility_rejected(self):
        for v in ("research","all","supported"):
            status, response = self.request("/api/devices/search?q="+PART+"&visibility="+v)
            self.assertEqual(status,400)
            self.assertEqual(response["error"]["error_type"],"INVALID_DEVICE_SEARCH")

    def test_missing_or_modified_phase1_source_fails_closed(self):
        from plasma_web import nxp_phase1_selector as audit
        with TemporaryDirectory() as temp:
            root=Path(temp)
            source_dir=root/"data/device-catalog/research"
            source_dir.mkdir(parents=True)
            evidence_root=audit.default_runtime_evidence_root()
            self.assertIsNotNone(evidence_root)
            original=evidence_root/"data/device-catalog/research"
            for fn,*_ in SOURCE_BLOBS:
                (source_dir/fn).write_bytes((original/fn).read_bytes())
            (source_dir/SOURCE_BLOBS[2][0]).write_text("icpn,manufacturer_12nc\nFORGED,012345678901\n",encoding="utf-8")
            with self.assertRaisesRegex(DeviceCatalogIntegrityError,"Git blob changed"):
                build_nxp_phase1_selector_catalog(self.production,root=root)

    def test_any_missing_source_never_falls_back_to_guessed_catalog(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                build_nxp_phase1_selector_catalog(self.production,root=Path(temp))

if __name__=="__main__":
    unittest.main(verbosity=2)

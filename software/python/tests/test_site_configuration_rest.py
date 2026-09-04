from __future__ import annotations

import json
import tempfile
import textwrap
import threading
import unittest
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_web.gateway_phase2 import Phase2PlasmaWebHandler
from plasma_web.site_configuration import SiteConfigurationController


CONFIG = """
ppu:
  id: ppu-rest-01
  facility_id: test-lab
  model: virtual
  display_name: REST Test PPU
server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 2
  max_queue_depth_per_site: 4
  output_root: output
  log_root: logs
  max_metadata_bytes: 65536
  max_map_bytes: 1048576
  max_binary_bytes: 67108864
sites:
  - {id: 1, enabled: true, interface: mock, target: TARGET-A}
  - {id: 2, enabled: false, interface: mock, target: TARGET-B}
"""


class SiteConfigurationRestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config" / "plasma.yaml"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(textwrap.dedent(CONFIG).lstrip(), encoding="utf-8")

        runtime_snapshot = {
            "ok": True,
            "ppu": {
                "ppu_id": "ppu-rest-01",
                "facility_id": "test-lab",
                "execution": {"busy": False, "active_job_count": 0},
            },
            "sites": [
                {
                    "site_id": 1,
                    "enabled": True,
                    "interface": "mock",
                    "target": "TARGET-A",
                    "state": "idle",
                    "current_job_id": None,
                },
                {
                    "site_id": 2,
                    "enabled": False,
                    "interface": None,
                    "target": None,
                    "state": "disabled",
                    "current_job_id": None,
                },
            ],
        }

        class Handler(Phase2PlasmaWebHandler):
            snapshot = deepcopy(runtime_snapshot)

            def _local_snapshot(self):
                return deepcopy(type(self).snapshot)

        Handler.site_configuration = SiteConfigurationController(self.path)
        Handler.allowed_origins = frozenset({"*"})
        self.handler = Handler
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)

    def _shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method: str, path: str, body=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def test_get_separates_desired_and_actual_state(self) -> None:
        status, payload = self.request("GET", "/api/settings/sites")
        self.assertEqual(status, 200)
        configuration = payload["site_configuration"]
        self.assertFalse(configuration["runtime_apply_supported"])
        self.assertEqual(configuration["source"], "canonical_ppu_config")
        self.assertEqual(configuration["reconciliation"], "partially_observable")
        self.assertEqual(configuration["sites"][0]["reconciliation"], "in_sync")
        self.assertEqual(configuration["sites"][0]["desired"]["target"], "TARGET-A")
        self.assertEqual(configuration["sites"][0]["actual"]["target"], "TARGET-A")
        self.assertEqual(
            configuration["sites"][1]["reconciliation"],
            "disabled_runtime_binding_unobservable",
        )

    def test_post_persists_desired_without_mutating_actual_runtime(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": True, "interface": "mock", "target": "TARGET-NEW"},
        )
        self.assertEqual(status, 200)
        site = payload["site_configuration"]["sites"][0]
        self.assertEqual(site["desired"]["target"], "TARGET-NEW")
        self.assertEqual(site["actual"]["target"], "TARGET-A")
        self.assertEqual(site["reconciliation"], "restart_required")
        self.assertEqual(payload["site_configuration"]["reconciliation"], "restart_required")
        self.assertEqual(
            SiteConfigurationController(self.path).current()["sites"][0]["target"],
            "TARGET-NEW",
        )

    def test_active_execution_rejects_write_before_persistence(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        self.handler.snapshot["ppu"]["execution"]["busy"] = True
        self.handler.snapshot["ppu"]["execution"]["active_job_count"] = 1
        self.handler.snapshot["sites"][0]["state"] = "program"
        self.handler.snapshot["sites"][0]["current_job_id"] = "job-active"

        status, payload = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": False, "interface": "mock", "target": "TARGET-A"},
        )
        self.assertEqual(status, 409)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_invalid_site_and_payload_fail_closed(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        status, _ = self.request(
            "POST",
            "/api/settings/sites/9",
            {"enabled": True, "interface": "mock", "target": "TARGET-X"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

        status, _ = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": True, "interface": "uart", "target": "TARGET-X"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()

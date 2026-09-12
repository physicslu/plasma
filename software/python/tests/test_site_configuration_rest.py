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

    def request(self, method: str, path: str, body=None, *, if_match: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        raw = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        if if_match is not None:
            headers["If-Match"] = if_match
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def revision(self, site_id: int) -> str:
        status, payload = self.request("GET", "/api/settings/sites")
        self.assertEqual(status, 200)
        site = next(item for item in payload["site_configuration"]["sites"] if item["site_id"] == site_id)
        return site["desired_revision"]

    @staticmethod
    def etag(revision: str) -> str:
        return f'"{revision}"'

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
        self.assertRegex(configuration["sites"][0]["desired_revision"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            configuration["sites"][1]["reconciliation"],
            "disabled_runtime_binding_unobservable",
        )

    def test_observed_runtime_topology_missing_desired_sites_requires_restart(self) -> None:
        self.handler.snapshot["sites"] = []

        status, payload = self.request("GET", "/api/settings/sites")

        self.assertEqual(status, 200)
        configuration = payload["site_configuration"]
        self.assertEqual(configuration["reconciliation"], "restart_required")
        self.assertEqual(len(configuration["sites"]), 2)
        for site in configuration["sites"]:
            self.assertIsNone(site["actual"])
            self.assertEqual(site["reconciliation"], "restart_required")

    def test_unobserved_runtime_topology_remains_actual_unavailable(self) -> None:
        self.handler.snapshot.pop("sites")

        status, payload = self.request("GET", "/api/settings/sites")

        self.assertEqual(status, 200)
        configuration = payload["site_configuration"]
        self.assertEqual(configuration["reconciliation"], "actual_unavailable")
        self.assertEqual(len(configuration["sites"]), 2)
        for site in configuration["sites"]:
            self.assertIsNone(site["actual"])
            self.assertEqual(site["reconciliation"], "actual_unavailable")

    def test_post_requires_strong_if_match_precondition(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        body = {"enabled": True, "interface": "mock", "target": "TARGET-NEW"}

        status, payload = self.request("POST", "/api/settings/sites/1", body)
        self.assertEqual(status, 428)
        self.assertEqual(payload["error"]["code"], "site_precondition_required")
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

        status, payload = self.request("POST", "/api/settings/sites/1", body, if_match="sha256:not-an-etag")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "invalid_site_precondition")
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_post_persists_desired_without_mutating_actual_runtime(self) -> None:
        previous_revision = self.revision(1)
        status, payload = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": True, "interface": "mock", "target": "TARGET-NEW"},
            if_match=self.etag(previous_revision),
        )
        self.assertEqual(status, 200)
        site = payload["site_configuration"]["sites"][0]
        self.assertEqual(site["desired"]["target"], "TARGET-NEW")
        self.assertEqual(site["actual"]["target"], "TARGET-A")
        self.assertEqual(site["reconciliation"], "restart_required")
        self.assertNotEqual(site["desired_revision"], previous_revision)
        self.assertEqual(payload["site_configuration"]["reconciliation"], "restart_required")
        self.assertEqual(
            SiteConfigurationController(self.path).current()["sites"][0]["target"],
            "TARGET-NEW",
        )

    def test_stale_if_match_returns_412_and_preserves_newer_desired_state(self) -> None:
        stale_revision = self.revision(1)
        status, first = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": True, "interface": "mock", "target": "TARGET-NEW"},
            if_match=self.etag(stale_revision),
        )
        self.assertEqual(status, 200)
        current_revision = first["site_configuration"]["sites"][0]["desired_revision"]
        before_conflict = self.path.read_text(encoding="utf-8")

        status, conflict = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": True, "interface": "mock", "target": "TARGET-STALE"},
            if_match=self.etag(stale_revision),
        )
        self.assertEqual(status, 412)
        self.assertEqual(conflict["error"]["code"], "site_desired_conflict")
        self.assertEqual(conflict["error"]["context"]["expected_revision"], stale_revision)
        self.assertEqual(conflict["error"]["context"]["current_revision"], current_revision)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before_conflict)

    def test_active_execution_rejects_write_before_persistence(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        revision = self.revision(1)
        self.handler.snapshot["ppu"]["execution"]["busy"] = True
        self.handler.snapshot["ppu"]["execution"]["active_job_count"] = 1
        self.handler.snapshot["sites"][0]["state"] = "program"
        self.handler.snapshot["sites"][0]["current_job_id"] = "job-active"

        status, payload = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": False, "interface": "mock", "target": "TARGET-A"},
            if_match=self.etag(revision),
        )
        self.assertEqual(status, 409)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_invalid_site_and_payload_fail_closed(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        revision = self.revision(1)
        status, _ = self.request(
            "POST",
            "/api/settings/sites/9",
            {"enabled": True, "interface": "mock", "target": "TARGET-X"},
            if_match=self.etag(revision),
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

        status, _ = self.request(
            "POST",
            "/api/settings/sites/1",
            {"enabled": True, "interface": "uart", "target": "TARGET-X"},
            if_match=self.etag(revision),
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()

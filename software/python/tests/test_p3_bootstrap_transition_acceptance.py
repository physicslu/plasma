from __future__ import annotations

import json
import tempfile
import textwrap
import threading
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_web.gateway_phase3 import Phase3PlasmaWebHandler
from plasma_web.site_configuration import SiteConfigurationController


CONFIG = """
ppu:
  id: ppu-rest-01
  facility_id: test-lab
  model: virtual
  display_name: P3 Bootstrap Acceptance PPU
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
  - {id: 1, enabled: false, interface: mock, target: STM32F103C8T6}
  - {id: 2, enabled: false, interface: mock, target: STM32F103C8T6}
  - {id: 3, enabled: false, interface: mock, target: STM32F103C8T6}
  - {id: 4, enabled: false, interface: mock, target: STM32F103C8T6}
  - {id: 5, enabled: false, interface: mock, target: STM32F103C8T6}
  - {id: 6, enabled: false, interface: mock, target: STM32F103C8T6}
  - {id: 7, enabled: false, interface: mock, target: STM32F103C8T6}
  - {id: 8, enabled: false, interface: mock, target: STM32F103C8T6}
"""


class TestP3BootstrapTransitionAcceptance:
    def setup_method(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config" / "ppu.yaml"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(textwrap.dedent(CONFIG).lstrip(), encoding="utf-8")

        runtime_snapshot = {
            "ok": True,
            "ppu": {
                "ppu_id": "ppu-rest-01",
                "facility_id": "test-lab",
                "execution": {"busy": False, "active_job_count": 0},
            },
            # This is the real bootstrap transition: the running pre-bootstrap
            # server successfully reports an observed but still-empty topology.
            "sites": [],
        }

        class Handler(Phase3PlasmaWebHandler):
            snapshot = deepcopy(runtime_snapshot)

            def _local_snapshot(self):
                return deepcopy(type(self).snapshot)

        Handler.site_configuration = SiteConfigurationController(self.path)
        Handler.allowed_origins = frozenset({"*"})
        Handler.configure_runtime_activation(Path(self.temp.name) / "runtime-activation.sock")
        self.handler = Handler
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def teardown_method(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path: str):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def test_observed_empty_runtime_topology_exposes_activation_required(self) -> None:
        status, sites_payload = self.request("/api/settings/sites")
        assert status == 200
        configuration = sites_payload["site_configuration"]
        assert configuration["runtime_apply_supported"] is True
        assert configuration["reconciliation"] == "restart_required"
        assert len(configuration["sites"]) == 8
        assert all(site["actual"] is None for site in configuration["sites"])
        assert all(site["reconciliation"] == "restart_required" for site in configuration["sites"])

        status, activation_payload = self.request("/api/settings/sites/activation")
        assert status == 200
        activation = activation_payload["runtime_activation"]
        assert activation["supported"] is True
        assert activation["state"] == "activation_required"
        assert activation["reconciliation"] == "restart_required"
        assert activation["ppu_id"] == "ppu-rest-01"
        assert activation["desired_runtime_revision"].startswith("sha256:")

    def test_post_restart_disabled_topology_is_partially_observable_not_unavailable(self) -> None:
        self.handler.snapshot["sites"] = [
            {
                "site_id": site_id,
                "enabled": False,
                "interface": None,
                "target": None,
                "state": "disabled",
                "current_job_id": None,
            }
            for site_id in range(1, 9)
        ]

        status, sites_payload = self.request("/api/settings/sites")
        assert status == 200
        configuration = sites_payload["site_configuration"]
        assert configuration["reconciliation"] == "partially_observable"
        assert all(
            site["reconciliation"] == "disabled_runtime_binding_unobservable"
            for site in configuration["sites"]
        )

        status, activation_payload = self.request("/api/settings/sites/activation")
        assert status == 200
        activation = activation_payload["runtime_activation"]
        assert activation["state"] == "partially_observable"
        assert activation["reconciliation"] == "partially_observable"

    def test_missing_runtime_topology_remains_fail_closed(self) -> None:
        self.handler.snapshot.pop("sites")

        status, sites_payload = self.request("/api/settings/sites")
        assert status == 200
        configuration = sites_payload["site_configuration"]
        assert configuration["reconciliation"] == "actual_unavailable"
        assert all(site["reconciliation"] == "actual_unavailable" for site in configuration["sites"])

        status, activation_payload = self.request("/api/settings/sites/activation")
        assert status == 200
        activation = activation_payload["runtime_activation"]
        assert activation["state"] == "actual_unavailable"
        assert activation["reconciliation"] == "actual_unavailable"

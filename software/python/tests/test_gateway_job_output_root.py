"""Job output downloads follow the Server's output root, not the Gateway's.

A Z2 installation runs the Gateway with ``--output-root .../gateway-output``
while the Plasma Server writes Job output under the ``server.output_root`` of
the PPU YAML. The download route must serve the Server's directory.
"""
from __future__ import annotations

import json
import tempfile
import textwrap
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web import gateway_phase2, gateway_phase3
from plasma_web.gateway_phase2 import Phase2PlasmaWebHandler

CONFIG = """
ppu:
  id: ppu-output-root-01
  facility_id: test-lab
  model: virtual
  display_name: Output Root Test PPU
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
"""

JOB = "job-20261111-044222-e26d4720"
NAME = "read_SITE2_flash.bin"


class GatewayJobOutputRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = root / "config" / "plasma.yaml"
        self.config.parent.mkdir()
        self.server_output = root / "server-output"
        self.config.write_text(
            textwrap.dedent(CONFIG).lstrip().replace(
                "output_root: output", f"output_root: {self.server_output}"),
            encoding="utf-8")
        self.gateway_output = root / "gateway-output"
        self.gateway_output.mkdir()

        class Handler(Phase2PlasmaWebHandler):
            output_root = self.gateway_output

        self.handler = Handler

    def _write_job(self, output_root: Path, data: bytes) -> None:
        job_dir = output_root / JOB
        job_dir.mkdir(parents=True)
        output = job_dir / NAME
        output.write_bytes(data)
        (job_dir / "result.json").write_text(json.dumps({"output_files": [str(output)]}))

    def _get(self) -> tuple[int, bytes]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_port)
            conn.request("GET", f"/api/jobs/{JOB}/files/{NAME}")
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_download_is_served_from_the_server_output_root(self) -> None:
        self.handler.configure_site_configuration(self.config)
        self.assertEqual(self.handler.job_output_root, self.server_output.resolve())
        self._write_job(self.server_output, b"\x01\x02\xff")
        status, body = self._get()
        self.assertEqual(status, 200)
        self.assertEqual(body, b"\x01\x02\xff")

    def test_gateway_output_root_is_not_a_job_output_source_once_configured(self) -> None:
        self.handler.configure_site_configuration(self.config)
        self._write_job(self.gateway_output, b"stale")
        status, _body = self._get()
        self.assertEqual(status, 400)

    def test_named_but_unreadable_ppu_config_is_an_error_not_a_fallback(self) -> None:
        missing = Path(self.temp.name) / "missing.yaml"
        with self.assertRaises(PlasmaError) as raised:
            self.handler.configure_site_configuration(missing)
        self.assertEqual(raised.exception.code, ErrorCode.CONFIG_INVALID)
        self.assertIn(str(missing), raised.exception.message)

    def test_gateway_started_without_ppu_config_keeps_the_shared_output_root(self) -> None:
        for module in (gateway_phase2, gateway_phase3):
            args = module._parser().parse_args([])
            self.assertFalse(getattr(args, "ppu_config_explicit", False))
        self.handler.configure_site_configuration(
            args.ppu_config, job_output_from_config=False)
        self.assertIsNone(self.handler.job_output_root)
        self._write_job(self.gateway_output, b"\x07")
        status, body = self._get()
        self.assertEqual(status, 200)
        self.assertEqual(body, b"\x07")

    def test_ppu_config_flag_is_recorded_as_explicit_by_both_entry_points(self) -> None:
        for module in (gateway_phase2, gateway_phase3):
            args = module._parser().parse_args(["--ppu-config", str(self.config)])
            self.assertIs(args.ppu_config_explicit, True)
            self.assertEqual(args.ppu_config, self.config)


if __name__ == "__main__":
    unittest.main()

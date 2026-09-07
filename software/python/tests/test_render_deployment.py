from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

from plasma_core.config import load_config
from plasma_web.engineering_targets import MOCK_FLASH_SIZE_BYTES, MockEngineeringPPUProvider
from plasma_web.gateway import PlasmaWebHandler


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class StaticGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.static_root = cls.root / "public"
        assets = cls.static_root / "assets"
        assets.mkdir(parents=True)
        (cls.static_root / "index.html").write_text("<html>Plasma public demo</html>")
        (assets / "app-1234.js").write_text("console.log('Plasma')")
        (cls.root / "private.txt").write_text("private")

        cls.handler = type("StaticPlasmaWebHandler", (PlasmaWebHandler,), {"static_root": cls.static_root})
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temporary.cleanup()

    def request(self, path: str) -> tuple[int, bytes, dict[str, str]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = response.read()
        headers = dict(response.getheaders())
        connection.close()
        return response.status, payload, headers

    def test_root_and_spa_routes_share_the_existing_gateway_origin(self) -> None:
        for path in ("/", "/demo", "/fleet", "/fleet/programming", "/engineering", "/devices", "/ppu"):
            with self.subTest(path=path):
                status, payload, headers = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(payload, b"<html>Plasma public demo</html>")
                self.assertTrue(headers["Content-Type"].startswith("text/html"))
                self.assertEqual(headers["Cache-Control"], "no-cache")

    def test_static_javascript_uses_content_type_and_immutable_cache(self) -> None:
        status, payload, headers = self.request("/assets/app-1234.js")
        self.assertEqual(status, 200)
        self.assertEqual(payload, b"console.log('Plasma')")
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(headers["Cache-Control"], "public, max-age=31536000, immutable")

    def test_unknown_api_routes_do_not_fall_back_to_the_spa(self) -> None:
        status, payload, headers = self.request("/api/missing")
        self.assertEqual(status, 404)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertFalse(json.loads(payload)["ok"])

    def test_missing_assets_do_not_fall_back_to_the_spa(self) -> None:
        status, payload, _ = self.request("/assets/missing.js")
        self.assertEqual(status, 404)
        self.assertFalse(json.loads(payload)["ok"])

    def test_static_files_reject_encoded_directory_traversal(self) -> None:
        status, payload, _ = self.request("/%2e%2e/private.txt")
        self.assertEqual(status, 404)
        self.assertFalse(json.loads(payload)["ok"])


class RenderDeploymentContractTests(unittest.TestCase):
    def _services(self) -> dict[str, dict[str, object]]:
        blueprint = yaml.safe_load((REPOSITORY_ROOT / "render.yaml").read_text())
        return {service["name"]: service for service in blueprint["services"]}

    def test_render_blueprint_preserves_public_demo_and_adds_control_station_lab(self) -> None:
        services = self._services()
        self.assertEqual(set(services), {"plasma-public-demo", "plasma-control-station-lab"})

        public_demo = services["plasma-public-demo"]
        self.assertEqual(public_demo["type"], "web")
        self.assertEqual(public_demo["runtime"], "python")
        self.assertEqual(public_demo["plan"], "free")
        self.assertEqual(public_demo["buildCommand"], "bash scripts/render-build.sh")
        self.assertEqual(public_demo["startCommand"], "bash scripts/render-start.sh")
        self.assertEqual(public_demo["healthCheckPath"], "/api/health/ready")
        public_environment = {item["key"]: str(item["value"]) for item in public_demo["envVars"]}
        self.assertEqual(public_environment["PLASMA_RENDER_ENGINEERING_MOCK"], "1")
        self.assertEqual(public_environment["PLASMA_RENDER_FLASH_BYTES"], str(1024 * 1024))

        control_station = services["plasma-control-station-lab"]
        self.assertEqual(control_station["type"], "web")
        self.assertEqual(control_station["runtime"], "python")
        self.assertEqual(control_station["plan"], "free")
        self.assertEqual(control_station["buildCommand"], "bash scripts/render-build.sh")
        self.assertEqual(control_station["startCommand"], "bash scripts/render-control-station-start.sh")
        self.assertEqual(control_station["healthCheckPath"], "/")
        control_environment = {item["key"]: item for item in control_station["envVars"]}
        self.assertEqual(control_environment["PLASMA_RENDER_PPU_ALIAS"]["value"], "swpc-ppu")
        self.assertIs(control_environment["PLASMA_RENDER_PPU_ENDPOINT"]["sync"], False)
        self.assertNotIn("value", control_environment["PLASMA_RENDER_PPU_ENDPOINT"])

    def test_control_station_lab_is_manager_only_and_requires_restricted_https_ppu_ingress(self) -> None:
        script = (REPOSITORY_ROOT / "scripts/render-control-station-start.sh").read_text(encoding="utf-8")
        self.assertIn("python -m plasma_manager.server", script)
        self.assertIn('PLASMA_CONTROL_STATION_MODE="managed"', script)
        self.assertIn('PLASMA_FLEET_UI_ENABLED="1"', script)
        self.assertIn('PLASMA_MANAGER_API_URL="http://127.0.0.1:', script)
        self.assertIn('parsed.scheme != "https"', script)
        self.assertIn("must identify the restricted ingress root", script)
        self.assertNotIn("python -m plasma_server.server", script)
        self.assertNotIn("-m plasma_web.gateway", script)
        self.assertNotIn("--engineering-mock", script)

    def test_render_build_produces_public_demo_and_control_station_payloads(self) -> None:
        script = (REPOSITORY_ROOT / "scripts/render-build.sh").read_text(encoding="utf-8")
        self.assertIn("npm run build:render", script)
        self.assertIn("npm run build:product", script)
        self.assertIn("dist/standalone/server.js", script)

    def test_render_mock_ppu_is_loopback_only_and_has_eight_sites(self) -> None:
        config = load_config(REPOSITORY_ROOT / "software/python/config/render-demo.yaml")
        self.assertEqual(config.server.host, "127.0.0.1")
        self.assertEqual(config.server.port, 9900)
        self.assertEqual(config.ppu.facility_id, "public-demo")
        self.assertEqual(config.enabled_site_count, 8)
        self.assertEqual(config.server.max_binary_bytes, 1024 * 1024)
        self.assertTrue(all(site.interface == "mock" for site in config.sites))
        self.assertTrue(all(site.mock["flash_size"] == 1024 * 1024 for site in config.sites))

    def test_engineering_mock_flash_capacity_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            provider = MockEngineeringPPUProvider(Path(root), flash_size_bytes=1024 * 1024)
            config = provider._config_for(provider._specs[0])
            self.assertTrue(all(site.mock["flash_size"] == 1024 * 1024 for site in config.sites))
            self.assertEqual(provider.catalog()["timing_profile"]["flash_size_bytes"], 1024 * 1024)

            default_provider = MockEngineeringPPUProvider(Path(root))
            self.assertEqual(default_provider.flash_size_bytes, MOCK_FLASH_SIZE_BYTES)

    def test_engineering_mock_rejects_invalid_flash_capacity(self) -> None:
        for value in (0, -1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MockEngineeringPPUProvider(Path("unused"), flash_size_bytes=value)


if __name__ == "__main__":
    unittest.main()

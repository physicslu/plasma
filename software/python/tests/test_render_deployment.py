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
        for path in ("/", "/demo", "/fleet", "/engineering", "/devices", "/ppu"):
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
    def test_render_blueprint_uses_one_free_python_web_service(self) -> None:
        blueprint = yaml.safe_load((REPOSITORY_ROOT / "render.yaml").read_text())
        self.assertEqual(len(blueprint["services"]), 1)
        service = blueprint["services"][0]
        self.assertEqual(service["type"], "web")
        self.assertEqual(service["runtime"], "python")
        self.assertEqual(service["plan"], "free")
        self.assertEqual(service["buildCommand"], "bash scripts/render-build.sh")
        self.assertEqual(service["startCommand"], "bash scripts/render-start.sh")
        self.assertEqual(service["healthCheckPath"], "/api/health/ready")
        environment = {item["key"]: str(item["value"]) for item in service["envVars"]}
        self.assertEqual(environment["PLASMA_RENDER_ENGINEERING_MOCK"], "1")
        self.assertEqual(environment["PLASMA_RENDER_FLASH_BYTES"], str(1024 * 1024))

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

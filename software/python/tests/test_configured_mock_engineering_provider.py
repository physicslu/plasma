from __future__ import annotations

import hashlib
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_web.configured_mock_provider import ConfiguredMockEngineeringPPUProvider
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[JobRequest] = []

    async def start(self, request: JobRequest) -> dict[str, object]:
        self.requests.append(request)
        return {"ok": True, "job": {"job_id": request.job_id, "state": "queued"}}


class ConfiguredMockEngineeringProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "ppu.yaml"
        self._write_config()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_config(self, *, site2_interface: str = "mock") -> None:
        output = self.root / "output"
        logs = self.root / "logs"
        sites = []
        for site_id in range(1, 9):
            enabled = "true" if site_id == 1 else "false"
            interface = site2_interface if site_id == 2 else "mock"
            mock = "\n    mock: {flash_size: 65536}" if site_id == 1 else ""
            sites.append(
                f"  - id: {site_id}\n"
                f"    enabled: {enabled}\n"
                f"    interface: {interface}\n"
                f"    target: STM32F103C8T6{mock}"
            )
        self.config.write_text(
            textwrap.dedent(
                f"""
                ppu:
                  id: swpc-z2like-01
                  facility_id: lab
                  model: SWPC-Z2-SURROGATE
                  display_name: SWPC Z2-like PS-only PPU
                server:
                  host: 127.0.0.1
                  port: 9900
                  max_supported_sites: 8
                  max_concurrent_jobs: 1
                  max_queue_depth_per_site: 16
                  output_root: {output}
                  log_root: {logs}
                sites:
                """
            ).lstrip()
            + "\n".join(sites)
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _activate_without_server(provider: ConfiguredMockEngineeringPPUProvider) -> tuple[str, str]:
        key = ("lab", "swpc-z2like-01")
        provider._ports[key] = 9900
        provider._output_roots[key] = provider._initial_config.server.output_root.resolve()
        return key

    def test_catalog_is_exactly_one_configured_ppu_and_eight_sites(self) -> None:
        provider = ConfiguredMockEngineeringPPUProvider(self.config)
        catalog = provider.catalog()

        self.assertEqual(catalog["provider"], "configured_mock")
        self.assertEqual(catalog["facility_count"], 1)
        self.assertEqual(catalog["ppu_count"], 1)
        self.assertEqual(catalog["site_count"], 8)
        self.assertEqual(catalog["facilities"][0]["facility_id"], "lab")
        ppu = catalog["facilities"][0]["ppus"][0]
        self.assertEqual(ppu["ppu_id"], "swpc-z2like-01")
        self.assertEqual(ppu["site_count"], 8)
        self.assertEqual(ppu["provider"], "configured_mock")
        self.assertEqual(catalog["timing_profile"]["site_flash_size_bytes"]["1"], 65536)
        self.assertEqual(catalog["timing_profile"]["site_flash_size_bytes"]["2"], 256 * 1024)
        self.assertNotIsInstance(provider, SharedImageMockEngineeringPPUProvider)

    def test_constructor_refuses_any_non_mock_site(self) -> None:
        self._write_config(site2_interface="openocd")
        with self.assertRaises(PlasmaError) as caught:
            ConfiguredMockEngineeringPPUProvider(self.config)
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
        self.assertEqual(caught.exception.context["site_ids"], [2])

    async def test_program_sends_uploaded_image_bytes_to_existing_server(self) -> None:
        provider = ConfiguredMockEngineeringPPUProvider(self.config)
        self._activate_without_server(provider)
        session_id = provider.begin_session()["session"]["session_id"]
        image = b"configured-z2like-image"
        sha256 = hashlib.sha256(image).hexdigest()
        provider.cache_asset(
            session_id,
            "lab",
            "swpc-z2like-01",
            "image.bin",
            "image",
            "binary",
            sha256,
            image,
        )
        client = _FakeClient()
        request = JobRequest(
            site_id=1,
            operation=Operation.PROGRAM,
            job_id="job-configured-program",
            target="STM32F103C8T6",
        )

        with patch.object(provider, "_client", return_value=client):
            accepted = await provider.start_job(
                "lab",
                "swpc-z2like-01",
                request,
                session_id=session_id,
                asset_sha256=sha256,
            )

        self.assertTrue(accepted["ok"])
        self.assertEqual(len(client.requests), 1)
        submitted = client.requests[0]
        self.assertEqual(submitted.image, image)
        self.assertIsNone(submitted.image_ref)
        self.assertEqual(submitted.metadata["source_asset_sha256"], sha256)
        self.assertEqual(submitted.metadata["source_asset_origin"], "user")
        self.assertEqual(submitted.timeout_s, 30.0)

    async def test_read_uses_configured_site_main_flash_geometry(self) -> None:
        provider = ConfiguredMockEngineeringPPUProvider(self.config)
        self._activate_without_server(provider)
        client = _FakeClient()
        request = JobRequest(
            site_id=1,
            operation=Operation.READ,
            job_id="job-configured-read",
            target="STM32F103C8T6",
        )

        with patch.object(provider, "_client", return_value=client):
            await provider.start_job("lab", "swpc-z2like-01", request)

        submitted = client.requests[0]
        self.assertEqual(submitted.map_data["scope"], "main_flash")
        self.assertEqual(
            submitted.map_data["sections"],
            [{"name": "main_flash", "address": 0, "length": 65536}],
        )
        self.assertEqual(submitted.metadata["read_size_bytes"], 65536)


if __name__ == "__main__":
    unittest.main()

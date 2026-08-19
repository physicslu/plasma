from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from plasma_core.config import PPUConfig, PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import JobState, Operation
from plasma_core.models import JobRequest
from plasma_server.site_manager import SiteManager


class PPUStatusTests(unittest.TestCase):
    def test_v32_status_exposes_ppu_identity_and_one_based_sites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = PlasmaConfig(
                server=ServerConfig(
                    max_supported_sites=8,
                    max_concurrent_jobs=1,
                    output_root=root / "output",
                    log_root=root / "logs",
                ),
                sites=[SiteConfig(id=1), SiteConfig(id=2), SiteConfig(id=3)],
                ppu=PPUConfig(
                    id="ppu-42",
                    facility_id="factory-a",
                    model="Plasma-4Site",
                    display_name="Line A PPU",
                ),
            )

            status = SiteManager(config).status()

            self.assertEqual(
                status["ppu"],
                {
                    "ppu_id": "ppu-42",
                    "facility_id": "factory-a",
                    "model": "Plasma-4Site",
                    "display_name": "Line A PPU",
                    "site_count": 3,
                    "enabled_site_count": 0,
                    "capabilities": {
                        "max_supported_sites": 8,
                        "operations": ["erase", "program", "verify", "read"],
                    },
                },
            )
            self.assertEqual([item["site_id"] for item in status["sites"]], [1, 2, 3])
            self.assertTrue(all(item["latest_job"] is None for item in status["sites"]))
            self.assertNotIn("programmer", status)
            self.assertNotIn("channels", status)

    def test_v32_status_exposes_safe_latest_job_summary_without_result_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = SiteManager(
                PlasmaConfig(
                    server=ServerConfig(
                        max_supported_sites=1,
                        max_concurrent_jobs=1,
                        output_root=root / "output",
                        log_root=root / "logs",
                    ),
                    sites=[SiteConfig(id=1, enabled=True, interface="mock")],
                    ppu=PPUConfig(id="ppu-job", facility_id="factory-a"),
                )
            )

            async def create_runtime():
                return manager.registry.create(
                    JobRequest(
                        site_id=1,
                        operation=Operation.VERIFY,
                        job_id="verify-job-1",
                        firmware=b"secret-firmware-bytes",
                        metadata={"private": "do-not-expose"},
                    )
                )

            runtime = asyncio.run(create_runtime())
            runtime.state = JobState.SUCCESS
            runtime.stage = "verify"
            runtime.stage_state = "complete"
            runtime.progress_percent = 100.0

            latest = manager.status()["sites"][0]["latest_job"]

            self.assertEqual(latest["job_id"], "verify-job-1")
            self.assertEqual(latest["operation"], "verify")
            self.assertEqual(latest["state"], "success")
            self.assertEqual(latest["stage"], "verify")
            self.assertEqual(latest["progress_percent"], 100.0)
            self.assertNotIn("result", latest)
            self.assertNotIn("firmware", latest)
            self.assertNotIn("metadata", latest)
            self.assertNotIn("output_files", latest)

    def test_v31_status_retains_zero_based_channel_shape(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_sites=2, max_concurrent_jobs=1),
            sites=[SiteConfig(id=1), SiteConfig(id=2)],
            ppu=PPUConfig(id="ppu-legacy", facility_id="facility-1"),
        )

        status = SiteManager(config).status(channel_id=0, protocol_version="3.1")

        self.assertEqual(status["programmer"]["programmer_id"], "ppu-legacy")
        self.assertEqual(status["programmer"]["site_id"], "facility-1")
        self.assertEqual(status["channels"][0]["channel_id"], 0)
        self.assertIn("latest_job", status["channels"][0])
        self.assertNotIn("ppu", status)
        self.assertNotIn("sites", status)


if __name__ == "__main__":
    unittest.main()

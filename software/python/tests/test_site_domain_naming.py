from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plasma_core.config import PPUConfig, PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation, SiteState
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.job_logging import JobEventLogger, OutputManager
from plasma_core.models import JobRequest
from plasma_server import SiteManager, SiteWorker
from plasma_server.channel_manager import ChannelManager
from plasma_server.channel_worker import ChannelWorker
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager as ModuleSiteManager
from plasma_server.site_worker import SiteWorker as ModuleSiteWorker


class SiteDomainNamingTests(unittest.TestCase):
    def test_server_config_uses_site_fields_canonically(self) -> None:
        config = ServerConfig(max_supported_sites=4, max_queue_depth_per_site=7)
        self.assertEqual(config.max_supported_sites, 4)
        self.assertEqual(config.max_queue_depth_per_site, 7)
        self.assertEqual(config.max_supported_channels, 4)
        self.assertEqual(config.max_queue_depth_per_channel, 7)

    def test_legacy_server_config_keywords_remain_compatible(self) -> None:
        config = ServerConfig(max_supported_channels=4, max_queue_depth_per_channel=7)
        self.assertEqual(config.max_supported_sites, 4)
        self.assertEqual(config.max_queue_depth_per_site, 7)
        with self.assertRaises(TypeError):
            ServerConfig(max_supported_sites=4, max_supported_channels=4)
        with self.assertRaises(TypeError):
            ServerConfig(max_queue_depth_per_site=7, max_queue_depth_per_channel=7)

    def test_site_manager_and_worker_are_canonical_exports(self) -> None:
        self.assertIs(SiteManager, ModuleSiteManager)
        self.assertIs(ChannelManager, SiteManager)
        self.assertIs(SiteWorker, ModuleSiteWorker)
        self.assertIs(ChannelWorker, SiteWorker)

    def test_site_error_symbols_keep_v31_wire_identity(self) -> None:
        self.assertIs(ErrorCode.SITE_INVALID, ErrorCode.CHANNEL_INVALID)
        self.assertIs(ErrorCode.SITE_DISABLED, ErrorCode.CHANNEL_DISABLED)
        self.assertIs(ErrorCode.SITE_BUSY, ErrorCode.CHANNEL_BUSY)
        error = PlasmaError(ErrorCode.SITE_INVALID, "missing site")
        self.assertEqual(error.code.value, "E4001")
        self.assertEqual(error.error_type, "CHANNEL_INVALID")

    def test_job_request_exposes_site_but_serializes_v31_channel_id(self) -> None:
        request = JobRequest(channel_id=3, operation=Operation.ERASE)
        metadata = request.protocol_metadata()
        self.assertEqual(request.site_id, 3)
        self.assertEqual(metadata["channel_id"], 3)
        self.assertNotIn("site_id", metadata)

    def test_site_audit_paths_and_readback_names_are_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logger = JobEventLogger(root / "logs", 2, "site-audit")
            logger.event("test_event")

            self.assertEqual(logger.text_path.parent.name, "SITE2")
            record = json.loads(logger.jsonl_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["site_id"], 2)
            self.assertEqual(record["channel_id"], 2)
            self.assertTrue(logger.legacy_jsonl_path.is_file())
            self.assertEqual(logger.legacy_jsonl_path.parent.name, "CH2")

            output = OutputManager(root / "output")
            paths = output.write_read_sections("site-readback", 2, {"flash": b"abc"})
            self.assertEqual([path.name for path in paths], ["read_SITE2_flash.bin"])
            self.assertEqual(paths[0].read_bytes(), b"abc")

    def test_plasma_server_defaults_to_site_manager(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = PlasmaConfig(
                server=ServerConfig(
                    port=0,
                    max_supported_sites=1,
                    max_concurrent_jobs=1,
                    max_queue_depth_per_site=1,
                    output_root=root / "output",
                    log_root=root / "logs",
                ),
                ppu=PPUConfig(id="ppu-test", facility_id="facility-test"),
                sites=[SiteConfig(id=0, enabled=False)],
            )
            server = PlasmaServer(config)
            self.assertIsInstance(server.manager, SiteManager)
            self.assertEqual(SiteState.IDLE.value, "idle")


if __name__ == "__main__":
    unittest.main()

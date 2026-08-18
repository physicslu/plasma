from __future__ import annotations

import unittest
from pathlib import Path


class SiteModuleLayoutTests(unittest.TestCase):
    def test_canonical_site_modules_own_implementation(self) -> None:
        server_dir = Path(__file__).parents[1] / "plasma_server"
        site_manager = (server_dir / "site_manager.py").read_text(encoding="utf-8")
        site_worker = (server_dir / "site_worker.py").read_text(encoding="utf-8")
        channel_manager = (server_dir / "channel_manager.py").read_text(encoding="utf-8")
        channel_worker = (server_dir / "channel_worker.py").read_text(encoding="utf-8")

        self.assertIn("class SiteManager", site_manager)
        self.assertIn("class SiteWorker", site_worker)
        self.assertNotIn("class SiteManager", channel_manager)
        self.assertNotIn("class SiteWorker", channel_worker)
        self.assertIn("compatibility", channel_manager.lower())
        self.assertIn("compatibility", channel_worker.lower())


if __name__ == "__main__":
    unittest.main()

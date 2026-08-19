from __future__ import annotations

import unittest

from plasma_manager.config import ManagerConfig, PPURegistryEntry


class ManagerConfigCompatibilityTests(unittest.TestCase):
    def test_existing_positional_ppus_argument_keeps_its_position(self):
        ppus = (PPURegistryEntry(endpoint="http://ppu-a"),)
        config = ManagerConfig("127.0.0.1", 18180, 2.0, 2.0, ppus)
        self.assertEqual(config.ppus, ppus)
        self.assertIsNone(config.observation_db_path)


if __name__ == "__main__":
    unittest.main()

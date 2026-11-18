"""Gate 1 regression: deployment journal integrity for Bundle v3 B3/B4.

Host-only: no service, device, FPGA, or DUT access.
"""
from __future__ import annotations

import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "scripts" / "ppu-bootstrap-deployment.py"


def load_engine():
    import sys
    spec = importlib.util.spec_from_file_location("ppu_b3_b4_journal_gate1", ENGINE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BundleV3JournalSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()

    def test_journal_round_trip_is_private_and_durable(self):
        with tempfile.TemporaryDirectory() as root:
            journal = self.engine.Journal(Path(root) / "deployment.json", clock=lambda: 100.0)
            record = self.engine.DeploymentRecord(
                schema_version=self.engine.SCHEMA_VERSION,
                transaction_id="b3-b4-host-only",
                state="received",
                sequence=0,
                started_at_epoch_s=100.0,
                updated_at_epoch_s=100.0,
                release_artifact="fixture.bundle.zip",
            )
            journal.write(record, "staging")
            self.assertEqual(journal.read().state, "staging")
            self.assertEqual(journal.read().sequence, 1)
            self.assertEqual(stat.S_IMODE(journal.path.stat().st_mode), 0o600)
            self.assertFalse(journal.path.with_name("deployment.json.new").exists())

    def test_corrupt_journal_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "deployment.json"
            path.write_text("{broken", encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaises(self.engine.DeploymentError):
                self.engine.Journal(path).read()

    def test_world_readable_journal_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "deployment.json"
            path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(self.engine.DeploymentError):
                self.engine.Journal(path).read()


if __name__ == "__main__":
    unittest.main()

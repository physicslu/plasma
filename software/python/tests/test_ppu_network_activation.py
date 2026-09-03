from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from plasma_web.ppu_network_activation import (
    PPUNetworkActivationController,
    PPUNetworkActivationError,
)
from plasma_web.ppu_network_settings import PPUNetworkSettingsController


STATIC_21 = {
    "mode": "static",
    "address": "192.168.77.21",
    "prefix_length": 24,
    "gateway": "192.168.77.1",
    "dns_servers": ["192.168.77.1"],
}
STATIC_22 = {
    "mode": "static",
    "address": "192.168.77.22",
    "prefix_length": 24,
    "gateway": "192.168.77.1",
    "dns_servers": ["192.168.77.1"],
}


class FakeHelper:
    def __init__(self) -> None:
        self.current = {"interface": "eth0", "address": "192.168.77.10", "prefix_length": 24}
        self.applies: list[dict[str, object]] = []
        self.restores: list[dict[str, object]] = []
        self.apply_started = threading.Event()
        self.apply_release = threading.Event()
        self.block_apply = False

    def snapshot(self):
        return dict(self.current)

    def apply(self, settings):
        self.apply_started.set()
        if self.block_apply:
            self.apply_release.wait(timeout=3)
        self.applies.append(dict(settings))
        self.current = {
            "interface": "eth0",
            "address": settings["address"],
            "prefix_length": settings["prefix_length"],
        }
        return dict(self.current)

    def restore(self, snapshot):
        self.restores.append(dict(snapshot))
        self.current = dict(snapshot)
        return dict(self.current)


class PPUNetworkActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = PPUNetworkSettingsController(self.root / "settings.yaml")
        self.helper = FakeHelper()
        self.ppu_id = "ppu-phase2-test"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def controller(self, *, apply_delay_s: float = 0.01):
        return PPUNetworkActivationController(
            self.settings,
            self.helper,
            self.root / "activation.json",
            lambda: self.ppu_id,
            apply_delay_s=apply_delay_s,
        )

    def write_static(self, body=STATIC_21) -> int:
        return int(self.settings.update(dict(body))["revision"])

    @staticmethod
    def wait_state(controller: PPUNetworkActivationController, state: str, timeout: float = 3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = controller.status()
            if status["state"] == state:
                return status
            time.sleep(0.01)
        raise AssertionError(f"activation did not reach {state}: {controller.status()}")

    def request(self, revision: int, *, timeout: int = 2):
        return {
            "action": "apply",
            "expected_revision": revision,
            "expected_ppu_id": self.ppu_id,
            "rollback_timeout_s": timeout,
        }

    def test_unconfigured_helper_preserves_phase1_not_implemented_boundary(self) -> None:
        controller = PPUNetworkActivationController(self.settings, None, None, lambda: self.ppu_id)
        self.assertEqual(controller.status(), {"supported": False, "state": "not_implemented"})
        with self.assertRaises(PPUNetworkActivationError) as caught:
            controller.schedule(self.request(1))
        self.assertEqual(caught.exception.http_status, 503)

    def test_apply_waits_for_explicit_commit_and_records_committed_revision(self) -> None:
        revision = self.write_static()
        controller = self.controller()
        scheduled = controller.schedule(self.request(revision))
        activation_id = scheduled["activation_id"]
        waiting = self.wait_state(controller, "applied_waiting_commit")
        self.assertEqual(self.helper.current["address"], STATIC_21["address"])
        self.assertIsNotNone(waiting["deadline_epoch_s"])

        committed = controller.commit(
            activation_id,
            {"expected_revision": revision, "expected_ppu_id": self.ppu_id},
        )
        self.assertEqual(committed["state"], "committed")
        self.assertEqual(committed["committed_revision"], revision)
        time.sleep(2.1)
        self.assertEqual(self.helper.current["address"], STATIC_21["address"])
        self.assertEqual(controller.status()["state"], "committed")
        controller.close()

    def test_missing_commit_automatically_restores_previous_network(self) -> None:
        revision = self.write_static()
        controller = self.controller()
        controller.schedule(self.request(revision, timeout=2))
        self.wait_state(controller, "applied_waiting_commit")
        self.assertEqual(self.helper.current["address"], STATIC_21["address"])
        rolled_back = self.wait_state(controller, "rolled_back", timeout=3.5)
        self.assertEqual(rolled_back["reason"], "commit_deadline_expired")
        self.assertEqual(self.helper.current["address"], "192.168.77.10")
        self.assertEqual(len(self.helper.restores), 1)
        controller.close()

    def test_stale_revision_and_wrong_identity_fail_before_helper_mutation(self) -> None:
        revision = self.write_static()
        controller = self.controller()
        with self.assertRaises(PPUNetworkActivationError) as stale:
            controller.schedule(self.request(revision - 1))
        self.assertEqual(stale.exception.http_status, 409)
        self.assertFalse(self.helper.applies)

        wrong = self.request(revision)
        wrong["expected_ppu_id"] = "wrong-ppu"
        with self.assertRaises(PPUNetworkActivationError) as identity:
            controller.schedule(wrong)
        self.assertEqual(identity.exception.http_status, 409)
        self.assertFalse(self.helper.applies)
        controller.close()

    def test_only_one_activation_can_be_active(self) -> None:
        revision = self.write_static()
        controller = self.controller(apply_delay_s=0.5)
        controller.schedule(self.request(revision))
        with self.assertRaises(PPUNetworkActivationError) as caught:
            controller.schedule(self.request(revision))
        self.assertEqual(caught.exception.http_status, 409)
        controller.close()
        self.assertEqual(self.helper.current["address"], "192.168.77.10")

    def test_startup_recovery_restores_uncommitted_journal(self) -> None:
        revision = self.write_static()
        controller = self.controller()
        controller.schedule(self.request(revision))
        self.wait_state(controller, "applied_waiting_commit")
        self.assertEqual(self.helper.current["address"], STATIC_21["address"])

        journal = json.loads((self.root / "activation.json").read_text(encoding="utf-8"))
        self.assertEqual(journal["transaction"]["state"], "applied_waiting_commit")
        # Simulate process death: do not call close on the old controller. The new
        # process must fail safe from the persisted uncommitted transaction.
        replacement = PPUNetworkActivationController(
            self.settings,
            self.helper,
            self.root / "activation.json",
            lambda: self.ppu_id,
            apply_delay_s=0.01,
        )
        status = replacement.status()
        self.assertEqual(status["state"], "rolled_back")
        self.assertEqual(status["reason"], "startup_recovery")
        self.assertEqual(self.helper.current["address"], "192.168.77.10")
        # Stop the abandoned worker after recovery to avoid a late timeout restore.
        controller._commit_event.set()
        replacement.close()

    def test_shutdown_during_blocked_apply_finishes_fail_safe(self) -> None:
        revision = self.write_static()
        self.helper.block_apply = True
        controller = self.controller(apply_delay_s=0.0)
        controller.schedule(self.request(revision))
        self.assertTrue(self.helper.apply_started.wait(timeout=1))

        closer = threading.Thread(target=controller.close)
        closer.start()
        time.sleep(0.05)
        self.helper.apply_release.set()
        closer.join(timeout=3)
        self.assertFalse(closer.is_alive())
        self.assertEqual(self.helper.current["address"], "192.168.77.10")
        self.assertIn(controller.status()["state"], {"rolled_back", "recovery_required"})

    def test_committed_revision_survives_next_uncommitted_revision_rollback(self) -> None:
        revision2 = self.write_static(STATIC_21)
        controller = self.controller()
        first = controller.schedule(self.request(revision2))
        self.wait_state(controller, "applied_waiting_commit")
        controller.commit(first["activation_id"], {"expected_revision": revision2, "expected_ppu_id": self.ppu_id})
        self.assertEqual(self.helper.current["address"], STATIC_21["address"])

        revision3 = self.write_static(STATIC_22)
        controller.schedule(self.request(revision3, timeout=2))
        self.wait_state(controller, "applied_waiting_commit")
        self.assertEqual(self.helper.current["address"], STATIC_22["address"])
        rolled_back = self.wait_state(controller, "rolled_back", timeout=3.5)
        self.assertEqual(rolled_back["committed_revision"], revision2)
        self.assertEqual(self.settings.current()["revision"], revision3)
        self.assertEqual(self.helper.current["address"], STATIC_21["address"])
        controller.close()


if __name__ == "__main__":
    unittest.main()

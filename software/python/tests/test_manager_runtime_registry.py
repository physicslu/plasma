from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_manager.config import ManagerConfig, ManagerConfigError, PPURegistryEntry, load_manager_config
from plasma_manager.fleet import FleetAggregator
from plasma_manager.registry import (
    REGISTRY_LIFECYCLE_COMMISSIONED,
    REGISTRY_LIFECYCLE_DISABLED,
    REGISTRY_LIFECYCLE_PENDING,
    PPURegistryStore,
    RegistryMutationDisabled,
)
from plasma_manager.server import PlasmaManagerHandler


class FakePoller:
    def __init__(self) -> None:
        self.payload = {"ok": True, "ppus": []}

    def snapshot(self):
        return self.payload


class RuntimeRegistryStoreTests(unittest.TestCase):
    def test_config_only_registry_is_read_only(self):
        store = PPURegistryStore((PPURegistryEntry(endpoint="http://ppu-a", alias="ppu-a"),), None)
        self.assertFalse(store.mutable)
        self.assertEqual(store.records()[0].lifecycle, REGISTRY_LIFECYCLE_COMMISSIONED)
        with self.assertRaises(RegistryMutationDisabled):
            store.add(alias="ppu-b", endpoint="http://ppu-b")

    def test_mutable_registry_persists_add_lifecycle_and_remove(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "registry.json"
            seed = (PPURegistryEntry(endpoint="http://ppu-a", alias="ppu-a"),)
            times = iter(
                [
                    "2026-09-02T05:00:00+00:00",
                    "2026-09-02T05:01:00+00:00",
                    "2026-09-02T05:02:00+00:00",
                ]
            )
            store = PPURegistryStore(seed, state_path, clock=lambda: next(times))
            added = store.add(alias="ppu-b", endpoint="http://ppu-b/")
            self.assertEqual(added.lifecycle, REGISTRY_LIFECYCLE_PENDING)
            commissioned = store.set_lifecycle("ppu-b", REGISTRY_LIFECYCLE_COMMISSIONED)
            self.assertEqual(commissioned.lifecycle, REGISTRY_LIFECYCLE_COMMISSIONED)

            restored = PPURegistryStore(seed, state_path)
            self.assertEqual([record.alias for record in restored.records()], ["ppu-a", "ppu-b"])
            restored_b = restored.record_by_alias("ppu-b")
            self.assertIsNotNone(restored_b)
            assert restored_b is not None
            self.assertEqual(restored_b.lifecycle, REGISTRY_LIFECYCLE_COMMISSIONED)

            removed = restored.remove("ppu-b")
            self.assertEqual(removed.alias, "ppu-b")
            restored_again = PPURegistryStore(seed, state_path)
            self.assertEqual([record.alias for record in restored_again.records()], ["ppu-a"])

    def test_manager_config_accepts_absolute_registry_state_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "runtime-registry.json"
            config_path = root / "manager.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "manager:",
                        f"  registry_state_path: {state_path}",
                        "ppus: []",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_manager_config(config_path)
            self.assertEqual(config.registry_state_path, state_path)

    def test_manager_config_rejects_relative_registry_state_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "manager.yaml"
            config_path.write_text(
                "manager:\n  registry_state_path: relative-registry.json\nppus: []\n",
                encoding="utf-8",
            )
            with self.assertRaises(ManagerConfigError):
                load_manager_config(config_path)


class RuntimeRegistryHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.state_path = Path(cls.temporary.name) / "registry.json"
        cls.config = ManagerConfig(
            ppus=(PPURegistryEntry(endpoint="http://ppu-a", alias="ppu-a"),),
            registry_state_path=cls.state_path,
        )
        cls.registry = PPURegistryStore(cls.config.ppus, cls.config.registry_state_path)
        cls.poller = FakePoller()
        cls.aggregator = FleetAggregator(cls.config, registry_provider=cls.registry.entries)

        cls.previous = (
            PlasmaManagerHandler.config,
            PlasmaManagerHandler.registry_store,
            PlasmaManagerHandler.poller,
            PlasmaManagerHandler.aggregator,
        )
        PlasmaManagerHandler.config = cls.config
        PlasmaManagerHandler.registry_store = cls.registry
        PlasmaManagerHandler.poller = cls.poller
        PlasmaManagerHandler.aggregator = cls.aggregator
        cls.addClassCleanup(cls._restore_handler_state)

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaManagerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        # Cleanups run LIFO: shutdown -> join -> close -> restore handler -> temp dir.
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.thread.join, 2.0)
        cls.addClassCleanup(cls.server.shutdown)

    @classmethod
    def _restore_handler_state(cls):
        (
            PlasmaManagerHandler.config,
            PlasmaManagerHandler.registry_store,
            PlasmaManagerHandler.poller,
            PlasmaManagerHandler.aggregator,
        ) = cls.previous

    def request(self, method: str, path: str, body=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        decoded = json.loads(raw) if raw else None
        return response.status, decoded

    def setUp(self):
        if self.registry.record_by_alias("ppu-b") is not None:
            self.poller.payload = {"ok": True, "ppus": []}
            self.registry.remove("ppu-b")
        self.poller.payload = {"ok": True, "ppus": []}

    def test_add_requires_validation_before_enable(self):
        status, payload = self.request(
            "POST",
            "/api/registry",
            {"alias": "ppu-b", "endpoint": "http://ppu-b"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["entry"]["lifecycle"], REGISTRY_LIFECYCLE_PENDING)

        status, payload = self.request(
            "PATCH",
            "/api/registry/ppu-b",
            {"lifecycle": REGISTRY_LIFECYCLE_COMMISSIONED},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_validation_incomplete")

        self.poller.payload = {
            "ok": True,
            "ppus": [
                {
                    "alias": "ppu-b",
                    "gateway_live": True,
                    "execution_ready": True,
                    "contract_compatible": True,
                    "identity_conflict": False,
                    "errors": [],
                    "ppu": {"ppu_id": "PPU-B"},
                    "sites": [{"site_id": 1, "state": "idle", "current_job_id": None}],
                    "observation": {"state": "current"},
                }
            ],
        }
        status, payload = self.request(
            "PATCH",
            "/api/registry/ppu-b",
            {"lifecycle": REGISTRY_LIFECYCLE_COMMISSIONED},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["entry"]["lifecycle"], REGISTRY_LIFECYCLE_COMMISSIONED)

    def test_active_job_blocks_disable_and_remove(self):
        self.registry.add(alias="ppu-b", endpoint="http://ppu-b")
        self.poller.payload = {
            "ok": True,
            "ppus": [
                {
                    "alias": "ppu-b",
                    "gateway_live": True,
                    "execution_ready": True,
                    "contract_compatible": True,
                    "identity_conflict": False,
                    "errors": [],
                    "ppu": {"ppu_id": "PPU-B"},
                    "sites": [{"site_id": 1, "state": "running", "current_job_id": "job-1"}],
                    "observation": {"state": "current"},
                }
            ],
        }

        status, payload = self.request(
            "PATCH",
            "/api/registry/ppu-b",
            {"lifecycle": REGISTRY_LIFECYCLE_DISABLED},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_busy")

        status, payload = self.request("DELETE", "/api/registry/ppu-b")
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "ppu_busy")

        self.poller.payload["ppus"][0]["sites"][0] = {"site_id": 1, "state": "idle", "current_job_id": None}
        status, payload = self.request("DELETE", "/api/registry/ppu-b")
        self.assertEqual(status, 200)
        self.assertEqual(payload["removed"]["alias"], "ppu-b")


if __name__ == "__main__":
    unittest.main()

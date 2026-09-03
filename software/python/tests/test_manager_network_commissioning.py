from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from plasma_manager.config import PPURegistryEntry
from plasma_manager.network_commissioning import (
    NetworkCommissioningCoordinator,
    NetworkCommissioningError,
    NetworkCommissioningRecord,
    NetworkCommissioningStore,
)
from plasma_manager.registry import PPURegistryStore, RegistryConflictError
from plasma_manager.client import PPUTransportError


class FakePPU:
    def __init__(self) -> None:
        self.ppu_id = "ppu-static-1"
        self.old_endpoint = "http://192.168.77.10:18080"
        self.candidate_endpoint = "http://192.168.77.21:18080"
        self.revision = 1
        self.activation_id = "activation-1"
        self.activation_state = "idle"
        self.candidate_identity = self.ppu_id
        self.commit_calls = 0

    def client(self, endpoint: str, timeout_s: float):
        owner = self

        class Client:
            def node(self, *, headers=None):
                if endpoint == owner.old_endpoint and owner.activation_state in {"applying", "applied_waiting_commit"}:
                    raise PPUTransportError("old endpoint unavailable")
                if endpoint == owner.candidate_endpoint and owner.activation_state not in {"applying", "applied_waiting_commit", "committed"}:
                    raise PPUTransportError("candidate endpoint unavailable")
                identity = owner.candidate_identity if endpoint == owner.candidate_endpoint else owner.ppu_id
                return 200, {"ok": True, "ppu": {"ppu_id": identity}}

            def update_ppu_network_settings(self, body, *, headers=None):
                owner.revision += 1
                return 200, {
                    "ok": True,
                    "ppu_network_settings": {**body, "revision": owner.revision, "interface": "eth0"},
                }

            def start_network_activation(self, body, *, headers=None):
                owner.activation_state = "applied_waiting_commit"
                return 202, {
                    "ok": True,
                    "activation": {
                        "state": "scheduled",
                        "activation_id": owner.activation_id,
                        "deadline_epoch_s": 100.0,
                    },
                }

            def commit_network_activation(self, activation_id, body, *, headers=None):
                owner.commit_calls += 1
                owner.activation_state = "committed"
                return 200, {"ok": True, "activation": {"state": "committed", "activation_id": activation_id}}

            def network_activation(self, *, headers=None):
                return 200, {"ok": True, "activation": {"state": owner.activation_state}}

        return Client()


class ManagerNetworkCommissioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = PPURegistryStore(
            (PPURegistryEntry(endpoint="http://192.168.77.10:18080", alias="ppu-a"),),
            self.root / "registry.json",
        )
        self.store = NetworkCommissioningStore(self.root / "commissioning.json")
        self.fake = FakePPU()
        self.wall = 10.0
        self.coordinator = NetworkCommissioningCoordinator(
            self.registry,
            self.store,
            1.0,
            client_factory=self.fake.client,
            sleeper=lambda _: None,
            wall_time=lambda: self.wall,
        )
        self.desired = {
            "mode": "static",
            "address": "192.168.77.21",
            "prefix_length": 24,
            "gateway": None,
            "dns_servers": [],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_success_commits_ppu_before_registry_endpoint_cas(self) -> None:
        record = self.coordinator.start(
            "ppu-a",
            self.desired,
            rollback_timeout_s=20,
            request_key="request-1",
            authorization="Bearer test",
        )
        self.assertEqual(record.state, "completed")
        self.assertEqual(record.ppu_id, self.fake.ppu_id)
        self.assertEqual(record.candidate_endpoint, self.fake.candidate_endpoint)
        self.assertEqual(self.fake.commit_calls, 1)
        self.assertEqual(self.registry.record_by_alias("ppu-a").endpoint, self.fake.candidate_endpoint)
        persisted = NetworkCommissioningStore(self.root / "commissioning.json").get("ppu-a")
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.state, "completed")

    def test_same_idempotency_key_replays_completed_transaction_without_second_commit(self) -> None:
        first = self.coordinator.start(
            "ppu-a",
            self.desired,
            rollback_timeout_s=20,
            request_key="request-1",
            authorization=None,
        )
        second = self.coordinator.start(
            "ppu-a",
            self.desired,
            rollback_timeout_s=20,
            request_key="request-1",
            authorization=None,
        )
        self.assertEqual(second.transaction_id, first.transaction_id)
        self.assertEqual(self.fake.commit_calls, 1)

    def test_candidate_wrong_identity_never_commits_or_repoints_registry(self) -> None:
        self.fake.candidate_identity = "different-ppu"
        self.fake.activation_state = "idle"
        original_network_activation = self.fake.client

        def client(endpoint: str, timeout_s: float):
            base = original_network_activation(endpoint, timeout_s)
            original_node = base.node

            def node(*, headers=None):
                return original_node(headers=headers)

            base.node = node
            original_activation = base.network_activation

            def network_activation(*, headers=None):
                self.fake.activation_state = "rolled_back"
                return original_activation(headers=headers)

            base.network_activation = network_activation
            return base

        self.coordinator = NetworkCommissioningCoordinator(
            self.registry,
            self.store,
            1.0,
            client_factory=client,
            sleeper=lambda _: None,
            wall_time=lambda: self.wall,
        )
        with self.assertRaises(NetworkCommissioningError) as caught:
            self.coordinator.start(
                "ppu-a",
                self.desired,
                rollback_timeout_s=20,
                request_key="wrong-identity",
                authorization=None,
            )
        self.assertEqual(caught.exception.code, "candidate_identity_mismatch")
        self.assertEqual(caught.exception.record.state, "rolled_back")
        self.assertEqual(self.fake.commit_calls, 0)
        self.assertEqual(self.registry.record_by_alias("ppu-a").endpoint, self.fake.old_endpoint)

    def test_restart_reconciles_only_durable_activation_committed_boundary(self) -> None:
        now = "2026-09-03T00:00:00+00:00"
        record = NetworkCommissioningRecord(
            transaction_id="tx-recover",
            request_key="recover-key",
            request_fingerprint="f" * 64,
            alias="ppu-a",
            state="activation_committed",
            old_endpoint=self.fake.old_endpoint,
            candidate_endpoint=self.fake.candidate_endpoint,
            ppu_id=self.fake.ppu_id,
            desired_revision=2,
            activation_id=self.fake.activation_id,
            rollback_timeout_s=20,
            rollback_deadline_epoch_s=100.0,
            started_at=now,
            updated_at=now,
        )
        self.store.put(record)
        recovered = NetworkCommissioningCoordinator(self.registry, self.store, 1.0)
        recovered.recover()
        final = self.store.get("ppu-a")
        self.assertEqual(final.state, "completed")
        self.assertEqual(self.registry.record_by_alias("ppu-a").endpoint, self.fake.candidate_endpoint)

    def test_restart_before_commit_becomes_recovery_required_without_registry_mutation(self) -> None:
        now = "2026-09-03T00:00:00+00:00"
        record = NetworkCommissioningRecord(
            transaction_id="tx-ambiguous",
            request_key="ambiguous-key",
            request_fingerprint="a" * 64,
            alias="ppu-a",
            state="identity_verified",
            old_endpoint=self.fake.old_endpoint,
            candidate_endpoint=self.fake.candidate_endpoint,
            ppu_id=self.fake.ppu_id,
            desired_revision=2,
            activation_id=self.fake.activation_id,
            rollback_timeout_s=20,
            rollback_deadline_epoch_s=100.0,
            started_at=now,
            updated_at=now,
        )
        self.store.put(record)
        recovered = NetworkCommissioningCoordinator(self.registry, self.store, 1.0)
        recovered.recover()
        final = self.store.get("ppu-a")
        self.assertEqual(final.state, "recovery_required")
        self.assertEqual(self.registry.record_by_alias("ppu-a").endpoint, self.fake.old_endpoint)

    def test_registry_endpoint_cas_rejects_concurrent_mutation_and_duplicate_candidate(self) -> None:
        second = self.registry.add(alias="ppu-b", endpoint="http://192.168.77.30:18080")
        self.registry.set_lifecycle("ppu-b", "commissioned")
        with self.assertRaises(RegistryConflictError):
            self.registry.compare_and_swap_endpoint(
                "ppu-a",
                expected_endpoint=self.fake.old_endpoint,
                new_endpoint=second.endpoint,
            )
        self.registry.compare_and_swap_endpoint(
            "ppu-a",
            expected_endpoint=self.fake.old_endpoint,
            new_endpoint=self.fake.candidate_endpoint,
        )
        with self.assertRaises(RegistryConflictError):
            self.registry.compare_and_swap_endpoint(
                "ppu-a",
                expected_endpoint=self.fake.old_endpoint,
                new_endpoint="http://192.168.77.22:18080",
            )


if __name__ == "__main__":
    unittest.main()

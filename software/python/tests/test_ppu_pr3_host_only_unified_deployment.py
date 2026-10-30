"""PR3 host-only capability resolution, independent policy and Manager API.

No real PPU, SWPC, FPGA Manager, systemd, product file, network or DUT.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from .test_ppu_bundle_v2_host_only_pr2 import (
    bundle, contract, PARTS,
)
from .test_ppu_generic_package_host_only_gate1 import (
    TARGET, SOURCE, coordinator, request, engine,
)
from .test_manager_bootstrap import (
    DEVICE_ID, TOKEN, _registry, FakeBootstrapClient,
)
from plasma_manager.bootstrap import (
    BootstrapCredentialStore, BootstrapManagerError, ManagerBootstrapCoordinator,
)

NOW = 1793448000


def verified(tmp_path: Path):
    archive, digest = bundle(tmp_path)
    return archive, digest, contract.verify_host_only_artifact(
        archive, expected_sha256=digest, source_commit=SOURCE, target_profile=TARGET,
    )


def trusted_policy(artifact):
    return {
        "schema": contract.BUNDLE_POLICY_SCHEMA,
        "publisher": "approved-lab-publisher",
        "source_commit": artifact.source_commit,
        "archive_sha256": artifact.archive_sha256,
        "target": dict(artifact.target),
        "purpose": artifact.purpose,
        "master_generation": 3,
        "active_master_generation": 3,
        "allowed_kinds": [c.kind for c in artifact.components],
        "expires_epoch_s": NOW + 3600,
    }


def test_pr3_versioned_dag_and_staged_components(tmp_path):
    _archive, _digest, artifact = verified(tmp_path)
    plan = contract.resolve_host_only_bundle(artifact, trusted_inventory={})
    assert plan["install_qualified"] is False
    assert len(plan["component_order"]) == 6
    assert plan["reuse"] == []
    assert set(plan["stage"]) == {c.id for c in artifact.components}
    assert plan["component_order"].index("ic-metadata") < plan["component_order"].index("flash-profile")
    assert plan["component_order"].index("flash-profile") < plan["component_order"].index("wordport")
    assert plan["component_order"].index("wordport") < plan["component_order"].index("bridge")
    assert plan["component_order"].index("bridge") < plan["component_order"].index("fpga-addon")


def test_pr3_matching_independently_verified_inventory_reuses_one(tmp_path):
    _archive, _digest, artifact = verified(tmp_path)
    base = artifact.components[0]
    inventory = {
        base.id: {
            "version": base.version,
            "sha256": contract.bundle_component_identity(base),
            "target": dict(artifact.target),
            "verified": True,
        },
    }
    result = contract.resolve_host_only_bundle(artifact, trusted_inventory=inventory)
    assert result["reuse"] == [base.id]
    assert len(result["stage"]) == 5
    inventory[base.id]["sha256"] = "0" * 64
    altered = contract.resolve_host_only_bundle(artifact, trusted_inventory=inventory)
    assert base.id in altered["stage"]
    assert altered["reuse"] == []


@pytest.mark.parametrize("change,error", [
    ({"verified": False}, "BUNDLE_INVENTORY_UNTRUSTED"),
    ({"verified": "True"}, "BUNDLE_INVENTORY_UNTRUSTED"),
    ({"target": {"board": "forged"}}, "BUNDLE_INVENTORY_UNTRUSTED"),
    ({"sha256": ["fake"]}, "BUNDLE_INVENTORY_UNTRUSTED"),
])
def test_pr3_untrusted_cache_hits_fail_closed(tmp_path, change, error):
    _archive, _digest, artifact = verified(tmp_path)
    first = artifact.components[0]
    inventory = {
        first.id: {
            "version": first.version,
            "sha256": contract.bundle_component_identity(first),
            "target": dict(artifact.target),
            "verified": True,
            **change,
        }
    }
    with pytest.raises(contract.UnifiedDeploymentError, match=error):
        contract.resolve_host_only_bundle(artifact, trusted_inventory=inventory)


def test_pr3_unknown_inventory_component_denied(tmp_path):
    _archive, _digest, artifact = verified(tmp_path)
    with pytest.raises(contract.UnifiedDeploymentError, match="BUNDLE_INVENTORY_UNKNOWN_COMPONENT"):
        contract.resolve_host_only_bundle(artifact, trusted_inventory={"phantom": {}})


def test_pr3_exact_authority_gate_accepts_only_host_only_scope(tmp_path):
    archive, digest, artifact = verified(tmp_path)
    approved = trusted_policy(artifact)
    result = contract.evaluate_host_only_bundle_authority(
        artifact, trusted_policy=approved, now_epoch_s=NOW,
    )
    assert result["scope"] == "host-only-fixture"
    assert result["device_install_authorized"] is False
    co = coordinator(tmp_path)
    receipt = co.execute_authorized_bundle_host_only(
        request(archive, digest), trusted_policy=approved,
        trusted_inventory={}, now_epoch_s=NOW,
    )
    assert receipt["result"] == "PASS"
    assert receipt["host_only"] is True
    assert receipt["authorization"]["device_install_authorized"] is False
    assert len(receipt["resolution"]["stage"]) == 6
    assert co.journal.read().state == "package_active"
    assert not co.paths.product_root.exists()


@pytest.mark.parametrize("change,reason", [
    ({"schema": "unknown"}, "BUNDLE_AUTHORITY_MISMATCH"),
    ({"publisher": ""}, "BUNDLE_AUTHORITY_MISMATCH"),
    ({"source_commit": "b" * 40}, "BUNDLE_AUTHORITY_MISMATCH"),
    ({"archive_sha256": "0" * 64}, "BUNDLE_AUTHORITY_MISMATCH"),
    ({"target": {"platform": "other"}}, "BUNDLE_AUTHORITY_MISMATCH"),
    ({"purpose": "system"}, "BUNDLE_AUTHORITY_MISMATCH"),
    ({"master_generation": 2}, "BUNDLE_AUTHORITY_REVOKED_OR_EXPIRED"),
    ({"active_master_generation": 4}, "BUNDLE_AUTHORITY_REVOKED_OR_EXPIRED"),
    ({"expires_epoch_s": NOW}, "BUNDLE_AUTHORITY_REVOKED_OR_EXPIRED"),
    ({"allowed_kinds": ["python"]}, "BUNDLE_COMPONENT_KIND_NOT_AUTHORIZED"),
    ({"allowed_kinds": []}, "BUNDLE_COMPONENT_KIND_NOT_AUTHORIZED"),
])
def test_pr3_authority_denials_have_no_journal_or_installs(tmp_path, change, reason):
    archive, digest, artifact = verified(tmp_path)
    policy = {**trusted_policy(artifact), **change}
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match=reason):
        co.execute_authorized_bundle_host_only(
            request(archive, digest), trusted_policy=policy,
            trusted_inventory={}, now_epoch_s=NOW,
        )
    assert not co.paths.journal.exists()
    assert not co.paths.product_root.exists()


def test_pr3_missing_authority_is_not_inferred_from_manifest_or_token(tmp_path):
    archive, digest, artifact = verified(tmp_path)
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="BUNDLE_AUTHORITY_NOT_PROVISIONED"):
        co.execute_authorized_bundle_host_only(
            request(archive, digest), trusted_policy={},
            trusted_inventory={}, now_epoch_s=NOW,
        )
    assert not co.paths.journal.exists()


def test_pr3_host_only_transaction_rollback_and_unknown_recovery(tmp_path):
    archive, digest, artifact = verified(tmp_path / "release")
    policy = trusted_policy(artifact)
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_INJECTED_ACTIVATION_FAILURE"):
        co.execute_authorized_bundle_host_only(
            request(archive, digest), trusted_policy=policy, trusted_inventory={},
            now_epoch_s=NOW, inject_failure="after_activate",
        )
    assert co.journal.read().state == "rolled_back"
    with pytest.raises(engine.DeploymentError, match="HOST_ONLY_INJECTED_ACTIVATION_FAILURE"):
        co.execute_authorized_bundle_host_only(
            request(archive, digest), trusted_policy=policy, trusted_inventory={},
            now_epoch_s=NOW, inject_failure="rollback_unknown",
        )
    assert co.journal.read().state == "recovery_required"


def test_pr3_manager_bundle_admission_uses_same_authenticated_api(tmp_path):
    FakeBootstrapClient.instances.clear()
    creds = BootstrapCredentialStore(tmp_path / "credentials.json")
    creds.set("z2", DEVICE_ID, TOKEN)

    class AdmissionClient(FakeBootstrapClient):
        def start_deployment(self, token, body):
            self.calls.append(("start_deployment", token, dict(body)))
            return 200, {
                "ok": True, "deployment": {
                    "state": "admitted",
                    "result": {
                        "stage": "package_admission_only",
                        "install_qualified": False,
                        "plan": {
                            "kind": "bundle", "execution_permitted": False,
                        },
                    },
                },
            }

    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=AdmissionClient,
    )
    status, body = manager.start_deployment(
        "z2", {"kind": "bundle", "upload_id": "a" * 32},
    )
    assert status == 200 and body["deployment"]["state"] == "admitted"
    calls = [c for c in AdmissionClient.instances[-1].calls if c[0] == "start_deployment"]
    assert calls == [("start_deployment", TOKEN, {"kind": "bundle", "upload_id": "a" * 32})]
    assert "gateway_host" not in calls[0][2]


@pytest.mark.parametrize("body", [
    {"kind": "bundle", "upload_id": "A" * 32},
    {"kind": "bundle", "upload_id": "a" * 32, "activate": True},
    {"kind": "bundle", "upload_id": "a" * 32, "publisher": "self"},
    {"kind": "bundle", "upload_id": "a" * 32, "gateway_host": "evil"},
])
def test_pr3_manager_rejects_caller_authority(tmp_path, body):
    creds = BootstrapCredentialStore(tmp_path / "credentials.json")
    creds.set("z2", DEVICE_ID, TOKEN)
    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=FakeBootstrapClient,
    )
    with pytest.raises(BootstrapManagerError):
        manager.start_deployment("z2", body)


def test_pr3_manager_rejects_untrusted_upstream_install_receipt(tmp_path):
    creds = BootstrapCredentialStore(tmp_path / "credentials.json")
    creds.set("z2", DEVICE_ID, TOKEN)

    class CompromisedClient(FakeBootstrapClient):
        def start_deployment(self, token, body):
            return 200, {
                "ok": True,
                "deployment": {
                    "state": "succeeded",
                    "result": {"stage": "installed", "install_qualified": True},
                },
            }
    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=CompromisedClient,
    )
    with pytest.raises(BootstrapManagerError, match="not non-executing"):
        manager.start_deployment("z2", {"kind": "bundle", "upload_id": "a" * 32})

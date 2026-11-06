"""PR3 host-only capability resolution, Owner Authorization and Manager API.

No real PPU, SWPC, FPGA Manager, systemd, product file, network or DUT.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import bundle_v3, contract, PARTS
from .test_ppu_generic_package_host_only_gate1 import (
    TARGET, SOURCE, coordinator, request, engine,
)
from .test_manager_bootstrap import (
    DEVICE_ID, TOKEN, _registry, FakeBootstrapClient,
)
from plasma_manager.bootstrap import (
    BootstrapCredentialStore, BootstrapManagerError, ManagerBootstrapCoordinator,
)
from .ppu_owner_authorization_fixture import install_summary, owner as owner_module


def verified(tmp_path: Path):
    archive, digest = bundle_v3(tmp_path)
    return archive, digest, contract.verify_host_only_artifact(
        archive, expected_sha256=digest, target_profile=TARGET,
    )


def owner_install(artifact):
    return install_summary(artifact.archive_sha256)


def test_pr3_versioned_dag_and_staged_components(tmp_path):
    _archive, _digest, artifact = verified(tmp_path)
    plan = contract.resolve_host_only_bundle(artifact, trusted_inventory={})
    assert plan["install_qualified"] is False
    assert len(plan["package_order"]) == 6
    assert plan["reuse"] == []
    assert set(plan["stage"]) == {c.id for c in artifact.packages}
    assert plan["package_order"].index("ic-metadata") < plan["package_order"].index("flash-profile")
    assert plan["package_order"].index("flash-profile") < plan["package_order"].index("wordport")
    assert plan["package_order"].index("wordport") < plan["package_order"].index("bridge")
    assert plan["package_order"].index("bridge") < plan["package_order"].index("fpga-addon")


def test_pr3_matching_independently_verified_inventory_reuses_one(tmp_path):
    _archive, _digest, artifact = verified(tmp_path)
    base = artifact.packages[0]
    inventory = {
        base.id: {
            "version": base.version,
            "sha256": contract.bundle_package_identity(base),
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
    first = artifact.packages[0]
    inventory = {
        first.id: {
            "version": first.version,
            "sha256": contract.bundle_package_identity(first),
            "target": dict(artifact.target),
            "verified": True,
            **change,
        }
    }
    with pytest.raises(contract.UnifiedDeploymentError, match=error):
        contract.resolve_host_only_bundle(artifact, trusted_inventory=inventory)


def test_pr3_unknown_inventory_component_denied(tmp_path):
    _archive, _digest, artifact = verified(tmp_path)
    with pytest.raises(contract.UnifiedDeploymentError, match="BUNDLE_INVENTORY_UNKNOWN_PACKAGE"):
        contract.resolve_host_only_bundle(artifact, trusted_inventory={"phantom": {}})


def test_pr3_owner_install_authorization_accepts_only_host_only_scope(tmp_path):
    archive, digest, artifact = verified(tmp_path)
    approved = owner_install(artifact)
    result = contract.evaluate_host_only_owner_authorization(
        artifact, owner_authorization=approved,
    )
    assert result["scope"] == "host-only-fixture"
    assert result["device_install_authorized"] is False
    co = coordinator(tmp_path)
    receipt = co.execute_authorized_bundle_host_only(
        request(archive, digest), owner_authorization=approved, trusted_inventory={},
    )
    assert receipt["result"] == "PASS"
    assert receipt["host_only"] is True
    assert receipt["authorization"]["device_install_authorized"] is False
    assert receipt["authorization"]["action"] == "bundle.install"
    assert len(receipt["resolution"]["stage"]) == 6
    assert co.journal.read().state == "installed"
    assert receipt["operation"] == "install_only"
    assert receipt["active_pointer_unchanged"] is True
    assert not co.paths.product_root.exists()


@pytest.mark.parametrize("change,reason", [
    ({"status": "LOCAL_APPROVED"}, "OWNER_AUTHORIZATION_REQUIRED"),
    ({"schema": "plasma.ppu.bundle-authority.v2"}, "OWNER_AUTHORIZATION_REQUIRED"),
    ({"action": "bundle.admit"}, "OWNER_AUTHORIZATION_REQUIRED"),
    ({"action": "asset.execute"}, "OWNER_AUTHORIZATION_REQUIRED"),
    ({"subject_sha256": "0" * 64}, "OWNER_AUTHORIZATION_SUBJECT_MISMATCH"),
])
def test_pr3_authority_denials_have_no_journal_or_installs(tmp_path, change, reason):
    archive, digest, artifact = verified(tmp_path)
    summary = {**owner_install(artifact), **change}
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match=reason):
        co.execute_authorized_bundle_host_only(
            request(archive, digest), owner_authorization=summary, trusted_inventory={},
        )
    assert not co.paths.journal.exists()
    assert not co.paths.product_root.exists()


def test_pr3_missing_authority_is_not_inferred_from_manifest_or_token(tmp_path):
    archive, digest, artifact = verified(tmp_path)
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="OWNER_AUTHORIZATION_REQUIRED"):
        co.execute_authorized_bundle_host_only(
            request(archive, digest), owner_authorization={}, trusted_inventory={},
        )
    assert not co.paths.journal.exists()


def test_pr3_host_only_install_only_rejects_activation_faults(tmp_path):
    archive, digest, artifact = verified(tmp_path / "release")
    approved = owner_install(artifact)
    co = coordinator(tmp_path)
    for fault in ("after_activate", "rollback_unknown"):
        with pytest.raises(engine.DeploymentError, match="INSTALL_ONLY_ACTIVATION_FAILURE_SELECTOR_DENIED"):
            co.execute_authorized_bundle_host_only(
                request(archive, digest), owner_authorization=approved, trusted_inventory={},
                inject_failure=fault,
            )
    assert not co.paths.journal.exists()
    assert not co.paths.product_root.exists()


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
                        "owner_authorized": True,
                        "plan": {
                            "kind": "bundle", "execution_permitted": False,
                            "archive_sha256": "b" * 64,
                            "owner_authorization": {
                                "status": "OWNER_AUTHORIZED",
                                "action": "bundle.admit",
                                "subject_sha256": "b" * 64,
                                "transaction_id": "a" * 32,
                            },
                        },
                    },
                },
            }

    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=AdmissionClient,
    )
    status, body = manager.start_deployment(
        "z2", {"kind": "bundle", "upload_id": "a" * 32, "archive_sha256": "b" * 64},
    )
    assert status == 200 and body["deployment"]["state"] == "admitted"
    calls = [c for c in AdmissionClient.instances[-1].calls if c[0] == "start_deployment"]
    assert len(calls) == 1 and calls[0][1] == TOKEN
    sent = calls[0][2]
    assert set(sent) == {"kind", "upload_id", "authorization"}
    assert "gateway_host" not in sent and "archive_sha256" not in sent
    # Producer/consumer contract: the PPU-side verifier accepts the Manager's
    # device-bound authorization for exactly this archive and upload.
    verified_owner = owner_module.verify(
        sent["authorization"], credential=TOKEN, action="bundle.admit",
        device_id=DEVICE_ID, subject_sha256="b" * 64, transaction_id="a" * 32,
    )
    assert verified_owner["status"] == "OWNER_AUTHORIZED"
    for wrong in ({"subject_sha256": "c" * 64}, {"device_id": "ppu-device-" + "f" * 24},
                  {"transaction_id": "d" * 32}, {"action": "bundle.install"}):
        args = dict(credential=TOKEN, action="bundle.admit", device_id=DEVICE_ID,
                    subject_sha256="b" * 64, transaction_id="a" * 32)
        args.update(wrong)
        with pytest.raises(owner_module.OwnerAuthorizationDenied):
            owner_module.verify(sent["authorization"], **args)


@pytest.mark.parametrize("body", [
    {"kind": "bundle", "upload_id": "A" * 32, "archive_sha256": "b" * 64},
    {"kind": "bundle", "upload_id": "a" * 32},
    {"kind": "bundle", "upload_id": "a" * 32, "archive_sha256": "B" * 64},
    {"kind": "bundle", "upload_id": "a" * 32, "archive_sha256": "b" * 64, "activate": True},
    {"kind": "bundle", "upload_id": "a" * 32, "archive_sha256": "b" * 64, "publisher": "self"},
    {"kind": "bundle", "upload_id": "a" * 32, "archive_sha256": "b" * 64, "gateway_host": "evil"},
    # Caller may not supply its own (possibly forged) authorization object.
    {"kind": "bundle", "upload_id": "a" * 32, "archive_sha256": "b" * 64,
     "authorization": {"mac": "0" * 64}},
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
    with pytest.raises(BootstrapManagerError, match="not owner-authorized and non-executing"):
        manager.start_deployment("z2", {"kind": "bundle", "upload_id": "a" * 32,
                                        "archive_sha256": "b" * 64})


B3_BODY = {"kind": "bundle", "upload_id": "a" * 32, "archive_sha256": "b" * 64,
           "admission_transaction_id": "e" * 32, "mode": "activate"}


@pytest.mark.parametrize("mode,fpga_load,action", [
    ("stage_only", False, "bundle.install"),
    ("activate", False, "bundle.activate"),
    ("activate", True, "bundle.activate-fpga-load"),
])
def test_manager_forwards_b3_mode_and_exact_authorization(tmp_path, mode, fpga_load, action):
    FakeBootstrapClient.instances.clear()
    creds = BootstrapCredentialStore(tmp_path / "credentials.json")
    creds.set("z2", DEVICE_ID, TOKEN)

    class B3Client(FakeBootstrapClient):
        def start_deployment(self, token, body):
            self.calls.append(("start_deployment", token, dict(body)))
            # The real PPU answers a queued B3 with HTTP 202 Accepted.
            return 202, {"ok": True, "deployment": {
                "state": "queued", "upload_id": "a" * 32, "transaction_id": "c" * 32,
                "admission_transaction_id": "e" * 32,
                "mode": body["mode"], "fpga_load": body["fpga_load"],
                "owner_authorization": {
                    "status": "OWNER_AUTHORIZED", "action": action,
                    "subject_sha256": "b" * 64,
                },
            }}

    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=B3Client,
    )
    status, body = manager.start_deployment("z2", {**B3_BODY, "mode": mode,
                                                   "fpga_load": fpga_load})
    assert status == 202 and body["deployment"]["state"] == "queued"
    calls = [c for c in B3Client.instances[-1].calls if c[0] == "start_deployment"]
    assert len(calls) == 1 and calls[0][1] == TOKEN
    sent = calls[0][2]
    assert set(sent) == {"kind", "upload_id", "mode", "fpga_load", "authorization"}
    assert sent["mode"] == mode
    assert sent["fpga_load"] is fpga_load
    # Each B3 mode is a distinct action bound to the CURRENT B2 transaction.
    owner_module.verify(
        sent["authorization"], credential=TOKEN, action=action,
        device_id=DEVICE_ID, subject_sha256="b" * 64, transaction_id="e" * 32,
    )
    for other_action in {"bundle.install", "bundle.activate",
                         "bundle.activate-fpga-load"} - {action}:
        with pytest.raises(owner_module.OwnerAuthorizationDenied, match="ACTION_MISMATCH"):
            owner_module.verify(
                sent["authorization"], credential=TOKEN, action=other_action,
                device_id=DEVICE_ID, subject_sha256="b" * 64, transaction_id="e" * 32,
            )


@pytest.mark.parametrize("body", [
    {**B3_BODY, "fpga_load": "true"},
    {**{key: value for key, value in B3_BODY.items() if key != "mode"}, "fpga_load": False},
    {**B3_BODY, "fpga_load": True, "mode": "stage_only"},
    {**B3_BODY, "fpga_load": False, "mode": "unknown"},
    {**B3_BODY, "fpga_load": False, "mode": None},
    {**B3_BODY, "fpga_load": True, "idle": True},
    {**B3_BODY, "fpga_load": True, "path": "/opt"},
    {**B3_BODY, "upload_id": "A" * 32, "fpga_load": False},
    {"kind": "bundle", "upload_id": "a" * 32, "fpga_load": True},
    {**B3_BODY, "admission_transaction_id": "x" * 32, "fpga_load": False},
    {**B3_BODY, "fpga_load": False, "authorization": {"mac": "0" * 64}},
])
def test_manager_rejects_b3_extra_or_non_boolean_fields(tmp_path, body):
    creds = BootstrapCredentialStore(tmp_path / "credentials.json")
    creds.set("z2", DEVICE_ID, TOKEN)
    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=FakeBootstrapClient,
    )
    with pytest.raises(BootstrapManagerError):
        manager.start_deployment("z2", body)


def test_manager_rejects_b3_reply_that_is_not_queued(tmp_path):
    creds = BootstrapCredentialStore(tmp_path / "credentials.json")
    creds.set("z2", DEVICE_ID, TOKEN)

    class Odd(FakeBootstrapClient):
        def start_deployment(self, token, body):
            return 200, {"ok": True, "deployment": {"state": "succeeded", "upload_id": "a" * 32}}

    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=Odd,
    )
    with pytest.raises(BootstrapManagerError, match="not a queued transaction"):
        manager.start_deployment("z2", {**B3_BODY, "fpga_load": False})


@pytest.mark.parametrize("change", [
    lambda receipt: receipt.__setitem__("mode", "stage_only"),
    lambda receipt: receipt.__setitem__("fpga_load", True),
    lambda receipt: receipt["owner_authorization"].__setitem__("action", "bundle.install"),
])
def test_manager_rejects_b3_reply_with_changed_mode_or_action(tmp_path, change):
    creds = BootstrapCredentialStore(tmp_path / "credentials.json")
    creds.set("z2", DEVICE_ID, TOKEN)

    class WrongB3(FakeBootstrapClient):
        def start_deployment(self, token, body):
            receipt = {
                "state": "queued", "upload_id": "a" * 32,
                "admission_transaction_id": "e" * 32,
                "mode": "activate", "fpga_load": False,
                "owner_authorization": {
                    "status": "OWNER_AUTHORIZED", "action": "bundle.activate",
                    "subject_sha256": "b" * 64,
                },
            }
            change(receipt)
            return 202, {"ok": True, "deployment": receipt}

    manager = ManagerBootstrapCoordinator(
        _registry(tmp_path), creds, 2.0, client_factory=WrongB3,
    )
    with pytest.raises(BootstrapManagerError, match="not a queued transaction"):
        manager.start_deployment("z2", {**B3_BODY, "fpga_load": False})

"""P4-01: the real Bundle v3 bytes share one B2/B3 admission engine.

Host filesystem only. No mock transport, Root Entry, Z2, FPGA or DUT.
"""
from __future__ import annotations

import pytest

from .ppu_fpga_qualification_fixture import synthetic_image
from .test_ppu_bundle_v3_packages_contract import TARGET, engine
from .test_ppu_bundle_v3_smoke_execution_gate1 import build_smoke
from .test_ppu_fpga_static_qualification_gate1 import contract_file, fpga_bundle


def _admit(archive, digest, contracts_path, *, target=TARGET):
    return engine.DeploymentCoordinator.qualify_bundle_v3_admission(
        archive, expected_sha256=digest,
        target_profile=target, contracts_path=contracts_path,
    )


def test_engine_b2_and_b3_preflight_same_real_three_package_bundle(tmp_path):
    archive, digest = build_smoke(tmp_path / "archive")
    absent_contracts = tmp_path / "factory" / "contracts.json"
    b2 = _admit(archive, digest, absent_contracts)
    b3 = _admit(archive, digest, absent_contracts)
    assert b2 == b3
    assert b2["bundle_schema"] == "plasma.ppu.bundle.v3"
    assert b2["archive_sha256"] == digest
    assert b2["source_commit"] is None
    assert b2["requested_actions"] == ["install", "verify"]
    assert [item["id"] for item in b2["packages"]] == [
        "python-smoke", "programming-profile", "ic-catalog",
    ]
    assert b2["execution_permitted"] is False
    assert b2["fpga_qualification"] is None
    assert not absent_contracts.exists()
    assert not (tmp_path / "product").exists()
    assert not (tmp_path / "state").exists()
    assert not list(tmp_path.rglob("active.json"))
    assert not list(tmp_path.rglob("deployment.json"))


@pytest.mark.parametrize("denial", ["wrong_digest", "wrong_target"])
def test_engine_preflight_fail_closed_without_deployment_mutation(tmp_path, denial):
    archive, digest = build_smoke(tmp_path / "archive")
    kwargs = {}
    if denial == "wrong_digest":
        digest = "0" * 64
    else:
        kwargs["target"] = {**TARGET, "board": "wrong-board"}
    with pytest.raises(engine.BundleV3AdmissionVerificationDenied):
        _admit(archive, digest, tmp_path / "unused.json", **kwargs)
    assert not (tmp_path / "product").exists()
    assert not list(tmp_path.rglob("active.json"))
    assert not list(tmp_path.rglob("deployment.json"))


def test_engine_fpga_qualification_is_shared_and_trusted_contract_drift_detectable(tmp_path):
    files, entry = synthetic_image()
    archive, digest = fpga_bundle(tmp_path / "archive", files)
    contracts = contract_file(tmp_path, entry)
    b2 = _admit(archive, digest, contracts)
    assert b2["fpga_qualification"]["result"] == "STATIC_QUALIFIED"
    assert b2["fpga_qualification"]["fpga_loaded"] is False
    assert b2 == _admit(archive, digest, contracts)

    # Withdraw factory contract after B2; B3 preflight must fail closed.
    contracts.unlink()
    with pytest.raises(engine.BundleV3AdmissionQualificationDenied):
        _admit(archive, digest, contracts)
    assert not list(tmp_path.rglob("active.json"))

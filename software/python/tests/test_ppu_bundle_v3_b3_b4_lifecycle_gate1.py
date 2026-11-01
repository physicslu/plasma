"""B3/B4 Bundle v3 Host-only positive and failure-injection regressions.

Reuses canonical v3 fixtures and the existing single DeploymentCoordinator.
No device, service, FPGA, DUT, or production path is accessed.
"""
from __future__ import annotations

import pytest

from .test_ppu_bundle_v3_packages_contract import (
    SOURCE, TARGET, bundle_v3, coordinator, request,
)


def test_b3_b4_authorized_host_only_receipt(tmp_path):
    archive, digest = bundle_v3(tmp_path / "input")
    co = coordinator(tmp_path)
    policy = {
        "schema": "plasma.ppu.host-policy.v1",
        "publisher": "fixture-publisher",
        "source_commit": SOURCE,
        "archive_sha256": digest,
        "target": TARGET,
        "purpose": "programming",
        "master_generation": 1,
        "active_master_generation": 1,
        "allowed_kinds": [
            "ic-catalog", "programming-profile", "python",
            "native-c", "firmware-asset", "fpga-image",
        ],
        "expires_epoch_s": 200,
    }
    receipt = co.execute_authorized_bundle_host_only(
        request(archive, digest),
        trusted_policy=policy,
        trusted_inventory={},
        now_epoch_s=123,
    )
    assert receipt["result"] == "PASS"
    assert receipt["host_only"] is True
    assert receipt["install_qualified"] is False
    assert receipt["b3_install"]["status"] == "NOT_QUALIFIED"
    assert len(receipt["b3_install"]["package_order_plan"]) == 6\n    assert receipt["b3_install"]["per_package_install_executed"] is False
    assert receipt["b4_activate"]["status"] == "NOT_QUALIFIED"\n    assert receipt["b4_activate"]["runtime_activation_executed"] is False
    assert not co.paths.product_root.exists()


@pytest.mark.parametrize("fault,expected_state", [
    ("after_stage", "rolled_back"),
    ("after_activate", "rolled_back"),
    ("rollback_unknown", "recovery_required"),
])
def test_b3_b4_failure_journal_fails_closed(tmp_path, fault, expected_state):
    archive, digest = bundle_v3(tmp_path / "input")
    co = coordinator(tmp_path)
    with pytest.raises(Exception):
        co.execute_package_host_only(request(archive, digest), inject_failure=fault)
    record = co.journal.read()
    assert record is not None
    assert record.state == expected_state
    active = (co.paths.bootstrap_state_root / "host-only-packages" /
              "active" / "multi-purpose-bundle.json")
    if expected_state == "recovery_required":
        # Fail closed: an uncertain rollback MUST retain evidence of the
        # possibly active release; it is NOT equivalent to a clean rollback.
        assert active.exists()
        assert record.error_code == "host_only_rollback_unknown"
    else:
        assert not active.exists()
    assert not co.paths.product_root.exists()

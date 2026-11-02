"""B3 install-only: host sandbox smoke; no activation, hardware or service changes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import (
    bundle_v3, coordinator, request,
)

def test_b3_install_only_does_not_create_active_pointer(tmp_path):
    archive, digest = bundle_v3(tmp_path / "bundle")
    co = coordinator(tmp_path)
    result = co.execute_package_host_only(request(archive, digest), install_only=True)
    assert result["result"] == "PASS"
    assert result["operation"] == "install_only"
    assert result["active_pointer_unchanged"] is True
    assert result["runtime_activation_executed"] is False
    assert result["install_qualified"] is False
    assert result["package_order"].index("ic-metadata") < result["package_order"].index("flash-profile")
    assert result["package_order"].index("flash-profile") < result["package_order"].index("wordport")
    active = co.paths.bootstrap_state_root / "host-only-packages" / "active" / "multi-purpose-bundle.json"
    assert not active.exists()
    release = co.paths.bootstrap_state_root / "host-only-packages" / "releases" / "multi-purpose-bundle" / result["release_id"]
    assert (release / "payload/packages/ic-metadata/data/device.json").is_file()
    assert (release / "payload/packages/flash-profile/data/geometry.yaml").is_file()

def test_b3_install_only_is_idempotent(tmp_path):
    archive, digest = bundle_v3(tmp_path / "bundle")
    co = coordinator(tmp_path)
    first = co.execute_package_host_only(request(archive, digest), install_only=True)
    second = co.execute_package_host_only(request(archive, digest), install_only=True)
    assert first["release_id"] == second["release_id"]
    assert second["result"] == "PASS"

def test_b3_install_only_preserves_existing_active_pointer(tmp_path):
    archive, digest = bundle_v3(tmp_path / "bundle")
    co = coordinator(tmp_path)
    active = co.paths.bootstrap_state_root / "host-only-packages" / "active" / "multi-purpose-bundle.json"
    active.parent.mkdir(parents=True)
    # Invalid prior receipt must fail closed, never silently replace it.
    active.write_bytes(b"not-a-valid-receipt")
    with pytest.raises(Exception):
        co.execute_package_host_only(request(archive, digest), install_only=True)
    assert active.read_bytes() == b"not-a-valid-receipt"

def test_b3_install_only_rejects_activation_failure_injection(tmp_path):
    archive, digest = bundle_v3(tmp_path / "bundle")
    co = coordinator(tmp_path)
    with pytest.raises(Exception, match="INSTALL_ONLY_ACTIVATION_FAILURE_SELECTOR_DENIED"):
        co.execute_package_host_only(request(archive, digest), install_only=True, inject_failure="after_activate")

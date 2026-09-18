from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "scripts" / "z2like-demo-qemu-installer.py"
DEPLOYER = ROOT / "scripts" / "z2like-demo-qemu-deploy.py"
TARGET = ROOT / "scripts" / "z2like-demo-qemu-target.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _config(installer, tmp_path: Path, *, site_count: str | None = None) -> dict:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    if site_count is not None:
        (state_root / installer.SITE_COUNT_MARKER).write_text(site_count + "\n", encoding="utf-8")
    text = installer._simulation_config(
        ppu_id="z2like-qemu-01",
        facility_id="swpc-simulation",
        display_name="SWPC QEMU ARMv7 Z2 Simulation",
        state_root=state_root,
        log_root=tmp_path / "logs",
    )
    payload = yaml.safe_load(text)
    assert isinstance(payload, dict)
    return payload


def _trusted_fleet(observed_at: datetime, *, state: str = "idle") -> dict:
    return {
        "ok": True,
        "observed_at": observed_at.isoformat(),
        "ppus": [
            {
                "alias": "z2like-qemu",
                "gateway_live": True,
                "identity_conflict": False,
                "errors": [],
                "observation": {"state": "current"},
                "sites": [{"site_id": 1, "state": state, "current_job_id": None}],
            }
        ],
    }


def test_default_topology_has_eight_enabled_mock_sites(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PLASMA_Z2LIKE_DEMO_SITE_COUNT", raising=False)
    installer = _load(INSTALLER, "plasma_z2like_demo_installer_default_sites")
    payload = _config(installer, tmp_path)

    assert payload["server"]["max_supported_sites"] == 8
    assert payload["server"]["max_concurrent_jobs"] == 8
    assert [site["id"] for site in payload["sites"]] == list(range(1, 9))
    assert all(site["enabled"] is True for site in payload["sites"])
    assert all(site["interface"] == "mock" for site in payload["sites"])
    assert all(site["mock"]["flash_size"] == 65536 for site in payload["sites"])
    assert all(
        site["mock"]["delays"]["erase"] == installer.CONFIGURED_MOCK_ERASE_OBSERVATION_DELAY_S
        for site in payload["sites"]
    )


def test_site_count_marker_controls_topology_without_hard_coding_runtime_count(tmp_path: Path) -> None:
    installer = _load(INSTALLER, "plasma_z2like_demo_installer_variable_sites")
    payload = _config(installer, tmp_path, site_count="3")

    assert payload["server"]["max_supported_sites"] == 8
    assert payload["server"]["max_concurrent_jobs"] == 3
    assert [site["id"] for site in payload["sites"]] == [1, 2, 3]


def test_site_count_marker_fails_closed_outside_supported_range(tmp_path: Path) -> None:
    installer = _load(INSTALLER, "plasma_z2like_demo_installer_invalid_sites")
    with pytest.raises(installer.Z2InstallerError):
        _config(installer, tmp_path, site_count="0")
    with pytest.raises(installer.Z2InstallerError):
        _config(installer, tmp_path, site_count="9")


def test_managed_topology_set_includes_legacy_empty_and_previous_no_delay_configs(tmp_path: Path) -> None:
    installer = _load(INSTALLER, "plasma_z2like_demo_installer_managed_configs")
    state_root = tmp_path / "state"
    log_root = tmp_path / "logs"
    managed = installer._managed_simulation_configs(
        ppu_id="z2like-qemu-01",
        facility_id="swpc-simulation",
        display_name="SWPC QEMU ARMv7 Z2 Simulation",
        state_root=state_root,
        log_root=log_root,
    )
    legacy = installer._legacy_empty_simulation_config(
        ppu_id="z2like-qemu-01",
        facility_id="swpc-simulation",
        display_name="SWPC QEMU ARMv7 Z2 Simulation",
        state_root=state_root,
        log_root=log_root,
    ).encode("utf-8")
    three = installer._simulation_config_for_count(
        ppu_id="z2like-qemu-01",
        facility_id="swpc-simulation",
        display_name="SWPC QEMU ARMv7 Z2 Simulation",
        state_root=state_root,
        log_root=log_root,
        site_count=3,
    ).encode("utf-8")
    previous_three = installer._simulation_config_for_count_without_observable_erase_delay(
        ppu_id="z2like-qemu-01",
        facility_id="swpc-simulation",
        display_name="SWPC QEMU ARMv7 Z2 Simulation",
        state_root=state_root,
        log_root=log_root,
        site_count=3,
    ).encode("utf-8")

    assert legacy in managed
    assert three in managed
    assert previous_three in managed
    assert previous_three != three
    assert len(managed) == 17


def test_target_enables_configured_mock_programming_provider() -> None:
    source = TARGET.read_text(encoding="utf-8")
    assert '"--engineering-configured-mock"' in source
    assert '"--engineering-mock"' not in source


def test_deployer_requires_new_generation_after_target_restart_for_existing_runtime() -> None:
    source = DEPLOYER.read_text(encoding="utf-8")
    generation_baseline = source.index("baseline_generation = _read_fleet_generation(manager)")
    reload_target = source.index("_prepare_target_scenario(args.container, args.site_count)")
    runtime_state = source.index('runtime_state_before = runtime.get("state")')
    maintenance_gate = source.index('maintenance_requires_idle = runtime_state_before == "runtime_active"')
    idle_wait = source.index("trusted_generation = _wait_for_trusted_idle(")
    upload_create = source.index("created, trusted_generation = _create_upload_with_idle_retry(")
    preserve_registration = source.index("lifecycle_after != lifecycle_before")
    assert generation_baseline < reload_target < runtime_state < maintenance_gate < idle_wait < upload_create < preserve_registration
    assert '_set_lifecycle(manager, args.alias, "disabled"' not in source
    assert '_set_lifecycle(manager, args.alias, "commissioned"' not in source


def test_trusted_idle_predicate_matches_manager_maintenance_gate() -> None:
    deployer = _load(DEPLOYER, "plasma_z2like_demo_deployer_idle")
    item = {
        "alias": "z2like-qemu",
        "gateway_live": True,
        "identity_conflict": False,
        "errors": [],
        "observation": {"state": "current"},
        "sites": [{"site_id": 1, "state": "idle", "current_job_id": None}],
    }
    assert deployer._fleet_item_is_trusted_idle(item, "z2like-qemu") is True

    stale = dict(item)
    stale["observation"] = {"state": "stale"}
    assert deployer._fleet_item_is_trusted_idle(stale, "z2like-qemu") is False

    busy = dict(item)
    busy["sites"] = [{"site_id": 1, "state": "running", "current_job_id": "job-1"}]
    assert deployer._fleet_item_is_trusted_idle(busy, "z2like-qemu") is False


def test_trusted_idle_generation_rejects_cached_pre_restart_snapshot() -> None:
    deployer = _load(DEPLOYER, "plasma_z2like_demo_deployer_generation")
    baseline = datetime(2026, 9, 14, 5, 30, tzinfo=timezone.utc)

    cached_current = _trusted_fleet(baseline)
    assert deployer._fleet_has_trusted_idle_after(cached_current, "z2like-qemu", baseline) is False

    newer_current = _trusted_fleet(baseline + timedelta(seconds=1))
    assert deployer._fleet_has_trusted_idle_after(newer_current, "z2like-qemu", baseline) is True

    newer_busy = _trusted_fleet(baseline + timedelta(seconds=2), state="running")
    assert deployer._fleet_has_trusted_idle_after(newer_busy, "z2like-qemu", baseline) is False


def test_fleet_generation_fails_closed_for_invalid_timestamp() -> None:
    deployer = _load(DEPLOYER, "plasma_z2like_demo_deployer_invalid_generation")
    with pytest.raises(deployer.DeployError):
        deployer._fleet_observed_at({"observed_at": "not-a-timestamp"})
    with pytest.raises(deployer.DeployError):
        deployer._fleet_observed_at({"observed_at": "2026-09-14T05:30:00"})


def test_upload_retry_is_limited_to_idle_observation_conflict() -> None:
    source = DEPLOYER.read_text(encoding="utf-8")
    retry_helper = source[source.index("def _create_upload_with_idle_retry(") : source.index("def _verify_programming_catalog(")]
    assert '"ppu_idle_state_unproven"' in retry_helper
    assert "status != 409" in retry_helper
    assert "_wait_for_trusted_idle(" in retry_helper


def test_deployer_programming_catalog_validation() -> None:
    deployer = _load(DEPLOYER, "plasma_z2like_demo_deployer_catalog")
    good = {
        "ok": True,
        "provider": "configured_mock",
        "ppu_count": 1,
        "site_count": 3,
        "facilities": [
            {
                "facility_id": "swpc-simulation",
                "ppus": [{"ppu_id": "z2like-qemu-01", "site_count": 3}],
            }
        ],
    }
    deployer._verify_programming_catalog(good, site_count=3, ppu_id="z2like-qemu-01")

    bad = dict(good)
    bad["site_count"] = 0
    with pytest.raises(deployer.DeployError):
        deployer._verify_programming_catalog(bad, site_count=3, ppu_id="z2like-qemu-01")

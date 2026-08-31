from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RETIRED_PUBLIC_GATEWAY = "plasma.open4th.com"


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_retired_public_gateway_is_absent_from_production_runtime_ownership() -> None:
    production_paths = (
        "packaging/windows/run-console.ps1",
        "scripts/plasmactl",
        "software/web/app/layout.tsx",
        "software/web/app/plasma-api.ts",
        "software/web/next.config.ts",
        "software/web/vite.config.ts",
    )
    for path in production_paths:
        assert RETIRED_PUBLIC_GATEWAY not in _source(path), path


def test_windows_control_station_launcher_is_explicitly_managed() -> None:
    launcher = _source("packaging/windows/run-console.ps1")
    assert "$env:PLASMA_FLEET_UI_ENABLED = '1'" in launcher
    assert "$env:PLASMA_CONTROL_STATION_MODE = 'managed'" in launcher
    assert "$env:PLASMA_MANAGER_API_URL = 'http://127.0.0.1:18180'" in launcher


def test_web_default_and_storage_migration_are_same_origin_owned() -> None:
    api = _source("software/web/app/plasma-api.ts")
    layout = _source("software/web/app/layout.tsx")
    assert 'process.env.NEXT_PUBLIC_PLASMA_API_URL ?? ""' in api
    assert 'return window.location.origin;' in api
    assert 'window.localStorage.getItem(versionKey) === "3"' in layout
    assert 'window.localStorage.removeItem(apiKey);' in layout
    assert "legacyApiBases" not in layout


def test_swpc_local_gateway_and_mock_path_remain_available_behind_same_origin() -> None:
    vite = _source("software/web/vite.config.ts")
    deployment = _source("scripts/plasmactl")
    assert 'target: "http://127.0.0.1:18080"' in vite
    assert 'engineering_mock_args=" --engineering-mock --engineering-mock-root $engineering_mock_root"' in deployment
    assert 'default_public_api_url=""' in deployment
    assert "current_config_version=6" in deployment


def test_windows_installer_acceptance_proves_clean_install_managed_fail_closed() -> None:
    acceptance = _source("scripts/windows-control-station-installer-acceptance.py")
    assert "def _assert_clean_install_managed_routing()" in acceptance
    assert "_assert_clean_install_managed_routing()" in acceptance
    assert 'payload.get("managed") is not True' in acceptance
    assert 'payload.get("configured") is not False' in acceptance
    assert '"manager_bff_misconfigured"' in acceptance
    assert "Windows installer clean-install managed routing: PASS" in acceptance

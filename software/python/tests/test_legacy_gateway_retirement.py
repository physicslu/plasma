from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_PREVIEW_HOST = "plasma.open4th.com"
PRIVATE_ENGINEERING_HOST = "swpc.tail820e64.ts.net"


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_public_preview_host_is_allowed_without_restoring_direct_gateway_ownership() -> None:
    vite = _source("software/web/vite.config.ts")
    assert 'allowedHosts: [' in vite
    assert f'"{PUBLIC_PREVIEW_HOST}",' in vite
    assert f'"{PRIVATE_ENGINEERING_HOST}",' in vite

    # The public hostname is an ingress alias for the same SWPC Web runtime.
    # It must not reappear as a Browser-owned/default remote Gateway endpoint.
    direct_gateway_ownership_paths = (
        "packaging/windows/run-console.ps1",
        "scripts/plasmactl",
        "utilities/plasmactl/backends/plasmactl-integration",
        "software/web/app/layout.tsx",
        "software/web/app/plasma-api.ts",
        "software/web/next.config.ts",
    )
    for path in direct_gateway_ownership_paths:
        assert PUBLIC_PREVIEW_HOST not in _source(path), path


def test_windows_control_station_launcher_is_explicitly_managed() -> None:
    launcher = _source("packaging/windows/run-console.ps1")
    assert "$env:PLASMA_FLEET_UI_ENABLED = '1'" in launcher
    assert "$env:PLASMA_CONTROL_STATION_MODE = 'managed'" in launcher
    assert "$env:PLASMA_MANAGER_API_URL = 'http://127.0.0.1:18180'" in launcher


def test_web_default_and_storage_migration_are_same_origin_owned() -> None:
    session = _source("software/web/app/workspace-session.tsx")
    api = _source("software/web/app/plasma-api.ts")
    layout = _source("software/web/app/layout.tsx")
    # U10: the Console is Manager-managed only; no Browser-owned API base.
    assert "`${window.location.origin}/api/manager/ppu`" in session
    assert "NEXT_PUBLIC_PLASMA_API_URL" not in api + session
    assert 'window.localStorage.getItem(versionKey) === "3"' in layout
    assert 'window.localStorage.removeItem(apiKey);' in layout
    assert "legacyApiBases" not in layout


def test_integration_host_console_is_manager_managed_without_a_gateway_proxy() -> None:
    vite = _source("software/web/vite.config.ts")
    deployment = _source("utilities/plasmactl/backends/plasmactl-integration")
    # U10: no same-origin Vite proxy to a PPU Gateway; the Manager is required.
    assert "PLASMA_GATEWAY_PROXY_URL" not in vite
    assert "proxy:" not in vite
    assert 'engineering_mock_args=" --engineering-mock --engineering-mock-root $engineering_mock_root"' in deployment
    assert 'default_public_api_url=""' in deployment
    assert "current_config_version=7" in deployment
    assert 'manager_enabled="${PLASMA_MANAGER_ENABLED:-1}"' in deployment


def test_windows_installer_acceptance_proves_clean_install_managed_fail_closed() -> None:
    acceptance = _source("scripts/windows-control-station-installer-acceptance.py")
    assert "def _assert_clean_install_managed_routing()" in acceptance
    assert "_assert_clean_install_managed_routing()" in acceptance
    assert 'payload.get("managed") is not True' in acceptance
    assert 'payload.get("configured") is not False' in acceptance
    assert '"manager_bff_misconfigured"' in acceptance
    assert "Windows installer clean-install managed routing: PASS" in acceptance

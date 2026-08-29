from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "product-deploy.py"
spec = importlib.util.spec_from_file_location("product_deploy", SCRIPT)
assert spec is not None and spec.loader is not None
product_deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(product_deploy)


def lookup_from(mapping: dict[str, str | None]):
    return lambda name: mapping.get(name)


def fake_version_reader(path: str, args: tuple[str, ...]) -> str | None:
    assert args == ("--version",)
    return "v22.23.0" if path == "/usr/local/bin/node" else None


def test_version_tuple_accepts_node_style_versions() -> None:
    assert product_deploy._version_tuple("v22.23.0") == (22, 23, 0)
    assert product_deploy._version_tuple("node 22.13") == (22, 13, 0)
    assert product_deploy._version_tuple("unknown") is None


def test_control_station_contract_requires_macos_launchd_and_node(tmp_path: Path) -> None:
    library = tmp_path / "Library"
    library.mkdir()
    report = product_deploy.audit_control_station(
        system="Darwin",
        architecture="arm64",
        version_info=(3, 11, 15),
        home=tmp_path,
        lookup=lookup_from(
            {
                "launchctl": "/bin/launchctl",
                "node": "/usr/local/bin/node",
                "npm": None,
                "git": None,
                "timeout": None,
            }
        ),
        version_reader=fake_version_reader,
    )

    assert report.ready is True
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["operating-system"] == "pass"
    assert statuses["launchctl"] == "pass"
    assert statuses["node"] == "pass"
    assert statuses["npm"] == "info"
    assert statuses["git"] == "info"
    assert statuses["timeout"] == "info"


def test_control_station_fails_closed_on_linux() -> None:
    report = product_deploy.audit_control_station(
        system="Linux",
        architecture="x86_64",
        version_info=(3, 11, 15),
        home=Path("/tmp/nonexistent-product-deploy-home"),
        lookup=lookup_from({"launchctl": None, "node": None}),
        version_reader=lambda _path, _args: None,
    )

    assert report.ready is False
    failed = {check.name for check in report.checks if check.status == "fail"}
    assert "operating-system" in failed
    assert "launchctl" in failed
    assert "node" in failed


def test_ppu_contract_does_not_require_node_npm_or_git(tmp_path: Path) -> None:
    systemd_runtime = tmp_path / "systemd"
    systemd_runtime.mkdir()
    os_release = tmp_path / "os-release"
    os_release.write_text("NAME=Test Linux\n", encoding="utf-8")

    report = product_deploy.audit_ppu(
        system="Linux",
        architecture="armv7l",
        version_info=(3, 11, 15),
        lookup=lookup_from(
            {
                "systemctl": "/bin/systemctl",
                "ip": "/sbin/ip",
                "node": None,
                "npm": None,
                "git": None,
            }
        ),
        systemd_runtime=systemd_runtime,
        os_release=os_release,
    )

    assert report.ready is True
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["systemctl"] == "pass"
    assert statuses["node"] == "info"
    assert statuses["npm"] == "info"
    assert statuses["git"] == "info"


def test_ppu_fails_when_systemd_is_not_running(tmp_path: Path) -> None:
    report = product_deploy.audit_ppu(
        system="Linux",
        architecture="armv7l",
        version_info=(3, 11, 15),
        lookup=lookup_from({"systemctl": "/bin/systemctl", "ip": None}),
        systemd_runtime=tmp_path / "missing-systemd-runtime",
        os_release=tmp_path / "missing-os-release",
    )

    assert report.ready is False
    failed = {check.name for check in report.checks if check.status == "fail"}
    assert "systemd-runtime" in failed

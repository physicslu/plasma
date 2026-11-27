"""U10 D2: the B3 Deployment Engine borrows the Runtime Job-admission lease
from the Bootstrap service's configured Runtime control socket.

* production (default ServicePaths) argv is byte-for-byte unchanged;
* a configured socket reaches the Engine only through service configuration;
* a REST deployment body can never name or influence the socket;
* the Engine keeps the same trusted-socket lease (no idle authorization).
Host-only: no Runtime, no hardware, the subprocess is never executed.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_SOCKET = Path("/run/plasma-server/control.sock")
TARGET = {"platform": "mock", "board": "mock-site", "fpga_part": "none"}
UPLOAD_ID = "a" * 32
API_TX = "b" * 32
SHA = "c" * 64


def _load(name: str, filename: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service = _load("d2_bootstrap_service", "ppu-bootstrap-service.py")
engine = _load("d2_bootstrap_deployment", "ppu-bootstrap-deployment.py")


def _paths(tmp_path: Path, **overrides):
    target = tmp_path / "ppu-package-target.json"
    target.write_text(json.dumps(TARGET), encoding="utf-8")
    target.chmod(0o600)
    policy = tmp_path / "ppu-bundle-install-policy.json"
    policy.write_bytes((ROOT / "scripts" / "ppu-bundle-install-policy.json").read_bytes())
    policy.chmod(0o600)
    return service.ServicePaths(
        product_root=tmp_path / "product", state_root=tmp_path / "state",
        package_target_file=target, bundle_install_policy=policy,
        deployment_engine_script=ROOT / "scripts" / "ppu-bootstrap-deployment.py",
        z2_installer_script=ROOT / "scripts" / "ppu-z2-installer.py",
        **overrides,
    )


def _request(**extra):
    return {"api_transaction_id": API_TX, "archive_sha256": SHA, "target": dict(TARGET),
            "mode": "activate", "fpga_load": False, **extra}


def _capture_argv(monkeypatch, paths, request) -> list[str]:
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    with pytest.raises(service.BootstrapServiceError, match="B3_DEVICE_INSTALL_SUBPROCESS_FAILED"):
        service.run_bundle_install_subprocess(paths, UPLOAD_ID, request)
    assert len(calls) == 1
    return calls[0]


def test_production_default_socket_is_the_runtime_fixed_socket() -> None:
    assert service.ServicePaths().runtime_control_socket == PRODUCTION_SOCKET
    assert service.RUNTIME_CONTROL_SOCKET == PRODUCTION_SOCKET
    assert engine.RUNTIME_CONTROL_SOCKET == PRODUCTION_SOCKET


def test_default_argv_is_unchanged(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    argv = _capture_argv(monkeypatch, paths, _request())
    committed = service._upload_paths(paths, UPLOAD_ID).committed
    assert argv == [
        sys.executable, str(paths.deployment_engine_script),
        "--installer", str(paths.z2_installer_script),
        "--bootstrap-state-root", str(paths.state_root),
        "--product-root", str(paths.product_root),
        "install-bundle", "--release-artifact", str(committed),
        "--artifact-sha256", SHA,
        "--platform", "mock", "--board", "mock-site", "--fpga-part", "none",
        "--api-transaction-id", API_TX,
        "--mode", "activate",
    ]
    assert "--runtime-control-socket" not in argv


def test_configured_socket_is_passed_to_the_engine(tmp_path, monkeypatch) -> None:
    socket_path = tmp_path / "rt" / "control.sock"
    paths = _paths(tmp_path, runtime_control_socket=socket_path)
    argv = _capture_argv(monkeypatch, paths, _request())
    index = argv.index("--runtime-control-socket")
    assert argv[index + 1] == str(socket_path)
    # A top-level Engine option: before the subcommand, parsed by the Engine.
    assert index < argv.index("install-bundle")
    parsed = engine._parser().parse_args(argv[2:])
    assert parsed.runtime_control_socket == socket_path
    assert parsed.command == "install-bundle"


@pytest.mark.parametrize("key", ["runtime_control_socket", "socket", "control_socket"])
def test_rest_body_cannot_name_a_socket(tmp_path, monkeypatch, key) -> None:
    paths = _paths(tmp_path)
    called: list[object] = []
    monkeypatch.setattr(service.subprocess, "run", lambda *a, **k: called.append(a))
    with pytest.raises(service.BootstrapServiceError,
                       match="B3_INTERNAL_ADMISSION_IDENTITY_DENIED"):
        service.run_bundle_install_subprocess(
            paths, UPLOAD_ID, _request(**{key: str(tmp_path / "evil.sock")}))
    assert called == []


def test_rest_body_never_changes_the_configured_socket(tmp_path, monkeypatch) -> None:
    socket_path = tmp_path / "rt" / "control.sock"
    paths = _paths(tmp_path, runtime_control_socket=socket_path)
    argv = _capture_argv(monkeypatch, paths, _request())
    assert argv.count("--runtime-control-socket") == 1
    assert argv[argv.index("--runtime-control-socket") + 1] == str(socket_path)


def _coordinator(tmp_path: Path, **kwargs):
    root = tmp_path / "engine"
    return engine.DeploymentCoordinator(
        paths=engine.DeploymentPaths(
            bootstrap_state_root=root / "state", product_root=root / "product",
            config_root=root / "config", runtime_state_root=root / "rt",
            log_root=root / "log", systemd_root=root / "systemd"),
        installer=object(), **kwargs)


def test_engine_default_lease_is_the_helper_fixed_socket(tmp_path) -> None:
    co = _coordinator(tmp_path)
    helper = co._asset_helper()
    assert co._runtime_asset_lease(helper) is helper.held_runtime_asset_lease
    assert engine._parser().parse_args(
        ["install-bundle", "--release-artifact", "x", "--artifact-sha256", SHA,
         "--platform", "p", "--board", "b", "--fpga-part", "f",
         "--api-transaction-id", API_TX, "--mode", "activate"]).runtime_control_socket is None


def test_engine_configured_socket_keeps_the_trusted_socket_checks(tmp_path) -> None:
    missing = tmp_path / "absent" / "control.sock"
    co = _coordinator(tmp_path, runtime_control_socket=missing)
    helper = co._asset_helper()
    lease = co._runtime_asset_lease(helper)
    # Same connection-held lease: an absent Runtime is never an idle grant.
    with pytest.raises(helper.AssetSetError, match="ASSET_SET_CONTROL_SOCKET_UNAVAILABLE"):
        with lease():
            pass
    relative = _coordinator(tmp_path, runtime_control_socket=Path("control.sock"))
    with pytest.raises(helper.AssetSetError, match="ASSET_SET_CONTROL_SOCKET_UNTRUSTED"):
        with relative._runtime_asset_lease(helper)():
            pass


def test_injected_host_lease_still_wins(tmp_path) -> None:
    sentinel = object()
    co = _coordinator(tmp_path, quiescence_lease=sentinel,
                      runtime_control_socket=tmp_path / "control.sock")
    assert co._runtime_asset_lease(co._asset_helper()) is sentinel

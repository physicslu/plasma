from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-bootstrap-deployment.py"
SPEC = importlib.util.spec_from_file_location("ppu_bootstrap_deployment", SCRIPT)
assert SPEC and SPEC.loader
deployment = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deployment
SPEC.loader.exec_module(deployment)


class FakeInstallPaths:
    def __init__(self, *, product_root, config_root, state_root, log_root, systemd_root):
        self.product_root = Path(product_root)
        self.config_root = Path(config_root)
        self.state_root = Path(state_root)
        self.log_root = Path(log_root)
        self.systemd_root = Path(systemd_root)

    @property
    def releases_root(self):
        return self.product_root / "releases"

    @property
    def current(self):
        return self.product_root / "current"


class FakeInstaller:
    InstallPaths = FakeInstallPaths

    def __init__(self, *, fail_verify=False, fail_install=None):
        self.fail_verify = fail_verify
        self.fail_install = fail_install
        self.calls = []
        self.health_called = False

    def verify_release(self, artifact, *, sidecar, extract_to):
        self.calls.append("verify")
        if self.fail_verify:
            raise RuntimeError("bad digest")
        Path(extract_to).mkdir(parents=True)
        return SimpleNamespace(
            release_id="1.2.3-aaaaaaaaaaaa",
            archive_sha256="d" * 64,
        )

    def validate_plasma_python(self, path, *, product_root):
        self.calls.append("python")
        return SimpleNamespace(path=path, version="3.12.13", architecture="armv7l", releaselevel="final")

    def _require_target_baseline(self):
        self.calls.append("baseline")

    def _previous_current(self, current):
        self.calls.append("previous")
        return Path("/opt/plasma/releases/1.2.2-bbbbbbbbbbbb")

    def _copy_release(self, verified, target):
        self.calls.append("stage")
        Path(target).mkdir(parents=True, exist_ok=True)

    def _health_ready(self, host):
        self.calls.append("health")
        self.health_called = True
        return {"ok": True, "gateway": "alive", "execution": "ready"}

    def install_release(self, verified, **kwargs):
        self.calls.append("activate")
        if self.fail_install:
            raise RuntimeError(self.fail_install)
        health = kwargs["health_check"](kwargs["gateway_host"])
        return {
            "result": "PASS",
            "release_id": verified.release_id,
            "gateway_readiness": health,
        }


def _paths(tmp_path: Path):
    return deployment.DeploymentPaths(
        bootstrap_state_root=tmp_path / "bootstrap",
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        runtime_state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )


def _request(tmp_path: Path):
    artifact = tmp_path / "release.tar.gz"
    sidecar = tmp_path / "release.tar.gz.sha256"
    python = tmp_path / "opt" / "plasma" / "python" / "3.12.13" / "bin" / "python3"
    artifact.write_bytes(b"artifact")
    sidecar.write_text("sidecar", encoding="utf-8")
    python.parent.mkdir(parents=True)
    python.write_text("python", encoding="utf-8")
    return deployment.DeploymentRequest(
        release_artifact=artifact,
        sidecar=sidecar,
        plasma_python=python,
        gateway_host="192.168.2.99",
        ppu_id="ppu-01",
        facility_id="lab",
        display_name="PPU 01",
    )


def _coordinator(tmp_path: Path, installer):
    counter = iter([100.0 + i for i in range(30)])
    return deployment.DeploymentCoordinator(
        paths=_paths(tmp_path),
        installer=installer,
        clock=lambda: next(counter),
        transaction_id_factory=lambda: "tx-001",
    )


def test_successful_transaction_orders_verify_stage_activate_health(tmp_path: Path):
    installer = FakeInstaller()
    coordinator = _coordinator(tmp_path, installer)
    result = coordinator.execute(_request(tmp_path))

    assert result["result"] == "PASS"
    assert result["transaction"]["transaction_id"] == "tx-001"
    assert result["transaction"]["state"] == "runtime_active"
    assert result["transaction"]["release_id"] == "1.2.3-aaaaaaaaaaaa"
    assert result["capabilities"]["fpga_update"] is False
    assert installer.calls == [
        "verify",
        "python",
        "baseline",
        "previous",
        "stage",
        "activate",
        "health",
    ]

    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "runtime_active"
    assert journal["sequence"] >= 8
    assert journal["previous_release"].endswith("1.2.2-bbbbbbbbbbbb")
    assert journal["error_code"] is None


def test_verification_failure_is_terminal_and_never_stages(tmp_path: Path):
    installer = FakeInstaller(fail_verify=True)
    coordinator = _coordinator(tmp_path, installer)

    with pytest.raises(deployment.DeploymentError, match="verification failed"):
        coordinator.execute(_request(tmp_path))

    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "verify_failed"
    assert journal["error_code"] == "verification_failed"
    assert installer.calls == ["verify"]


def test_activation_failure_with_installer_rollback_is_classified_rolled_back(tmp_path: Path):
    installer = FakeInstaller(fail_install="activation failed and previous configuration/release was restored")
    coordinator = _coordinator(tmp_path, installer)

    with pytest.raises(deployment.DeploymentError, match="deployment failed"):
        coordinator.execute(_request(tmp_path))

    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "rolled_back"
    assert journal["error_code"] == "activation_failed_rolled_back"


def test_rollback_failure_requires_recovery(tmp_path: Path):
    installer = FakeInstaller(fail_install="activation failed; rollback also failed")
    coordinator = _coordinator(tmp_path, installer)

    with pytest.raises(deployment.DeploymentError):
        coordinator.execute(_request(tmp_path))

    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "recovery_required"
    assert journal["error_code"] == "rollback_failed"


def test_nonblocking_lock_prevents_overlapping_deployments(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.bootstrap_state_root.mkdir(parents=True)
    installer = FakeInstaller()
    coordinator = deployment.DeploymentCoordinator(paths=paths, installer=installer)

    import fcntl

    with paths.lock.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(deployment.DeploymentError, match="another PPU deployment"):
            coordinator.execute(_request(tmp_path))

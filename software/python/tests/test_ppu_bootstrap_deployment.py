from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from .ppu_control_plane_fixture import verify_real_control_plane

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

    def verify_release(self, artifact, *, sidecar, extract_to):
        self.calls.append("verify")
        if self.fail_verify:
            raise RuntimeError("bad digest")
        Path(extract_to).mkdir(parents=True)
        return SimpleNamespace(release_id="1.2.3-aaaaaaaaaaaa", archive_sha256="d" * 64,
                               git_sha="a" * 40)

    def verify_control_plane(self, verified):
        return verify_real_control_plane(verified)

    def _systemctl(self, *args):
        self.calls.append(("systemctl", *args))

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
        return {"ok": True, "gateway": "alive", "execution": "ready"}

    def install_release(self, verified, **kwargs):
        self.calls.append("activate")
        if self.fail_install:
            if "restored" in self.fail_install:
                kwargs["on_rollback"]()
            raise RuntimeError(self.fail_install)
        health = kwargs["health_check"](kwargs["gateway_host"])
        return {"result": "PASS", "release_id": verified.release_id, "gateway_readiness": health}


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
    python.parent.mkdir(parents=True, exist_ok=True)
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


def _coordinator(tmp_path: Path, installer, runtime_restart_quiesce=None):
    counter = iter([100.0 + i for i in range(30)])
    if runtime_restart_quiesce is None:
        def runtime_restart_quiesce():
            installer.calls.append("quiesce")
            return {"token": "quiesce-test", "ttl_s": 60}
    return deployment.DeploymentCoordinator(
        paths=_paths(tmp_path), installer=installer,
        clock=lambda: next(counter), transaction_id_factory=lambda: "tx-001",
        runtime_restart_quiesce=runtime_restart_quiesce,
    )


def _write_journal(tmp_path: Path, *, state: str, error_code=None, error_message=None, mode=0o600):
    path = _paths(tmp_path).journal
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "transaction_id": "tx-old", "state": state, "sequence": 4,
        "started_at_epoch_s": 10.0, "updated_at_epoch_s": 11.0,
        "release_artifact": "/tmp/old-release.tar.gz", "release_id": "old-release",
        "artifact_sha256": "a" * 64, "previous_release": "/opt/plasma/releases/older",
        "error_code": error_code, "error_message": error_message,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


def test_successful_transaction_orders_verify_stage_activate_health(tmp_path: Path):
    installer = FakeInstaller()
    coordinator = _coordinator(tmp_path, installer)
    result = coordinator.execute(_request(tmp_path))
    assert result["result"] == "PASS"
    assert result["transaction"]["state"] == "runtime_active"
    assert result["transaction"]["api_transaction_id"] is None  # Local CLI remains independent.
    assert result["capabilities"]["fpga_update"] is False
    assert installer.calls == ["verify", "python", "baseline", "previous", "stage", "quiesce", "activate", "health"]
    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "runtime_active"
    assert coordinator.paths.journal.stat().st_mode & 0o077 == 0
    assert coordinator.paths.lock.stat().st_mode & 0o077 == 0


def test_api_transaction_id_is_recorded_by_the_locked_coordinator(tmp_path: Path):
    coordinator = _coordinator(tmp_path, FakeInstaller())
    api_id = "f" * 32
    result = coordinator.execute(replace(_request(tmp_path), api_transaction_id=api_id))
    assert result["transaction"]["api_transaction_id"] == api_id
    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["api_transaction_id"] == api_id
    assert journal["transaction_id"] == result["transaction"]["transaction_id"]


@pytest.mark.parametrize("api_id", ["", "f" * 31, "F" * 32, "unknown", True])
def test_invalid_api_transaction_id_is_rejected_before_coordinator_mutation(tmp_path: Path, api_id):
    coordinator = _coordinator(tmp_path, FakeInstaller())
    with pytest.raises(deployment.DeploymentError, match="API transaction identity"):
        coordinator.execute(replace(_request(tmp_path), api_transaction_id=api_id))
    assert not coordinator.paths.journal.exists()


def test_verification_failure_is_terminal_and_never_stages(tmp_path: Path):
    installer = FakeInstaller(fail_verify=True)
    coordinator = _coordinator(tmp_path, installer)
    with pytest.raises(deployment.DeploymentError, match="verification failed"):
        coordinator.execute(_request(tmp_path))
    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "verify_failed"
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


def test_interrupted_transaction_is_promoted_to_recovery_required_before_new_work(tmp_path: Path):
    journal_path = _write_journal(tmp_path, state="activating")
    installer = FakeInstaller()
    coordinator = _coordinator(tmp_path, installer)
    with pytest.raises(deployment.DeploymentError, match="interrupted in state activating"):
        coordinator.execute(_request(tmp_path))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["state"] == "recovery_required"
    assert journal["error_code"] == "interrupted_transaction"
    assert installer.calls == []


def test_recovery_required_journal_blocks_retry_without_overwriting_evidence(tmp_path: Path):
    journal_path = _write_journal(tmp_path, state="recovery_required", error_code="rollback_failed", error_message="manual recovery required")
    before = journal_path.read_text(encoding="utf-8")
    coordinator = _coordinator(tmp_path, FakeInstaller())
    with pytest.raises(deployment.DeploymentError, match="requires recovery"):
        coordinator.execute(_request(tmp_path))
    assert journal_path.read_text(encoding="utf-8") == before


def test_corrupt_or_overpermissive_journal_fails_closed(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.bootstrap_state_root.mkdir(parents=True, exist_ok=True)
    paths.journal.write_text("not-json\n", encoding="utf-8")
    paths.journal.chmod(0o600)
    with pytest.raises(deployment.DeploymentError, match="journal is unreadable"):
        _coordinator(tmp_path, FakeInstaller()).execute(_request(tmp_path))
    _write_journal(tmp_path, state="runtime_active", mode=0o644)
    with pytest.raises(deployment.DeploymentError, match="permissions are too broad"):
        _coordinator(tmp_path, FakeInstaller()).execute(_request(tmp_path))


def test_upgrade_quiesce_denial_is_terminal_before_activation(tmp_path: Path):
    installer = FakeInstaller()

    def busy():
        installer.calls.append("quiesce")
        raise RuntimeError("RUNTIME_RESTART_QUIESCE_NOT_GRANTED: PPU execution is active")

    coordinator = _coordinator(tmp_path, installer, runtime_restart_quiesce=busy)
    with pytest.raises(deployment.DeploymentError, match="runtime upgrade quiesce denied"):
        coordinator.execute(_request(tmp_path))
    assert installer.calls == ["verify", "python", "baseline", "previous", "stage", "quiesce"]
    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "verify_failed"
    assert journal["error_code"] == "runtime_quiesce_denied"
    # A refused upgrade leaves the PPU deployable again (no recovery_required).
    assert deployment.DeploymentCoordinator(paths=_paths(tmp_path), installer=FakeInstaller(), runtime_restart_quiesce=lambda: {}).execute(_request(tmp_path))["result"] == "PASS"


def test_fresh_install_needs_no_runtime_quiesce(tmp_path: Path):
    class FreshInstaller(FakeInstaller):
        def _previous_current(self, current):
            self.calls.append("previous")
            return None

    installer = FreshInstaller()

    def must_not_run():
        raise AssertionError("fresh install has no running Runtime to quiesce")

    result = _coordinator(tmp_path, installer, runtime_restart_quiesce=must_not_run).execute(_request(tmp_path))
    assert result["result"] == "PASS"
    assert "quiesce" not in installer.calls


def test_kit_standalone_upgrade_without_runtime_socket_is_terminal_not_recovery(tmp_path: Path, monkeypatch):
    """Regression for Z2 #1282 D2: the Runtime upgrade runs this module from the
    Z2 PS kit scripts/ directory (no sibling helpers). A missing helper or an
    unavailable Runtime gate must end verify_failed, never recovery_required."""
    import importlib.util
    import shutil
    import sys

    kit_scripts = tmp_path / "kit-scripts"
    kit_scripts.mkdir()
    target = kit_scripts / "ppu-bootstrap-deployment.py"
    shutil.copyfile(Path(deployment.__file__), target)
    spec = importlib.util.spec_from_file_location("plasma_kit_standalone_deployment_tx", target)
    standalone = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = standalone
    spec.loader.exec_module(standalone)
    monkeypatch.setattr(standalone, "RUNTIME_CONTROL_SOCKET", tmp_path / "absent" / "control.sock")

    installer = FakeInstaller()
    counter = iter([100.0 + i for i in range(30)])
    coordinator = standalone.DeploymentCoordinator(
        paths=_paths(tmp_path), installer=installer,
        clock=lambda: next(counter), transaction_id_factory=lambda: "tx-kit",
    )
    with pytest.raises(standalone.DeploymentError, match="RUNTIME_CONTROL_SOCKET_UNAVAILABLE"):
        coordinator.execute(_request(tmp_path))
    assert "activate" not in installer.calls
    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "verify_failed"
    assert journal["error_code"] == "runtime_quiesce_denied"

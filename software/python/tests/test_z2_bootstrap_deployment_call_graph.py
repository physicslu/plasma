from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
Z2_BACKEND = ROOT / "scripts" / "plasmactl-z2-ps"
BOOTSTRAP_KIT = ROOT / "scripts" / "ppu-bootstrap-kit.py"
BOOTSTRAP_DEPLOYMENT = ROOT / "scripts" / "ppu-bootstrap-deployment.py"
Z2_RELEASE = ROOT / ".github" / "workflows" / "z2-ps-release.yml"

SPEC = importlib.util.spec_from_file_location(
    "ppu_bootstrap_deployment_qualification", BOOTSTRAP_DEPLOYMENT
)
assert SPEC and SPEC.loader
deployment = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deployment
SPEC.loader.exec_module(deployment)


class QualificationInstallPaths:
    def __init__(self, *, product_root, config_root, state_root, log_root, systemd_root):
        self.product_root = Path(product_root)
        self.config_root = Path(config_root)
        self.state_root = Path(state_root)
        self.log_root = Path(log_root)
        self.systemd_root = Path(systemd_root)

    @property
    def releases_root(self) -> Path:
        return self.product_root / "releases"

    @property
    def current(self) -> Path:
        return self.product_root / "current"


class QualificationInstaller:
    InstallPaths = QualificationInstallPaths

    def __init__(self, previous: Path | None):
        self.previous = previous
        self.real_health_calls = 0

    def verify_release(self, artifact, *, sidecar, extract_to):
        Path(extract_to).mkdir(parents=True)
        return SimpleNamespace(release_id="1.2.3-cccccccccccc", archive_sha256="d" * 64)

    def validate_plasma_python(self, path, *, product_root):
        return SimpleNamespace(path=path, version="3.12.13", architecture="armv7l", releaselevel="final")

    def _require_target_baseline(self):
        return None

    def _previous_current(self, current):
        return self.previous

    def _copy_release(self, verified, target):
        Path(target).mkdir(parents=True, exist_ok=True)

    def _health_ready(self, host):
        self.real_health_calls += 1
        return {"ok": True, "gateway": "alive", "execution": "ready"}

    def install_release(self, verified, **kwargs):
        try:
            kwargs["health_check"](kwargs["gateway_host"])
        except Exception as exc:
            raise RuntimeError(
                f"activation failed and previous configuration/release was restored: {exc}"
            ) from exc
        raise AssertionError("qualification health-check injection did not fire")


def _qualification_request(tmp_path: Path):
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
        ppu_id="z2-hil",
        facility_id="lab",
        display_name="PYNQ-Z2 HIL",
        qualification_fail_health_check=True,
    )


def _qualification_coordinator(tmp_path: Path, installer: QualificationInstaller):
    return deployment.DeploymentCoordinator(
        paths=deployment.DeploymentPaths(
            bootstrap_state_root=tmp_path / "bootstrap",
            product_root=tmp_path / "opt" / "plasma",
            config_root=tmp_path / "etc" / "plasma",
            runtime_state_root=tmp_path / "var" / "lib" / "plasma",
            log_root=tmp_path / "var" / "log" / "plasma",
            systemd_root=tmp_path / "etc" / "systemd" / "system",
        ),
        installer=installer,
        transaction_id_factory=lambda: "qualification-tx",
    )


def test_z2_backend_routes_activation_through_durable_coordinator():
    source = Z2_BACKEND.read_text(encoding="utf-8")
    assert "PLASMA_Z2_BOOTSTRAP_DEPLOYMENT" in source
    assert "ppu-bootstrap-deployment.py" in source
    assert 'python3 "$deployment_tool" "${args[@]}"' in source
    assert 'python3 "$ppu_installer" "${args[@]}"' not in source
    assert '--installer "$ppu_installer"' in source
    assert '--product-root "$product_root"' in source


def test_bootstrap_kit_requires_current_durable_coordinator_and_installer_core():
    source = BOOTSTRAP_KIT.read_text(encoding="utf-8")
    assert 'scripts / "ppu-bootstrap-deployment.py"' in source
    assert 'scripts / "ppu-z2-installer-core.py"' in source
    assert "missing required deployment tooling" in source


def test_z2_release_candidate_packages_and_tests_durable_coordinator():
    source = Z2_RELEASE.read_text(encoding="utf-8")
    assert source.count('"scripts/ppu-bootstrap-deployment.py"') >= 2
    assert "python -m py_compile scripts/ppu-bootstrap-deployment.py" in source
    assert "software/python/tests/test_z2_bootstrap_deployment_call_graph.py" in source
    assert 'cp scripts/ppu-bootstrap-deployment.py "$root/scripts/ppu-bootstrap-deployment.py"' in source
    assert '"$root/scripts/ppu-bootstrap-deployment.py"' in source


def test_rollback_qualification_injection_is_packaged_but_not_a_normal_plasmactl_option():
    deployment_source = BOOTSTRAP_DEPLOYMENT.read_text(encoding="utf-8")
    backend_source = Z2_BACKEND.read_text(encoding="utf-8")
    assert "--qualification-fail-health-check" in deployment_source
    assert deployment.QUALIFICATION_HEALTH_FAILURE in deployment_source
    assert "--qualification-fail-health-check" not in backend_source


def test_rollback_qualification_injection_reaches_real_rollback_classification(tmp_path: Path):
    previous = Path("/opt/plasma/releases/1.2.2-bbbbbbbbbbbb")
    installer = QualificationInstaller(previous=previous)
    coordinator = _qualification_coordinator(tmp_path, installer)

    with pytest.raises(deployment.DeploymentError, match=deployment.QUALIFICATION_HEALTH_FAILURE):
        coordinator.execute(_qualification_request(tmp_path))

    journal = json.loads(coordinator.paths.journal.read_text(encoding="utf-8"))
    assert journal["state"] == "rolled_back"
    assert journal["error_code"] == "activation_failed_rolled_back"
    assert journal["previous_release"] == str(previous)
    assert deployment.QUALIFICATION_HEALTH_FAILURE in journal["error_message"]
    assert installer.real_health_calls == 0


def test_rollback_qualification_injection_requires_existing_previous_release(tmp_path: Path):
    installer = QualificationInstaller(previous=None)
    coordinator = _qualification_coordinator(tmp_path, installer)

    with pytest.raises(deployment.DeploymentError, match="requires an existing previous release"):
        coordinator.execute(_qualification_request(tmp_path))

    assert not coordinator.paths.journal.exists()

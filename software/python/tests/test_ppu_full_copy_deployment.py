"""PR-B Full-Copy Deployment: Runtime + Bootstrap + Site Worker v3 + Adapter.

Host-only. One Bootstrap deployment transaction (same coordinator, lock and
journal) verifies the Runtime release's same-commit control plane, installs it
into the Bootstrap tree with a durable snapshot, activates the Runtime through
the existing installer and restores both on failure. Nothing here touches
systemd, Z2, FPGA or a DUT.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import types
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from .ppu_control_plane_fixture import (
    PROTOCOL, installed_control_plane, real_control_plane, verify_real_control_plane,
    write_control_plane,
)
from .test_ppu_bootstrap_deployment import FakeInstaller, _paths, _request, deployment
from .test_ppu_z2_installer import _fake_release, installer as z2_installer

ROOT = Path(__file__).resolve().parents[3]
CORE, _RUNTIME, _MANIFEST = real_control_plane()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _sha(p)
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


@lru_cache(maxsize=1)
def _bootstrap_installer():
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "ppu_full_copy_test_bootstrap_installer", ROOT / "scripts" / "ppu-bootstrap-installer.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- fixtures


class FullCopyInstaller(FakeInstaller):
    """Fake activation; real control-plane verification on the repo's files."""

    def __init__(self, *, fail_install=None, tamper_snapshot=False, **kwargs):
        super().__init__(fail_install=fail_install, **kwargs)
        self.tamper_snapshot = tamper_snapshot
        self.seen_at_activation: dict[str, str] | None = None
        self.install_root: Path | None = None

    def install_release(self, verified, **kwargs):
        self.calls.append("activate")
        if self.install_root is not None:
            self.seen_at_activation = _tree(self.install_root)
        if self.fail_install:
            # Same contract as the real core: control plane restored first,
            # its failure is a rollback failure.
            if self.tamper_snapshot:
                for stored in self.snapshot_root.rglob("files/*"):
                    if stored.is_file():
                        stored.write_bytes(b"corrupted")
            try:
                kwargs["on_rollback"]()
            except Exception as exc:
                raise RuntimeError(f"activation failed; rollback also failed ({exc})") from exc
            raise RuntimeError("activation failed and previous configuration/release was restored")
        health = kwargs["health_check"](kwargs["gateway_host"])
        return {"result": "PASS", "release_id": verified.release_id, "gateway_readiness": health}


def _coordinator(tmp_path: Path, installer, quiesce=None):
    counter = iter([100.0 + i for i in range(60)])
    installer.install_root = _paths(tmp_path).bootstrap_install_root
    installer.snapshot_root = _paths(tmp_path).control_plane_snapshots
    return deployment.DeploymentCoordinator(
        paths=_paths(tmp_path), installer=installer,
        clock=lambda: next(counter), transaction_id_factory=lambda: "tx-full-copy",
        runtime_restart_quiesce=quiesce or (lambda: installer.calls.append("quiesce")),
    )


def _seed_device(tmp_path: Path) -> dict[str, Path]:
    """Previous Bootstrap tree plus device identity / recovery / Site state."""
    paths = _paths(tmp_path)
    old = paths.bootstrap_install_root
    shutil.copytree(_RUNTIME / "control-plane", old)
    (old / "control-plane-manifest.json").unlink()
    (old / "ppu_site_worker.py").write_text('PROTOCOL = "plasma.ppu.site-worker.v2"\n')
    (old / "ppu_asset_set.py").write_text("# previous asset helper without resource identity\n")
    (old / "ppu-bootstrap-installer.py").unlink()  # pre-Full-Copy factory lacked it
    state = {
        "controller": paths.bootstrap_state_root / "controller" / "controller.json",
        "enrollment": paths.bootstrap_state_root / "enrollment.json",
        "seal": tmp_path / "var" / "lib" / "plasma-site-worker" / "seals" / "site-2.json",
        "engine": paths.config_root / "site-worker-engine.json",
        "fpga": tmp_path / "var" / "lib" / "plasma-privileged" / "fpga-deployment-state.json",
        "active_set": paths.product_root / "assets" / "active.json",
    }
    for name, path in state.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if name == "engine":
            path.write_text(json.dumps({"adapter_driver": "plasma_swd", "driver_abi": 5}))
        else:
            path.write_text(json.dumps({"state": name, "safe_off": "SAFE_OFF_MODE_OFF_VERIFIED"}))
    systemd = paths.systemd_root
    systemd.mkdir(parents=True, exist_ok=True)
    for unit in ("plasma-site-worker.service", "plasma-package-control.service"):
        (systemd / unit).write_text("[Service]\n")
    return state


# ------------------------------------------------------------- release-side contract


def test_real_control_plane_is_the_bootstrap_installer_file_set_and_one_protocol():
    plane = verify_real_control_plane()
    assert set(plane.files) == set(_bootstrap_installer().control_plane_files())
    assert "ppu-bootstrap-installer.py" in plane.files
    from plasma_interfaces.site_worker_c3 import PROTOCOL as runtime_protocol
    assert plane.site_worker_protocol == runtime_protocol == "plasma.ppu.site-worker.v3"
    assert plane.manifest["site_adapter"] == {"module": "ppu_site_adapter_abi5.py",
                                              "driver_abi": {"plasma_swd": [5]}}
    for name, digest in plane.files.items():
        source = ROOT / name if name.startswith(("pl/", "software/")) else ROOT / "scripts" / name
        assert _sha(source) == digest, name


def test_release_verifier_requires_the_bundled_control_plane(tmp_path: Path):
    good = z2_installer.verify_release(_fake_release(tmp_path / "good"),
                                       extract_to=tmp_path / "good-x")
    assert z2_installer.verify_control_plane(good).site_worker_protocol == PROTOCOL
    with pytest.raises(z2_installer.Z2InstallerError, match="RELEASE_CONTROL_PLANE_MISSING"):
        z2_installer.verify_release(_fake_release(tmp_path / "old", control_plane=False),
                                    extract_to=tmp_path / "old-x")


def _runtime(tmp_path: Path, **kwargs) -> tuple[Path, dict]:
    runtime = tmp_path / "runtime"
    return runtime, {"control_plane": write_control_plane(runtime, **kwargs)}


def _rewrite_manifest(runtime: Path, mutate) -> None:
    path = runtime / "control-plane" / "control-plane-manifest.json"
    manifest = json.loads(path.read_text())
    mutate(manifest)
    path.write_text(json.dumps(manifest))


@pytest.mark.parametrize("case,code", [
    ("runtime_v3_worker_v2", "RELEASE_SITE_WORKER_PROTOCOL_MISMATCH"),
    ("tampered_file", "SHA-256 mismatch"),
    ("unlisted_file", "file set mismatch"),
    ("missing_required", "RELEASE_CONTROL_PLANE_INCOMPLETE"),
    ("unsafe_path", "unsafe control-plane path"),
    ("bad_abi", "site_adapter ABI"),
    ("worker_source_disagrees", "bundled Worker source"),
    ("undeclared", "RELEASE_CONTROL_PLANE_MISSING"),
    ("bad_schema", "manifest schema"),
])
def test_control_plane_verifier_rejects(tmp_path: Path, case: str, code: str):
    runtime, manifest = _runtime(tmp_path, worker_protocol=(
        "plasma.ppu.site-worker.v2" if case == "runtime_v3_worker_v2" else None))
    root = runtime / "control-plane"
    if case == "tampered_file":
        (root / "ppu_site_adapter_abi5.py").write_text("# swapped adapter\n")
    elif case == "unlisted_file":
        (root / "ppu_extra.py").write_text("# not in manifest\n")
    elif case == "missing_required":
        _rewrite_manifest(runtime, lambda m: m["files"].pop("ppu_site_engine.py"))
        (root / "ppu_site_engine.py").unlink()
    elif case == "unsafe_path":
        _rewrite_manifest(runtime, lambda m: m["files"].update({"../escape.py": "0" * 64}))
    elif case == "bad_abi":
        _rewrite_manifest(runtime, lambda m: m["site_adapter"].update(driver_abi={"plasma_swd": ["5"]}))
    elif case == "worker_source_disagrees":
        (root / "ppu_site_worker.py").write_text('PROTOCOL = "plasma.ppu.site-worker.v2"\n')
        digest = _sha(root / "ppu_site_worker.py")
        _rewrite_manifest(runtime, lambda m: m["files"].update({"ppu_site_worker.py": digest}))
    elif case == "undeclared":
        manifest = {}
    elif case == "bad_schema":
        _rewrite_manifest(runtime, lambda m: m.update(schema="plasma.ppu.control-plane.v0"))
    with pytest.raises(CORE.Z2InstallerError, match=re.escape(code)):
        CORE.verify_control_plane_tree(runtime, manifest)


def test_factory_bundle_ci_ships_every_bootstrap_script():
    """The factory bundle (refresh path) and the Runtime release ship one set."""
    workflow = (ROOT / ".github" / "workflows" / "ppu-bootstrap.yml").read_text()
    module = _bootstrap_installer()
    for name in (*module.REQUIRED_SCRIPTS, *module.B3_FILES):
        if name.endswith(".json"):
            assert f"cp scripts/{name}" in workflow, name
        else:
            assert f"scripts/{name} \\" in workflow, name


# --------------------------------------------------------------- coordinator: success


def test_full_copy_installs_runtime_and_same_commit_control_plane_in_one_transaction(tmp_path: Path):
    state = _seed_device(tmp_path)
    state_before = {name: path.read_bytes() for name, path in state.items()}
    installer = FullCopyInstaller()
    paths = _paths(tmp_path)
    seen_at_quiesce: dict[str, str] = {}

    def quiesce():
        installer.calls.append("quiesce")
        seen_at_quiesce.update(_tree(paths.bootstrap_install_root))

    old_tree = _tree(paths.bootstrap_install_root)
    result = _coordinator(tmp_path, installer, quiesce).execute(_request(tmp_path))

    assert result["result"] == "PASS"
    assert installer.calls == ["verify", "python", "baseline", "previous", "stage", "quiesce",
                               "activate", "health"]
    # Quiesce precedes any control-plane change; the Runtime restart sees the new set.
    assert seen_at_quiesce == old_tree
    plane = verify_real_control_plane()
    installed = _tree(paths.bootstrap_install_root)
    assert {k: v for k, v in installed.items() if k != "control-plane.json"} == dict(plane.files)
    assert installer.seen_at_activation == installed
    identity = json.loads((paths.bootstrap_install_root / "control-plane.json").read_text())
    assert identity["release_git_sha"] == "a" * 40
    assert identity["release_id"] == "1.2.3-aaaaaaaaaaaa"
    assert identity["site_worker_protocol"] == "plasma.ppu.site-worker.v3"
    assert identity["control_plane_manifest_sha256"] == plane.manifest_sha256
    assert result["control_plane"]["identity"] == identity
    assert {"ppu_site_worker.py", "ppu_asset_set.py", "ppu-bootstrap-installer.py"} <= set(
        result["control_plane"]["changed_files"])
    assert result["control_plane"]["bootstrap_service_restart_required"] is True
    journal = json.loads(paths.journal.read_text())
    assert journal["state"] == "runtime_active" and journal["source_commit"] == "a" * 40
    # Device identity, controller, enrollment, seals, engine pin, FPGA and Active Set untouched.
    assert {name: path.read_bytes() for name, path in state.items()} == state_before
    snapshot = Path(result["control_plane"]["snapshot"])
    assert snapshot.parent == paths.control_plane_snapshots
    assert snapshot.stat().st_mode & 0o077 == 0


def test_redeploying_the_same_release_changes_nothing_and_needs_no_bootstrap_restart(tmp_path: Path):
    _seed_device(tmp_path)
    _coordinator(tmp_path, FullCopyInstaller()).execute(_request(tmp_path))
    paths = _paths(tmp_path)
    before = _tree(paths.bootstrap_install_root)
    again = deployment.DeploymentCoordinator(
        paths=paths, installer=FullCopyInstaller(),
        clock=lambda: 500.0, transaction_id_factory=lambda: "tx-second",
        runtime_restart_quiesce=lambda: None).execute(_request(tmp_path))
    assert again["control_plane"]["changed_files"] == []
    assert again["control_plane"]["bootstrap_service_restart_required"] is False
    after = _tree(paths.bootstrap_install_root)
    before.pop("control-plane.json"), after.pop("control-plane.json")
    assert before == after
    # Only the latest terminal transaction keeps a snapshot.
    assert [p.name for p in paths.control_plane_snapshots.iterdir()] == ["tx-second"]


# ---------------------------------------------------------- coordinator: rollback


def test_runtime_activation_failure_restores_previous_control_plane_and_worker(tmp_path: Path):
    state = _seed_device(tmp_path)
    paths = _paths(tmp_path)
    old_tree = _tree(paths.bootstrap_install_root)
    installer = FullCopyInstaller(fail_install=True)
    with pytest.raises(deployment.DeploymentError, match="deployment failed"):
        _coordinator(tmp_path, installer).execute(_request(tmp_path))
    assert _tree(paths.bootstrap_install_root) == old_tree  # byte-exact, new files removed
    assert not (paths.bootstrap_install_root / "control-plane.json").exists()
    assert installer.calls[-2:] == [("systemctl", "restart", "plasma-package-control.service"),
                                    ("systemctl", "restart", "plasma-site-worker.service")]
    journal = json.loads(paths.journal.read_text())
    assert journal["state"] == "rolled_back"
    assert journal["error_code"] == "activation_failed_rolled_back"
    assert json.loads(state["seal"].read_text())["state"] == "seal"


def test_control_plane_rollback_failure_is_recovery_required_and_never_retried(tmp_path: Path):
    _seed_device(tmp_path)
    paths = _paths(tmp_path)
    installer = FullCopyInstaller(fail_install=True, tamper_snapshot=True)
    with pytest.raises(deployment.DeploymentError):
        _coordinator(tmp_path, installer).execute(_request(tmp_path))
    journal = json.loads(paths.journal.read_text())
    assert journal["state"] == "recovery_required"
    assert journal["error_code"] == "rollback_failed"
    snapshot = paths.control_plane_snapshots / "tx-full-copy"
    assert (snapshot / "index.json").is_file()  # preserved for guided recovery
    retry = FullCopyInstaller()
    with pytest.raises(deployment.DeploymentError, match="requires recovery"):
        _coordinator(tmp_path, retry).execute(_request(tmp_path))
    assert retry.calls == []  # fenced: nothing verified, staged or resent
    assert (snapshot / "index.json").is_file()


def test_control_plane_install_failure_restores_files_without_activation(tmp_path: Path, monkeypatch):
    _seed_device(tmp_path)
    paths = _paths(tmp_path)
    old_tree = _tree(paths.bootstrap_install_root)
    installer = FullCopyInstaller()
    coordinator = _coordinator(tmp_path, installer)

    def half_install(plane, verified, transaction_id):
        (paths.bootstrap_install_root / "ppu_site_worker.py").write_text("# half written\n")
        (paths.bootstrap_install_root / "ppu-bootstrap-installer.py").write_text("# new\n")
        raise OSError("disk full")
    monkeypatch.setattr(coordinator, "_install_control_plane", half_install)
    with pytest.raises(deployment.DeploymentError, match="previous restored"):
        coordinator.execute(_request(tmp_path))
    assert _tree(paths.bootstrap_install_root) == old_tree
    assert "activate" not in installer.calls
    assert not any(isinstance(c, tuple) for c in installer.calls)  # Worker never restarted
    journal = json.loads(paths.journal.read_text())
    assert (journal["state"], journal["error_code"]) == (
        "rolled_back", "control_plane_install_failed_rolled_back")


def test_post_copy_digest_mismatch_is_detected_and_rolled_back(tmp_path: Path, monkeypatch):
    _seed_device(tmp_path)
    paths = _paths(tmp_path)
    old_tree = _tree(paths.bootstrap_install_root)
    installer = FullCopyInstaller()
    coordinator = _coordinator(tmp_path, installer)
    real_plane = verify_real_control_plane()
    lying = SimpleNamespace(root=real_plane.root, manifest=real_plane.manifest,
                            manifest_sha256=real_plane.manifest_sha256,
                            site_worker_protocol=real_plane.site_worker_protocol,
                            files={**real_plane.files, "ppu_site_worker.py": "0" * 64})
    monkeypatch.setattr(installer, "verify_control_plane", lambda verified: lying)
    with pytest.raises(deployment.DeploymentError, match="CONTROL_PLANE_INSTALL_UNVERIFIED"):
        coordinator.execute(_request(tmp_path))
    assert _tree(paths.bootstrap_install_root) == old_tree


def test_snapshot_failure_is_terminal_before_any_mutation(tmp_path: Path):
    _seed_device(tmp_path)
    paths = _paths(tmp_path)
    paths.control_plane_snapshots.parent.mkdir(parents=True, exist_ok=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    paths.control_plane_snapshots.symlink_to(elsewhere)
    old_tree = _tree(paths.bootstrap_install_root)
    installer = FullCopyInstaller()
    with pytest.raises(deployment.DeploymentError, match="snapshot failed"):
        _coordinator(tmp_path, installer).execute(_request(tmp_path))
    assert _tree(paths.bootstrap_install_root) == old_tree
    assert "activate" not in installer.calls
    journal = json.loads(paths.journal.read_text())
    assert (journal["state"], journal["error_code"]) == ("verify_failed", "control_plane_snapshot_failed")


# --------------------------------------------------------- coordinator: pre-flight


@pytest.mark.parametrize("selection,ok", [
    ({"adapter_driver": "plasma_swd", "driver_abi": 5}, True),
    ({"adapter_driver": "plasma_swd", "driver_abi": 4}, False),
    ({"adapter_driver": "other_swd", "driver_abi": 5}, False),
    ("not json", False),
    (None, True),  # no engine selected: the Worker already refuses Sessions
])
def test_adapter_abi_is_checked_against_the_selected_engine_before_mutation(tmp_path, selection, ok):
    _seed_device(tmp_path)
    paths = _paths(tmp_path)
    engine = paths.config_root / "site-worker-engine.json"
    if selection is None:
        engine.unlink()
    else:
        engine.write_text(selection if isinstance(selection, str) else json.dumps(selection))
    old_tree = _tree(paths.bootstrap_install_root)
    installer = FullCopyInstaller()
    if ok:
        assert _coordinator(tmp_path, installer).execute(_request(tmp_path))["result"] == "PASS"
        return
    with pytest.raises(deployment.DeploymentError, match="verification failed"):
        _coordinator(tmp_path, installer).execute(_request(tmp_path))
    assert installer.calls == ["verify", "python"]
    assert _tree(paths.bootstrap_install_root) == old_tree
    assert not paths.control_plane_snapshots.exists()
    assert json.loads(paths.journal.read_text())["state"] == "verify_failed"


class PreFullCopyInstaller(FullCopyInstaller):
    verify_control_plane = None


def test_installer_without_control_plane_support_is_refused(tmp_path: Path):
    _seed_device(tmp_path)
    paths = _paths(tmp_path)
    old_tree = _tree(paths.bootstrap_install_root)
    with pytest.raises(deployment.DeploymentError, match="RELEASE_CONTROL_PLANE_UNSUPPORTED_INSTALLER"):
        _coordinator(tmp_path, PreFullCopyInstaller()).execute(_request(tmp_path))
    assert _tree(paths.bootstrap_install_root) == old_tree


def test_interrupted_control_plane_install_is_fenced_not_resumed(tmp_path: Path):
    _seed_device(tmp_path)
    paths = _paths(tmp_path)
    paths.journal.parent.mkdir(parents=True, exist_ok=True)
    paths.journal.write_text(json.dumps({
        "schema_version": 1, "transaction_id": "tx-crashed", "state": "control_plane_installing",
        "sequence": 5, "started_at_epoch_s": 1.0, "updated_at_epoch_s": 2.0,
        "release_artifact": "/x.tar.gz"}))
    paths.journal.chmod(0o600)
    installer = FullCopyInstaller()
    with pytest.raises(deployment.DeploymentError, match="interrupted in state control_plane_installing"):
        _coordinator(tmp_path, installer).execute(_request(tmp_path))
    assert installer.calls == []
    assert json.loads(paths.journal.read_text())["state"] == "recovery_required"


# -------------------------------------------- real installer core: rollback ordering


def _core_install(tmp_path: Path, monkeypatch, *, on_rollback):
    artifact = _fake_release(tmp_path / "rel")
    verified = z2_installer.verify_release(artifact, extract_to=tmp_path / "verified")
    paths = z2_installer.InstallPaths(
        product_root=tmp_path / "opt" / "plasma", config_root=tmp_path / "etc" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma", log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system")
    previous = paths.releases_root / "0.0.9-previous"
    previous.mkdir(parents=True)
    paths.current.symlink_to(previous)
    monkeypatch.setattr(z2_installer, "_chown_tree", lambda *args: None)
    monkeypatch.setattr(z2_installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(z2_installer.pwd, "getpwnam", lambda n: types.SimpleNamespace(pw_uid=1, pw_gid=1))
    monkeypatch.setattr(z2_installer.grp, "getgrnam", lambda n: types.SimpleNamespace(gr_gid=1))
    calls: list = []

    def failed_health(host):
        raise z2_installer.Z2InstallerError("synthetic readiness failure")
    with pytest.raises(z2_installer.Z2InstallerError) as raised:
        z2_installer.install_release(
            verified, python_runtime=z2_installer.PythonRuntime(
                paths.product_root / "python" / "3.12.13" / "bin" / "python3", "3.12.13", "armv7l"),
            gateway_host="192.168.2.99", paths=paths, ppu_id="z2", facility_id="lab",
            display_name="Z2", systemctl=lambda *a: calls.append(a), health_check=failed_health,
            ensure_service_account=lambda: None,
            on_rollback=lambda: on_rollback(calls))
    return str(raised.value), calls, paths, previous


def test_real_core_restores_control_plane_before_restarting_previous_runtime(tmp_path, monkeypatch):
    message, calls, paths, previous = _core_install(
        tmp_path, monkeypatch, on_rollback=lambda calls: calls.append(("control-plane-restored",)))
    assert "previous configuration/release was restored" in message
    marker = calls.index(("control-plane-restored",))
    assert calls.index(("restart", "plasma-server.service"), marker) > marker
    assert paths.current.resolve() == previous.resolve()


def test_real_core_reports_control_plane_restore_failure_as_rollback_failure(tmp_path, monkeypatch):
    def broken(calls):
        raise RuntimeError("CONTROL_PLANE_RESTORE_FAILED: snapshot copy digest mismatch")
    message, calls, paths, previous = _core_install(tmp_path, monkeypatch, on_rollback=broken)
    assert "rollback also failed" in message and "CONTROL_PLANE_RESTORE_FAILED" in message
    # The Runtime rollback still ran (previous release restored and restarted).
    assert paths.current.resolve() == previous.resolve()
    assert ("restart", "plasma-server.service") in calls


# ------------------------------------------------ Runtime binding (new Runtime x old Worker)


def test_runtime_accepts_only_its_own_release_control_plane(tmp_path: Path):
    from plasma_server.package_actions import require_control_plane_release
    plane, product = installed_control_plane(tmp_path / "ok")
    assert require_control_plane_release(plane, product)["release_git_sha"] == "a" * 40
    plane, product = installed_control_plane(tmp_path / "old", identity_sha="b" * 40)
    with pytest.raises(RuntimeError, match="CONTROL_PLANE_RELEASE_MISMATCH"):
        require_control_plane_release(plane, product)
    plane, product = installed_control_plane(tmp_path / "proto", protocol="plasma.ppu.site-worker.v2")
    with pytest.raises(RuntimeError, match="SITE_WORKER_PROTOCOL_MISMATCH"):
        require_control_plane_release(plane, product)
    plane, product = installed_control_plane(tmp_path / "unbound")
    (plane / "control-plane.json").unlink()  # separately refreshed / pre-Full-Copy tree
    with pytest.raises(RuntimeError, match="CONTROL_PLANE_RELEASE_UNBOUND"):
        require_control_plane_release(plane, product)


def _package_actions_config(tmp_path: Path, plane: Path, product: Path) -> Path:
    import os
    import pwd
    cfg = {"schema": "plasma.ppu.package-actions-config.v1", "control_plane": str(plane),
           "product_root": str(product), "state_root": str(tmp_path / "state"),
           "python": "/usr/bin/python3", "package_user": pwd.getpwuid(os.getuid()).pw_name,
           "helper_socket": str(tmp_path / "helper.sock"),
           "site_worker_control_socket": str(tmp_path / "w.sock")}
    path = tmp_path / "pa.json"
    path.write_text(json.dumps(cfg))
    return path


def test_runtime_refuses_to_start_with_an_old_worker_module(tmp_path: Path):
    from plasma_server.package_actions import from_config
    plane, product = installed_control_plane(tmp_path)
    worker = plane / "ppu_site_worker.py"
    worker.write_text(worker.read_text().replace(
        'PROTOCOL = "plasma.ppu.site-worker.v3"', 'PROTOCOL = "plasma.ppu.site-worker.v2"'))
    with pytest.raises(RuntimeError, match="SITE_WORKER_PROTOCOL_MISMATCH"):
        from_config(object(), _package_actions_config(tmp_path, plane, product))


def test_runtime_refuses_to_start_on_another_releases_control_plane(tmp_path: Path):
    """New Runtime x Bootstrap tree of another commit: refused before any
    control-plane module is loaded, so a deployment health check rolls back."""
    from plasma_server.package_actions import from_config
    plane, product = installed_control_plane(tmp_path, identity_sha="b" * 40)
    with pytest.raises(RuntimeError, match="CONTROL_PLANE_RELEASE_MISMATCH"):
        from_config(object(), _package_actions_config(tmp_path, plane, product))


# --------------------------------------- no second installer / separate Bootstrap refresh


@pytest.mark.parametrize("refresh_only", [True, False])
def test_bootstrap_installer_refuses_to_split_a_full_copy_tree(tmp_path: Path, refresh_only: bool):
    module = _bootstrap_installer()
    install_root = tmp_path / "opt" / "plasma" / "bootstrap"
    install_root.mkdir(parents=True)
    (install_root / "control-plane.json").write_text("{}")
    paths = module.InstallPaths(install_root, tmp_path / "state", tmp_path / "unit.service")
    with pytest.raises(module.BootstrapInstallError, match="BOOTSTRAP_MANAGED_BY_FULL_COPY_DEPLOYMENT"):
        module.install_bootstrap(source_root=_RUNTIME / "control-plane", host="192.168.2.99",
                                 port=18081, python_executable="/usr/bin/python3", paths=paths,
                                 refresh_only=refresh_only)
    assert sorted(p.name for p in install_root.iterdir()) == ["control-plane.json"]


def test_coordinator_reuses_the_bootstrap_installer_copy_routine():
    source = (ROOT / "scripts" / "ppu-bootstrap-deployment.py").read_text()
    assert "bootstrap_installer._copy_scripts(plane.root, install_root)" in source
    assert "shutil.copytree" not in source

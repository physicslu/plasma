"""Host-only safety tests; no SWPC Runner, user-systemd, PPU or DUT touched."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "scripts/plasma_path2_control_station.py"
spec = importlib.util.spec_from_file_location("plasma_path2_control_station", SOURCE)
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

SHA = "a" * 40


@pytest.fixture()
def backend(tmp_path: Path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    file = scripts / "plasmactl-local-control-station"
    file.write_text(
        "run_deployment_preflight() { true; }\n"
        "deploy_profile() {\n"
        "  run_deployment_preflight\n"
        "  prepare_release\n"
        "  run_deployment_preflight\n"
        "}\n"
        "parse_options() { true; }\n",
        encoding="utf-8",
    )
    (scripts / "plasma_cs_deploy_preflight.py").write_text("# stub fixture", encoding="utf-8")
    monkeypatch.setattr(adapter, "ROOT", tmp_path)
    monkeypatch.setattr(adapter, "BACKEND", file)
    monkeypatch.setattr(adapter, "PREFLIGHT", scripts / "plasma_cs_deploy_preflight.py")
    monkeypatch.setattr(adapter.socket, "gethostname", lambda: "SWPC")
    monkeypatch.setattr(adapter.sys, "platform", "linux")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SHA + "\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    return file, calls


def test_read_only_verify_uses_pinned_owner_and_fixed_shell(backend) -> None:
    _, calls = backend
    assert adapter.run("verify", SHA) == 0
    assert len(calls) == 3
    final = calls[-1]
    assert final == [
        "/usr/bin/sudo", "-n", "-H", "-u", "gordon", "--", "/usr/bin/env",
        "XDG_RUNTIME_DIR=/run/user/1000",
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
        "/usr/bin/bash", str(adapter.BACKEND), "verify",
    ]


def test_status_is_read_only_and_not_a_deploy(backend) -> None:
    _, calls = backend
    assert adapter.run("status", SHA) == 0
    assert calls[-1][-1] == "status"


def test_deploy_requires_explicit_maintenance_and_two_preflight_checkpoints(backend) -> None:
    backend_file, calls = backend
    with pytest.raises(adapter.Blocked, match="MAINTENANCE_EXCLUSIVITY"):
        adapter.run("deploy", SHA)
    assert len(calls) == 2  # git source checks, never sudo
    assert adapter.run("deploy", SHA, True) == 0
    assert calls[-1][-1] == "deploy"
    backend_file.write_text("deploy_profile() {\n  prepare_release\n}\n")
    with pytest.raises(adapter.Blocked, match="PREFLIGHT"):
        adapter.run("deploy", SHA, True)


def test_wrong_source_and_hostname_fail_before_sudo(backend, monkeypatch) -> None:
    _, calls = backend
    with pytest.raises(adapter.Blocked, match="SOURCE_SHA_INVALID"):
        adapter.run("verify", "not-a-sha")
    assert not calls
    with pytest.raises(adapter.Blocked, match="SOURCE_SHA_MISMATCH"):
        adapter.run("verify", "b" * 40)
    assert len(calls) == 1
    monkeypatch.setattr(adapter.socket, "gethostname", lambda: "other")
    with pytest.raises(adapter.Blocked, match="SWPC_LINUX_REQUIRED"):
        adapter.run("verify", SHA)


def test_dirty_source_and_sudo_failure_never_retry(backend, monkeypatch) -> None:
    _, calls = backend

    def dirty(cmd, **kwargs):
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SHA)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(adapter.subprocess, "run", dirty)
    with pytest.raises(adapter.Blocked, match="SOURCE_DIRTY"):
        adapter.run("verify", SHA)

    def failed(cmd, **kwargs):
        calls.append(cmd)
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SHA)
        if "diff" in cmd:
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(adapter.subprocess, "run", failed)
    with pytest.raises(adapter.Blocked, match="NO_RETRY"):
        adapter.run("verify", SHA)
    assert sum(x[-1] == "verify" for x in calls) == 1


def test_deploy_timeout_is_outcome_unknown_not_auto_retried(backend, monkeypatch) -> None:
    _, calls = backend

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SHA)
        if "diff" in cmd:
            return SimpleNamespace(returncode=0)
        raise adapter.subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    with pytest.raises(adapter.Blocked, match="TIMED_OUT_OUTCOME_UNKNOWN"):
        adapter.run("deploy", SHA, True)
    assert sum(x[-1] == "deploy" for x in calls) == 1


def test_arbitrary_operations_cannot_run(backend) -> None:
    _, calls = backend
    with pytest.raises(adapter.Blocked, match="OPERATION_DENIED"):
        adapter.run("shell", SHA)
    assert len(calls) == 2


def test_maintenance_flag_rejected_for_readonly(backend) -> None:
    _, calls = backend
    with pytest.raises(adapter.Blocked, match="FLAG_ONLY_ALLOWED"):
        adapter.run("verify", SHA, True)
    assert len(calls) == 2

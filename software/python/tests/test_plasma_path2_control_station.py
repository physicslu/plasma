"""Path 2 fixed owner bridge negative tests (Host-only; zero SWPC mutation)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "scripts/plasma_path2_control_station.py"
spec = importlib.util.spec_from_file_location("plasma_path2_control_station", SOURCE)
assert spec and spec.loader
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

SOURCE_SHA = "a" * 40
TARGET_SHA = "b" * 40


@pytest.fixture()
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "ROOT", tmp_path)
    monkeypatch.setattr(adapter.socket, "gethostname", lambda: "SWPC")
    monkeypatch.setattr(adapter.sys, "platform", "linux")
    calls = []

    def fake(cmd, **kwargs):
        calls.append(list(cmd))
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SOURCE_SHA + "\n")
        if "--porcelain=v1" in cmd:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(adapter.subprocess, "run", fake)
    return calls


@pytest.mark.parametrize("operation", ["status", "verify"])
def test_only_exact_fixed_owner_bridge_used(operation, runner):
    assert adapter.run(operation, SOURCE_SHA) == 0
    assert len(runner) == 3
    assert runner[-1] == [
        "/usr/bin/sudo", "-n", "-H", "-u", "gordon", "--",
        "/usr/local/libexec/plasma/plasma-control-station-owner-bridge",
        operation,
    ]


@pytest.mark.parametrize("operation", [
    "deploy", "shell", "install", "rollback", "git", "sudo"
])
def test_arbitrary_or_deploy_command_cannot_invoke_bridge(operation, runner):
    with pytest.raises(adapter.Blocked):
        adapter.run(operation, SOURCE_SHA, TARGET_SHA, True)
    assert all(adapter.BRIDGE not in c for c in runner)


def test_deploy_without_owner_intent_still_refused(runner):
    with pytest.raises(adapter.Blocked, match="DEPLOY_BRIDGE_NOT_QUALIFIED"):
        adapter.run("deploy", SOURCE_SHA)
    assert len(runner) == 2
    assert all(adapter.BRIDGE not in c for c in runner)


@pytest.mark.parametrize("operation", ["status", "verify"])
def test_deploy_only_args_rejected_on_readonly(operation, runner):
    with pytest.raises(adapter.Blocked, match="DEPLOY_ONLY_ARGUMENT"):
        adapter.run(operation, SOURCE_SHA, target_sha=TARGET_SHA)
    with pytest.raises(adapter.Blocked, match="DEPLOY_ONLY_ARGUMENT"):
        adapter.run(operation, SOURCE_SHA, owner_maintenance_confirmed=True)
    assert all(adapter.BRIDGE not in c for c in runner)


def test_reject_invalid_source_sha_before_any_io(runner):
    with pytest.raises(adapter.Blocked, match="ADAPTER_SOURCE_SHA_INVALID"):
        adapter.run("status", "not-a-SHA")
    assert runner == []


def test_reject_forged_source_sha_and_wrong_host(runner, monkeypatch):
    with pytest.raises(adapter.Blocked, match="ADAPTER_SOURCE_SHA_MISMATCH"):
        adapter.run("verify", "f" * 40)
    assert len(runner) == 2
    monkeypatch.setattr(adapter.socket, "gethostname", lambda: "unknown-host")
    with pytest.raises(adapter.Blocked, match="SWPC_LINUX_REQUIRED"):
        adapter.run("verify", SOURCE_SHA)


def test_reject_dirty_untracked_candidate_source(runner, monkeypatch):
    def fake(cmd, **kwargs):
        runner.append(list(cmd))
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SOURCE_SHA + "\n")
        return SimpleNamespace(returncode=0, stdout="?? injected.py\n")
    monkeypatch.setattr(adapter.subprocess, "run", fake)
    with pytest.raises(adapter.Blocked, match="ADAPTER_WORKTREE_DIRTY"):
        adapter.run("status", SOURCE_SHA)
    assert all(adapter.BRIDGE not in c for c in runner)


@pytest.mark.parametrize("code,reason", [
    (77, "PERMISSION_DENIED"),
    (2, "FAILED_2"),
])
def test_bridge_failure_never_retries(code, reason, runner, monkeypatch):
    def fake(cmd, **kwargs):
        runner.append(list(cmd))
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SOURCE_SHA + "\n")
        if "--porcelain=v1" in cmd:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=code)
    monkeypatch.setattr(adapter.subprocess, "run", fake)
    with pytest.raises(adapter.Blocked, match=reason):
        adapter.run("status", SOURCE_SHA)
    assert sum(adapter.BRIDGE in c for c in runner) == 1


def test_unknown_bridge_timeout_is_nonretry(runner, monkeypatch):
    def fake(cmd, **kwargs):
        runner.append(list(cmd))
        if "rev-parse" in cmd:
            return SimpleNamespace(returncode=0, stdout=SOURCE_SHA + "\n")
        if "--porcelain=v1" in cmd:
            return SimpleNamespace(returncode=0, stdout="")
        raise adapter.subprocess.TimeoutExpired(cmd, kwargs["timeout"])
    monkeypatch.setattr(adapter.subprocess, "run", fake)
    with pytest.raises(adapter.Blocked, match="BRIDGE_UNAVAILABLE"):
        adapter.run("verify", SOURCE_SHA)
    assert sum(adapter.BRIDGE in c for c in runner) == 1


def test_cli_reports_bridge_permission_denied_as_77(runner, monkeypatch):
    monkeypatch.setattr(adapter, "run",
                        lambda *args: (_ for _ in ()).throw(
                            adapter.Blocked("FIXED_OWNER_BRIDGE_PERMISSION_DENIED")))
    assert adapter.main(["status", "--source-sha", SOURCE_SHA]) == 77

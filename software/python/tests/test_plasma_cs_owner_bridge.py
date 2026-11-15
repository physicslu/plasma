"""Host-only negative coverage for fixed Control Station owner bridge.

Never invokes the installed bridge or touches systemd / SWPC / DUT.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "scripts/plasma_cs_owner_bridge.py"
spec = importlib.util.spec_from_file_location("plasma_cs_owner_bridge", TARGET)
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


@pytest.mark.parametrize("argv", [
    [], ["deploy"], ["deploy", "abc"], ["status", "--source", "bad"],
    ["verify", "extra"], ["shell"], ["../../bin/sh"],
])
def test_unsupported_operations_refused_without_fallback(argv, monkeypatch):
    called = []
    monkeypatch.setattr(bridge, "invoke_readonly", lambda op: called.append(op))
    assert bridge.main(argv) == 77
    assert called == []


@pytest.mark.parametrize("operation", ["status", "verify"])
def test_allowed_operation_invokes_exact_known_route(operation, monkeypatch):
    called = []
    monkeypatch.setattr(bridge, "invoke_readonly", lambda op: called.append(op) or 0)
    assert bridge.main([operation]) == 0
    assert called == [operation]


def test_readonly_runtime_runs_fixed_backend_with_sanitized_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(bridge, "require_safe_installed_bridge", lambda: None)
    monkeypatch.setattr(bridge, "require_origin", lambda: None)
    monkeypatch.setattr(bridge, "require_owner_checkout", lambda: None)
    monkeypatch.setattr(bridge.pwd, "getpwuid",
                        lambda uid: SimpleNamespace(pw_dir="/home/operator"))
    def fake(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(bridge.subprocess, "run", fake)
    assert bridge.invoke_readonly("verify") == 0
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == ["/usr/bin/bash", str(bridge.BACKEND), "verify"]
    assert kwargs["check"] is False and kwargs["timeout"] == 180
    assert kwargs["env"]["PATH"] == "/usr/local/bin:/usr/bin:/bin"
    assert kwargs["env"]["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert "PYTHONPATH" not in kwargs["env"]
    assert "LD_PRELOAD" not in kwargs["env"]


def test_nonzero_never_retries(monkeypatch):
    calls = []
    for name in ("require_safe_installed_bridge", "require_origin",
                 "require_owner_checkout"):
        monkeypatch.setattr(bridge, name, lambda: None)
    monkeypatch.setattr(bridge.pwd, "getpwuid",
                        lambda uid: SimpleNamespace(pw_dir="/home/operator"))
    def fail(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr(bridge.subprocess, "run", fail)
    with pytest.raises(bridge.Blocked, match="FAILED_2"):
        bridge.invoke_readonly("status")
    assert len(calls) == 1


def test_refuses_direct_deploy_even_with_all_other_guards_patched(monkeypatch):
    called = []
    monkeypatch.setattr(bridge, "invoke_readonly", lambda op: called.append(op))
    assert bridge.main(["deploy"]) == 77
    assert called == []


def test_rejects_missing_untrusted_runner_identity(monkeypatch):
    monkeypatch.setattr(bridge.sys, "platform", "linux")
    monkeypatch.setattr(bridge.os, "getuid", lambda: 1000)
    monkeypatch.setattr(bridge.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(bridge.pwd, "getpwuid",
                        lambda uid: SimpleNamespace(pw_name="gordon"))
    monkeypatch.setenv("SUDO_USER", "someone-else")
    monkeypatch.setenv("SUDO_UID", "998")
    with pytest.raises(bridge.Blocked, match="RUNNER_IDENTITY"):
        bridge.require_origin()


def test_bad_parent_path_and_symlink_refused(monkeypatch, tmp_path):
    target = tmp_path / "plasma-control-station-owner-bridge"
    target.symlink_to(TARGET)
    monkeypatch.setattr(bridge, "INSTALLED_PATH", target)
    monkeypatch.setattr(bridge, "__file__", str(target))
    with pytest.raises(bridge.Blocked, match="TRUSTED_BRIDGE_PATH_MUTABLE"):
        bridge.require_safe_installed_bridge()

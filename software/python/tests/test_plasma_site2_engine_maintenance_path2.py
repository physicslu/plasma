"""Path2 Admission-only Engine repair: Host-only fail-closed contract tests.

No SWPC SSH, sudo, Z2, FPGA or DUT is touched.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "plasma_site2_engine_maint_test",
    ROOT / "scripts/plasma_site2_engine_maintenance_path2.py",
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

SHA = "c" * 40


def _pinned(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module.subprocess, "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["git", "rev-parse", "HEAD"], returncode=0, stdout=SHA + "\n"
        ),
    )


def test_remote_is_parseable_and_never_executes_during_import():
    compile(module.REMOTE, "<bounded-z2-remote>", "exec")
    assert "install_selected_admission(" in module.REMOTE
    assert "held_runtime_asset_lease()" in module.REMOTE
    assert "restart=True" in module.REMOTE
    assert '("prepare","switch")' in module.REMOTE
    assert "openocd_build" in module.REMOTE
    assert "bundle_deploy" in module.REMOTE
    assert "DEVMEM_INDEPENDENT_IMAGES" in module.REMOTE  # rejection, not use


def test_wrong_source_commit_refuses_before_any_preflight(tmp_path, monkeypatch):
    _pinned(monkeypatch, tmp_path)
    class Never:
        @staticmethod
        def run(*_args, **_kwargs):
            raise AssertionError("must not reach any preflight")
    with pytest.raises(RuntimeError, match="SOURCE_SHA_MISMATCH"):
        module.run("192.168.2.99", "d"*40, "prepare", baseline=Never())


def test_unsafe_target_denied_before_any_preflight(tmp_path, monkeypatch):
    _pinned(monkeypatch, tmp_path)
    class Never:
        @staticmethod
        def run(*_args, **_kwargs):
            raise AssertionError("must not reach any preflight")
    with pytest.raises(RuntimeError, match="HOST_SCOPE_DENIED"):
        module.run("8.8.8.8", SHA, "prepare", baseline=Never())


@pytest.mark.parametrize("mode", ["prepare", "switch"])
def test_idle_or_engine_identity_missing_blocks_without_ssh(tmp_path, monkeypatch, mode):
    _pinned(monkeypatch, tmp_path)
    class Preflight:
        @staticmethod
        def run(*_args):
            return {"readiness": "NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS",
                    "blockers": [], "z2": {
                        "engine": {"status": "VERIFIED", "abi": 5,
                                   "adapter_khz": 2000, "openocd_sha256_observed": "0"*64,
                                   "admission_sha256_observed": module.OLD_ADMISSION_SHA256},
                        "fpga": {"manager_state": "operating"},
                        "openocd_pids": [], "site2_seal": {"present": False},
                        "site2_admission": {"present": False}}}
    class NeverHelper:
        @staticmethod
        def z2_login_credentials(*_args):
            raise AssertionError("must not touch enrolled credentials")
    with pytest.raises(RuntimeError, match="ENGINE_MAINT_PREFLIGHT_BLOCKED"):
        module.run("192.168.2.99", SHA, mode,
                   baseline=Preflight(), helper=NeverHelper())


def test_remote_script_denies_an_unexpected_mode(tmp_path, monkeypatch):
    _pinned(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="MODE_DENIED"):
        module.run("192.168.2.99", SHA, "deploy",
                   baseline=object(), helper=object())

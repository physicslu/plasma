from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-bootstrap-hil-evidence.py"
SPEC = importlib.util.spec_from_file_location("ppu_bootstrap_hil_evidence", SCRIPT)
assert SPEC and SPEC.loader
hil = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hil
SPEC.loader.exec_module(hil)


def _service(active: bool = True):
    return {"state": "active" if active else "inactive", "active": active}


def _trusted(state: str):
    return {"trusted": True, "mode": "0o600", "record": {"state": state}}


def _base(phase: str, *, expected: str | None = None):
    return {
        "phase": phase,
        "expected_release_id": expected,
        "services": {
            "plasma-bootstrap.service": _service(),
            "plasma-server.service": _service(),
            "plasma-web.service": _service(),
        },
        "current_release": {
            "state": "active" if expected else "absent",
            "release_id": expected,
        },
        "bootstrap_status": {
            "status": 200,
            "payload": {
                "bootstrap": {"state": "bootstrap_ready"},
                "runtime": {
                    "state": "runtime_active" if expected else "runtime_absent",
                    "release_id": expected,
                },
                "capabilities": {"fpga_update": False},
            },
        },
        "gateway_ready": {
            "status": 200,
            "payload": {"gateway": "alive", "execution": "ready"},
        },
        "deployment_engine_journal": _trusted("runtime_active"),
        "deployment_api_journal": _trusted("succeeded"),
    }


def test_factory_checkpoint_requires_bootstrap_but_not_runtime():
    snapshot = _base("factory")
    snapshot["services"]["plasma-server.service"] = _service(False)
    snapshot["services"]["plasma-web.service"] = _service(False)
    snapshot["gateway_ready"] = {"status": None, "payload": None, "error": "connection refused"}
    assert hil.evaluate_snapshot(snapshot) == []


def test_runtime_checkpoint_requires_exact_release_services_and_ready_gateway():
    expected = "0.1.1-0123456789ab"
    snapshot = _base("runtime-after-reboot", expected=expected)
    assert hil.evaluate_snapshot(snapshot) == []

    snapshot["current_release"]["release_id"] = "wrong-release"
    snapshot["gateway_ready"]["payload"]["execution"] = "unavailable"
    failures = hil.evaluate_snapshot(snapshot)
    assert "active release does not match expected_release_id" in failures
    assert "Gateway readiness payload is not gateway=alive/execution=ready" in failures


def test_runtime_checkpoint_rejects_untrusted_or_nonterminal_journals():
    expected = "0.1.1-0123456789ab"
    snapshot = _base("runtime-active", expected=expected)
    snapshot["deployment_engine_journal"] = {
        "trusted": False,
        "error": "journal permissions allow group/other access",
    }
    snapshot["deployment_api_journal"] = _trusted("running")
    failures = hil.evaluate_snapshot(snapshot)
    assert "deployment engine journal is unavailable or untrusted" in failures
    assert "deployment API journal is not succeeded" in failures


def test_rollback_checkpoint_requires_rolled_back_engine_and_failed_api_transaction():
    expected = "0.1.0-aaaaaaaaaaaa"
    snapshot = _base("rollback-restored", expected=expected)
    snapshot["deployment_engine_journal"] = _trusted("rolled_back")
    snapshot["deployment_api_journal"] = _trusted("failed")
    assert hil.evaluate_snapshot(snapshot) == []

    snapshot["deployment_engine_journal"] = _trusted("recovery_required")
    snapshot["deployment_api_journal"] = _trusted("succeeded")
    failures = hil.evaluate_snapshot(snapshot)
    assert "deployment engine journal is not rolled_back" in failures
    assert "deployment API journal is not failed after controlled rollback" in failures


def test_non_factory_checkpoint_requires_expected_release_identity():
    snapshot = _base("runtime-active", expected=None)
    snapshot["bootstrap_status"]["payload"]["runtime"]["state"] = "runtime_active"
    failures = hil.evaluate_snapshot(snapshot)
    assert "expected_release_id is required for non-factory checkpoints" in failures

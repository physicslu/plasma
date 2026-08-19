from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLASMACTL = REPO_ROOT / "scripts" / "plasmactl"
VERIFY = REPO_ROOT / "scripts" / "plasmactl-verify"


def run_bash(script: str, *, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PLASMACTL_VERIFY_LIB_ONLY": "1",
            "PLASMA_PYTHON": sys.executable,
            "PLASMACTL_CONFIG": str(REPO_ROOT / ".nonexistent-plasmactl-test.env"),
        }
    )
    return subprocess.run(
        ["bash", "-c", script, "_", str(VERIFY)],
        cwd=REPO_ROOT,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def valid_payload() -> dict[str, object]:
    return {
        "ok": True,
        "contract_version": "1",
        "degraded": False,
        "summary": {
            "configured_ppus": 1,
            "reachable_ppus": 1,
            "ready_ppus": 1,
            "current_ppus": 1,
            "stale_ppus": 0,
            "unknown_ppus": 0,
            "reported_sites": 8,
            "enabled_sites": 2,
            "identity_conflicts": 0,
        },
        "manager": {
            "cache_age_s": 0.2,
            "poll_interval_s": 2.0,
            "refresh_healthy": True,
            "observation_store": {
                "mode": "sqlite",
                "healthy": True,
                "writable": True,
            },
        },
        "ppus": [
            {
                "alias": "ppu-a",
                "identity": {
                    "ppu_id": "z2-dev-01",
                    "facility_id": "lab-01",
                    "model": "PYNQ-Z2",
                    "display_name": "Plasma Z2 Prototype",
                },
                "transport_state": "reachable",
                "execution_state": "ready",
                "observation": {
                    "state": "current",
                    "last_success_at": "2026-08-19T08:00:00+00:00",
                    "stale_age_s": 0.0,
                },
                "topology": {
                    "source": "current",
                    "site_count": 8,
                    "enabled_site_count": 2,
                    "sites": [],
                },
                "current_capacity": {
                    "site_count": 8,
                    "enabled_site_count": 2,
                },
                "identity_conflict": False,
                "degraded": False,
            }
        ],
    }


def test_plasmactl_and_verifier_are_valid_bash() -> None:
    for path in (PLASMACTL, VERIFY):
        result = subprocess.run(
            ["bash", "-n", str(path)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_fleet_payload_validator_accepts_sanitized_current_capacity() -> None:
    result = run_bash(
        'source "$1"; validate_fleet_payload',
        stdin=json.dumps(valid_payload()),
    )
    assert result.returncode == 0, result.stderr
    assert "configured_ppus=1" in result.stdout
    assert "ready_ppus=1" in result.stdout
    assert "reported_sites=8" in result.stdout
    assert "enabled_sites=2" in result.stdout
    assert "observation_store=sqlite" in result.stdout


def test_fleet_payload_validator_rejects_internal_endpoint_leak() -> None:
    payload = valid_payload()
    payload["ppus"][0]["endpoint"] = "http://192.0.2.10:18080"  # type: ignore[index]
    result = run_bash(
        'source "$1"; validate_fleet_payload',
        stdin=json.dumps(payload),
    )
    assert result.returncode != 0
    assert "forbidden key: endpoint" in result.stderr


def test_fleet_payload_validator_rejects_stale_current_capacity() -> None:
    payload = valid_payload()
    ppu = payload["ppus"][0]  # type: ignore[index]
    ppu["observation"]["state"] = "stale"  # type: ignore[index]
    ppu["current_capacity"] = {"site_count": 8, "enabled_site_count": 2}  # type: ignore[index]
    result = run_bash(
        'source "$1"; validate_fleet_payload',
        stdin=json.dumps(payload),
    )
    assert result.returncode != 0
    assert "stale/unknown PPU contributes current capacity" in result.stderr


def test_verifier_exposes_fleet_target_and_main_dispatch_contract() -> None:
    verifier_source = VERIFY.read_text(encoding="utf-8")
    plasmactl_source = PLASMACTL.read_text(encoding="utf-8")

    assert "fleet) verify_fleet" in verifier_source
    assert "plasmactl verify TARGET" in verifier_source
    assert "verify)" in plasmactl_source
    assert "plasmactl-verify" in plasmactl_source

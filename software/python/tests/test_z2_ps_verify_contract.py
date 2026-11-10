from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
Z2_PS = REPO_ROOT / "scripts" / "plasmactl-z2-ps"


def test_z2_ps_verify_uses_read_only_g13_readiness_not_an_unsigned_write() -> None:
    """LOM-P2A-2 P0: the kit is not the controller and never sends a Gateway write.

    The former unsigned ``curl`` PS loopback POST was refused by G13 (401) on the
    real Z2 and left Bootstrap tx ``370e51bc…`` ``coordinator_result_unreconciled``.
    """
    source = Z2_PS.read_text(encoding="utf-8")
    verify = source[source.index("verify_runtime() {"):source.index("show_status() {")]
    assert 'loopback_request="' not in source
    assert "diagnostics/loopback" not in verify
    assert '"$readiness_tool" --gateway "$base"' in verify
    assert '--bootstrap "http://$gateway_host:18081"' in verify
    assert "signed PS loopback: delegated to the controller-authorized Manager acceptance" in verify


def test_z2_ps_verify_matches_current_readiness_contract() -> None:
    source = (REPO_ROOT / "scripts" / "ppu_runtime_local_readiness.py").read_text(encoding="utf-8")

    assert 'ready.get("gateway") != "alive"' in source
    assert 'ready.get("execution") != "ready"' in source
    assert 'ready.get("gateway") != "ready"' not in source


def test_z2_ps_readiness_tool_checks_g13_refusal_and_identity() -> None:
    tool = (REPO_ROOT / "scripts" / "ppu_runtime_local_readiness.py").read_text(encoding="utf-8")
    assert '"/api/auth/challenge"' in tool and '"/v1/status"' in tool
    assert '"POST"' not in tool and "--data" not in tool          # GET-only: no write of any kind
    assert '"signed_ps_loopback": "DELEGATED_TO_MANAGER_ACCEPTANCE"' in tool

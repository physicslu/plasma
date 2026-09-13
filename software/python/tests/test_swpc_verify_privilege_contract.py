from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "scripts" / "plasmactl"
ORCHESTRATOR = ROOT / "scripts" / "plasmactl-swpc-z2like-orchestrator"


def test_swpc_verify_operator_contract_requires_root() -> None:
    router = ROUTER.read_text(encoding="utf-8")
    orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")

    assert "sudo plasmactl verify swpc-z2like" in router
    assert "require_root_verify" in orchestrator
    assert "verify requires root because appliance configuration" in orchestrator
    assert "Root-read-only verification" in orchestrator


def test_swpc_verify_root_guard_runs_before_restricted_state_probe() -> None:
    source = ORCHESTRATOR.read_text(encoding="utf-8")
    verify_body = source.split("verify_profile() {", 1)[1].split("}\n\ndeploy_profile()", 1)[0]

    assert verify_body.index("require_root_verify") < verify_body.index("capture_desired_state")

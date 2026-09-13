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


def test_swpc_verify_root_guard_is_operator_admission_not_internal_deploy_policy() -> None:
    source = ORCHESTRATOR.read_text(encoding="utf-8")
    verify_body = source.split("verify_profile() {", 1)[1].split("}\n\ndeploy_profile()", 1)[0]
    command_dispatch = source.split('case "$command" in', 1)[1]

    assert "require_root_verify" not in verify_body
    assert "verify) require_root_verify; verify_profile" in command_dispatch

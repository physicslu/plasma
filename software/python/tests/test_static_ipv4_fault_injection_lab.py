from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[3]


def _text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def test_fault_lab_covers_all_approved_scenarios() -> None:
    source = _text("scripts/static-ipv4-fault-injection-lab.py")
    for token in (
        "duplicate_candidate",
        "wrong_ppu_id",
        "reconnect_timeout",
        "helper_apply_failure",
        "manager_crash_before_commit",
        "manager_crash_after_commit",
    ):
        assert token in source
    assert "linux-host-real-manager-qemu-armv7-static-ipv4-fault-injection" in source
    assert "Z2 NETWORK BACKEND CLAIM    : NONE" in source


def test_precommit_recovery_retry_is_blocked_by_recovery_required_itself() -> None:
    source = _text("scripts/static-ipv4-fault-injection-lab.py")
    assert '"network_commissioning_busy"' in source
    assert 'retry_record.get("state") != "recovery_required"' in source
    assert '"trusted_fleet_restored_before_retry": True' in source
    assert source.index('activation = _wait_activation(') < source.index('"fault-crash-before-commit-retry"')


def test_crash_injector_crashes_only_after_real_durable_put() -> None:
    source = _text("scripts/manager-network-commissioning-crash-injector.py")
    assert 'choices=("identity_verified", "activation_committed")' in source
    assert "persisted = original_put(self, record)" in source
    assert "os.kill(os.getpid(), signal.SIGKILL)" in source
    assert source.index("persisted = original_put(self, record)") < source.index("os.kill(os.getpid(), signal.SIGKILL)")


def test_fault_helper_is_test_only_and_preserves_gateway_contract() -> None:
    source = _text("scripts/static-ipv4-fault-helper.py")
    for operation in ('operation == "snapshot"', 'operation == "apply"', 'operation == "restore"'):
        assert operation in source
    for mode in ("apply-error", "apply-noop", "apply-drop", "restore-error"):
        assert mode in source
    assert "CAP_NET_ADMIN" not in source


def test_production_manager_and_gateway_have_no_fault_switches() -> None:
    manager = _text("software/python/plasma_manager/network_commissioning.py")
    server = _text("software/python/plasma_manager/server.py")
    gateway = _text("software/python/plasma_web/ppu_network_activation.py")
    combined = manager + server + gateway
    assert "crash-after-state" not in combined
    assert "STATIC_IPV4_FAULT_HELPER_ERROR" not in combined
    assert "fault_mode" not in combined


def test_release_workflow_runs_fault_lab_after_happy_path() -> None:
    workflow = _text(".github/workflows/ppu-release.yml")
    assert "scripts/static-ipv4-fault-injection-lab.py" in workflow
    assert "software/python/tests/test_static_ipv4_fault_injection_lab.py" in workflow
    happy = workflow.index("Run Virtual PPU Network Lab with production Manager")
    faults = workflow.index("Run Static IPv4 fault-injection lab")
    assert happy < faults


def test_fault_injection_document_is_indexed_and_keeps_hardware_claim_closed() -> None:
    index = _text("docs/README.md")
    doc = _text("docs/architecture/static-ipv4-fault-injection.md")
    assert "architecture/static-ipv4-fault-injection.md" in index
    assert "PYNQ-Z2" in doc
    assert "does **not** prove" in doc
    assert "recovery_required" in doc

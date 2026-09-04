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


def test_fault_lab_repairs_disposable_container_owned_workspace_without_sudo() -> None:
    source = _text("scripts/static-ipv4-fault-injection-lab.py")
    assert "_make_stale_work_host_removable" in source
    assert '"--network", "none"' in source
    assert '"--cap-drop", "ALL"' in source
    assert '"no-new-privileges:true"' in source
    assert '"sudo"' not in source
    assert 'shutil.which("sudo")' not in source
    assert source.index("phase2._docker_preflight()") < source.index("_make_stale_work_host_removable(phase2, root)")
    assert source.index("_make_stale_work_host_removable(phase2, root)") < source.index("shutil.rmtree(root)")


def test_postcommit_evidence_uses_canonical_activation_journal_path() -> None:
    source = _text("scripts/static-ipv4-fault-injection-lab.py")
    assert 'ppu_work / "gateway-output" / "ppu-network-activation.json"' in source
    assert 'ppu_work.rglob("ppu-network-activation.json")' not in source


def test_private_activation_journal_is_hashed_through_locked_down_readonly_container() -> None:
    source = _text("scripts/static-ipv4-fault-injection-lab.py")
    sha_source = source.split("def _sha256(path: Path) -> str:", 1)[1].split(
        "def _make_stale_work_host_removable", 1
    )[0]
    assert "root:root 0600" in sha_source
    assert "tempfile.mkstemp()" in sha_source
    assert '"--network", "none"' in sha_source
    assert '"--cap-drop", "ALL"' in sha_source
    assert '"no-new-privileges:true"' in sha_source
    assert 'f"{ppu_work}:/work:ro"' in sha_source
    assert "phase2.ARM_IMAGE" in sha_source
    assert "chmod" not in sha_source
    assert 'with path.open("rb")' not in sha_source
    assert '"with path.open(\'rb\') as handle:\\n"' in sha_source


def test_independent_private_evidence_verifier_enforces_ownership_and_read_boundary() -> None:
    source = _text("scripts/private-ppu-evidence-verifier.py")
    assert 'CANONICAL_RELATIVE_PATH = Path("gateway-output/ppu-network-activation.json")' in source
    assert "host verifier must run as a non-root user" in source
    assert "info.st_uid != 0 or info.st_gid != 0 or mode != 0o600" in source
    assert "expected root:root 0600" in source
    assert '"--network",\n            "none"' in source
    assert '"--cap-drop",\n            "ALL"' in source
    assert '"no-new-privileges:true"' in source
    assert 'f"{ppu_work}:/evidence:ro"' in source
    assert '"--user",\n            "0:0"' in source
    for forbidden in (
        "chmod(",
        "sudo",
        "rglob(",
        "static-ipv4-fault-helper",
        "manager-network-commissioning-crash-injector",
        "plasma_manager",
        "plasma_web",
    ):
        assert forbidden not in source


def test_repeatability_gate_runs_twice_in_same_workdir_without_own_cleanup() -> None:
    source = _text("scripts/static-ipv4-fault-injection-repeatability.py")
    assert "for attempt in range(1, 3):" in source
    assert 'command.extend(["--work-dir", str(work), "--report", str(run_report)])' in source
    assert 'work / "manager-crash-after-commit" / "ppu-a"' in source
    assert 'str(repo / "scripts/private-ppu-evidence-verifier.py")' in source
    assert '"run_count": 2' in source
    assert '"manual_cleanup": False' in source
    assert '"host_verifier_non_root": True' in source
    assert '"producer_evidence_contract": "root:root 0600"' in source
    assert '"verifier_independent": True' in source
    for forbidden in ("rmtree(", "chmod(", "rglob(", "sudo"):
        assert forbidden not in source


def test_fault_lab_streams_scenario_progress() -> None:
    source = _text("scripts/static-ipv4-fault-injection-lab.py")
    assert 'print(f"[RUN ] {index}/{total} {label}", flush=True)' in source
    assert 'print(f"[PASS] {index}/{total} {label} ({elapsed:.1f}s)", flush=True)' in source
    assert 'print(f"[FAIL] {index}/{total} {label} ({elapsed:.1f}s)", flush=True)' in source


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
    assert "_journal_visibility_worker" not in source
    assert '"--journal-path"' not in source
    assert "chmod(0o644)" not in source


def test_production_manager_and_gateway_have_no_fault_switches() -> None:
    manager = _text("software/python/plasma_manager/network_commissioning.py")
    server = _text("software/python/plasma_manager/server.py")
    gateway = _text("software/python/plasma_web/ppu_network_activation.py")
    combined = manager + server + gateway
    assert "crash-after-state" not in combined
    assert "STATIC_IPV4_FAULT_HELPER_ERROR" not in combined
    assert "fault_mode" not in combined


def test_release_workflow_runs_repeatability_gate_after_happy_path() -> None:
    workflow = _text(".github/workflows/ppu-release.yml")
    assert "scripts/static-ipv4-fault-injection-lab.py" in workflow
    assert "scripts/static-ipv4-fault-injection-repeatability.py" in workflow
    assert "scripts/private-ppu-evidence-verifier.py" in workflow
    assert "software/python/tests/test_static_ipv4_fault_injection_lab.py" in workflow
    happy = workflow.index("Run Virtual PPU Network Lab with production Manager")
    faults = workflow.index("Run Static IPv4 repeatability and privilege-parity gate")
    assert happy < faults


def test_fault_injection_document_is_indexed_and_keeps_hardware_claim_closed() -> None:
    index = _text("docs/README.md")
    doc = _text("docs/architecture/static-ipv4-fault-injection.md")
    assert "architecture/static-ipv4-fault-injection.md" in index
    assert "PYNQ-Z2" in doc
    assert "does **not** prove" in doc
    assert "recovery_required" in doc

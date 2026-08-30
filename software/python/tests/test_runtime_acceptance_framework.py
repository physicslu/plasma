from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HARNESS = REPO / "scripts" / "runtime_acceptance"
RUNNER = HARNESS / "run.py"


def test_runtime_acceptance_python_sources_compile() -> None:
    sources = sorted(HARNESS.glob("*.py"))
    assert {path.name for path in sources} >= {
        "common.py",
        "managed_ps_loopback.py",
        "emode_programming.py",
        "job_cancel.py",
        "pmode_batch.py",
        "eight_site_batch.py",
        "run.py",
    }
    for path in sources:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_runtime_acceptance_cli_exposes_expected_scenarios_without_network() -> None:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    for scenario in (
        "ps-loopback",
        "emode-programming",
        "job-cancel",
        "pmode-batch",
        "eight-site-batch",
        "managed-software",
    ):
        assert scenario in output
    assert "--allow-real-hardware" in output


def test_emode_runtime_acceptance_uses_current_server_side_batch_contract() -> None:
    source = (HARNESS / "emode_programming.py").read_text(encoding="utf-8")
    assert '"/api/batches"' in source
    assert "server-side-batch-envelope" in source
    assert "api/programming-assets/check" not in source
    assert 'f"{client.target_url(target)}/api/jobs"' not in source


def test_managed_runtime_acceptance_fails_closed_on_direct_gateway_base() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "require_managed_bff" in source
    assert "/api/manager/ppu" in source
    assert "direct Gateway routes are not Managed Mode evidence" in source
    assert 'payload.get("managed") is not True' in source
    assert 'payload.get("ppu_alias")' in source


def test_runtime_acceptance_evidence_is_not_repository_source() -> None:
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "artifacts/runtime-acceptance/" in gitignore


def test_runtime_acceptance_is_not_invoked_by_normal_cloud_ci() -> None:
    cloud_test = (REPO / "scripts" / "codex-cloud-test.sh").read_text(encoding="utf-8")
    assert "runtime_acceptance/run.py" not in cloud_test

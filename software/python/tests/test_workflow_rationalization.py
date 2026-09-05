from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_no_agent_scoped_workflow_files_on_mainline() -> None:
    offenders = sorted(path.name for path in WORKFLOWS.glob("agent-*.yml"))
    assert offenders == []


def test_retired_standalone_entrypoints_are_absent() -> None:
    retired = {
        "documentation-integrity.yml",
        "terminology-contract.yml",
        "web-e2e.yml",
        "ic-support-source-integrity.yml",
    }
    present = {path.name for path in WORKFLOWS.glob("*.yml")}
    assert retired.isdisjoint(present)


def test_repository_contracts_preserve_distinct_jobs_and_routing() -> None:
    entrypoint = _read("repository-contracts.yml")

    assert "  push:\n" in entrypoint
    assert "  pull_request:\n" in entrypoint
    assert "  documentation:\n" in entrypoint
    assert "  terminology:\n" in entrypoint
    assert "Test public documentation sanitization" in entrypoint
    assert "Test documentation integrity" in entrypoint
    assert "Self-test terminology guard" in entrypoint
    assert "Reject new retired domain vocabulary" in entrypoint
    assert "software/python/plasma_web/gateway_settings.py" in entrypoint
    assert "software/python/plasma_core/errors.py" in entrypoint
    assert 'path.startswith("software/python/")' in entrypoint
    assert 'path.startswith("software/web/")' in entrypoint


def test_web_validation_preserves_fast_and_e2e_event_boundaries() -> None:
    entrypoint = _read("web-tests.yml")

    assert "name: Web validation" in entrypoint
    assert "  workflow_dispatch:\n" in entrypoint
    assert "if: github.event_name != 'workflow_dispatch'" in entrypoint
    assert "github.event_name == 'pull_request'" in entrypoint
    assert "github.ref == 'refs/heads/main'" in entrypoint
    assert "Install visual regression CJK font" in entrypoint
    assert "Playwright E2E" in entrypoint
    assert "Upload visual regression diagnostics" in entrypoint


def test_ic_support_manual_source_lock_is_kept_in_domain_entrypoint() -> None:
    entrypoint = _read("ic-support-validation.yml")

    assert "  workflow_dispatch:\n" in entrypoint
    assert "if: github.event_name != 'workflow_dispatch'" in entrypoint
    assert "if: github.event_name == 'workflow_dispatch'" in entrypoint
    assert "  verify-official-source-lock:\n" in entrypoint
    assert "Verify locked official PDF bytes" in entrypoint
    assert "python data/ic-support/evidence/source_integrity.py verify" in entrypoint

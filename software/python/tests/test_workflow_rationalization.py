from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_no_agent_scoped_workflow_files_on_mainline() -> None:
    offenders = sorted(path.name for path in WORKFLOWS.glob("agent-*.yml"))
    assert offenders == []


def test_repository_contracts_are_single_top_level_entrypoint() -> None:
    dispatcher = _read("repository-contracts.yml")
    documentation = _read("documentation-integrity.yml")
    terminology = _read("terminology-contract.yml")

    assert "  push:\n" in dispatcher
    assert "  pull_request:\n" in dispatcher
    assert "uses: ./.github/workflows/documentation-integrity.yml" in dispatcher
    assert "uses: ./.github/workflows/terminology-contract.yml" in dispatcher

    for reusable in (documentation, terminology):
        assert "  workflow_call:\n" in reusable
        assert "  push:\n" not in reusable
        assert "  pull_request:\n" not in reusable
        assert "  workflow_dispatch:\n" not in reusable


def test_web_validation_preserves_fast_and_e2e_event_boundaries() -> None:
    entrypoint = _read("web-tests.yml")
    e2e = _read("web-e2e.yml")

    assert "name: Web validation" in entrypoint
    assert "  workflow_dispatch:\n" in entrypoint
    assert "if: github.event_name != 'workflow_dispatch'" in entrypoint
    assert "github.event_name == 'pull_request'" in entrypoint
    assert "github.ref == 'refs/heads/main'" in entrypoint
    assert "uses: ./.github/workflows/web-e2e.yml" in entrypoint

    assert "  workflow_call:\n" in e2e
    assert "  push:\n" not in e2e
    assert "  pull_request:\n" not in e2e
    assert "  workflow_dispatch:\n" not in e2e


def test_ic_support_manual_source_lock_is_routed_by_domain_entrypoint() -> None:
    entrypoint = _read("ic-support-validation.yml")
    source_lock = _read("ic-support-source-integrity.yml")

    assert "  workflow_dispatch:\n" in entrypoint
    assert "if: github.event_name != 'workflow_dispatch'" in entrypoint
    assert "if: github.event_name == 'workflow_dispatch'" in entrypoint
    assert "uses: ./.github/workflows/ic-support-source-integrity.yml" in entrypoint

    assert "  workflow_call:\n" in source_lock
    assert "  push:\n" not in source_lock
    assert "  pull_request:\n" not in source_lock
    assert "  workflow_dispatch:\n" not in source_lock

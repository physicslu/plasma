from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"


def test_pull_request_path_never_reaches_live_mutation_job() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in source
    assert "github.event_name != 'pull_request'" in source
    assert "github.repository == 'physicslu/plasma'" in source
    assert "github.ref == 'refs/heads/main'" in source
    assert "runs-on: [self-hosted, linux, x64, plasma-integration]" in source


def test_live_job_uses_clean_noncredentialed_checkout_and_evidence_upload() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "fetch-depth: 0" in source
    assert "clean: true" in source
    assert "persist-credentials: false" in source
    assert "--expected-commit \"$GITHUB_SHA\"" in source
    assert "if: always()" in source
    assert "z2like-demo-browser-runtime-live-${{ github.sha }}" in source

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"


def test_main_only_live_gate_has_explicit_repository_identity() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'test "$GITHUB_REPOSITORY" = "physicslu/plasma"' in source
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in source
    assert 'test "$(id -u)" -ne 0' in source

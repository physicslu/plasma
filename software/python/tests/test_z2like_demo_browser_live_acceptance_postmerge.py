from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"


def test_live_mutation_is_not_a_pull_request_job() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    live_job = source[source.index("  live-swpc-render-qemu:"):]
    assert "github.event_name != 'pull_request'" in live_job
    assert "github.ref == 'refs/heads/main'" in live_job
    assert "docker inspect plasma-z2like-demo-qemu" in live_job

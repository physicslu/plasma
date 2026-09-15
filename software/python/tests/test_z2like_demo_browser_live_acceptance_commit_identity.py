from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_live_gate_requires_render_commit_to_contain_triggering_main_commit() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "git merge-base" in source
    assert "--is-ancestor" in source
    assert 'session.request("/deployment.json"' in source
    assert "public Render deployment did not reach expected main ancestry" in source

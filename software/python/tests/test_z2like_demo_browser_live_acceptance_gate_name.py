from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"


def test_live_gate_name_is_explicit() -> None:
    assert "z2like-demo Browser Runtime live acceptance" in WORKFLOW.read_text(encoding="utf-8")

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"


def test_h021_live_gate_has_stable_name() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.startswith("name: z2like-demo Browser Runtime live acceptance\n")

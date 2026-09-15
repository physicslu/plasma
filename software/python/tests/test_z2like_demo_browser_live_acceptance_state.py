from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_gate_requires_commissioned_start() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "live acceptance requires a commissioned starting state" in source

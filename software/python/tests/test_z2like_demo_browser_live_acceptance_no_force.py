from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_no_force_lifecycle_recovery_exists() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "force=true" not in source
    assert "--force" not in source
    assert "force commission" not in source

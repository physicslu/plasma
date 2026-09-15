from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HANDOVER = ROOT / "handover" / "H021-z2like-demo-browser-runtime-deployment-plan-2026-09-14.md"


def test_h021_identifies_automated_and_remaining_live_evidence() -> None:
    source = HANDOVER.read_text(encoding="utf-8")
    assert "Implementation merged in PR #560" in source
    assert "Automated live coverage in this gate" in source
    assert "Still not live-qualified by this gate" in source
    assert "active Site Job" in source
    assert "stale/non-idle" in source
    assert "15-minute capability expiry" in source
    assert "H021 is not fully closed" in source

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_report_does_not_claim_remaining_live_negative_cases() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"not_live_qualified_by_this_gate"' in source
    assert "active-Site-Job disable rejection" in source
    assert "forced stale/non-idle maintenance proof rejection" in source
    assert "15-minute capability expiry wall-clock rejection" in source


def test_failure_path_is_fail_closed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "No force-commission fallback is permitted" in source
    assert "cleanup could not restore commissioned lifecycle" in source
    assert "_set_lifecycle(session, args.alias, \"commissioned\", timeout_s=120.0)" in source

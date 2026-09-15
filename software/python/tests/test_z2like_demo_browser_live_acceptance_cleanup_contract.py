from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_cleanup_never_bypasses_manager_lifecycle_gate() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "force-commission" not in source.lower()
    assert '_set_lifecycle(session, args.alias, "commissioned", timeout_s=120.0)' in source
    assert "lifecycle_disabled" in source
    assert "cleanup could not restore commissioned lifecycle" in source

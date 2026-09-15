from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_wrong_pair_precedes_verified_pair_and_capability_use() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    wrong = source.index("wrong Bootstrap pairing token")
    correct = source.index("correct Bootstrap pairing while commissioned")
    disable = source.index('_set_lifecycle(session, args.alias, "disabled", timeout_s=30.0)')
    assert wrong < correct < disable

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_runtime_deploy_requires_disabled_lifecycle_then_returns_commissioned() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    disable = source.index('_set_lifecycle(session, args.alias, "disabled", timeout_s=30.0)')
    deploy = source.index("deployment = _upload_and_deploy(")
    commission = source.index('_set_lifecycle(session, args.alias, "commissioned", timeout_s=90.0)')
    assert disable < deploy < commission

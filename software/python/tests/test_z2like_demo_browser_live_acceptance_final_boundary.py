from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HANDOVER = ROOT / "handover" / "H021-z2like-demo-browser-runtime-deployment-plan-2026-09-14.md"


def test_physical_z2_and_ic_claims_remain_excluded() -> None:
    source = HANDOVER.read_text(encoding="utf-8")
    assert "Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED" in source
    assert "no claim for PL/FPGA behavior" in source
    assert "real IC programming" in source
    assert "physical multi-Site concurrency" in source

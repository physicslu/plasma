from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HANDOVER = ROOT / "handover" / "H021-z2like-demo-browser-runtime-deployment-plan-2026-09-14.md"


def test_h021_gate_scope_is_qemu_simulation_only() -> None:
    source = HANDOVER.read_text(encoding="utf-8")
    assert "live SWPC/Render qualification still pending" in source
    assert "QEMU 172.30.77.2:18081" in source

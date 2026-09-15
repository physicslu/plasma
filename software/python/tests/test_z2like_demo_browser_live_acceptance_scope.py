from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_live_gate_requires_canonical_public_alias_and_endpoints_by_default() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'default="https://z2like-demo.open4th.com"' in source
    assert 'default="https://ppu-managed-lab.open4th.com"' in source
    assert 'default="z2like-qemu"' in source
    assert 'default="plasma-z2like-demo-qemu"' in source
    assert 'default="http://127.0.0.1:18082"' in source

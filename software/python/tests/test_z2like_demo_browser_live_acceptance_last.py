from __future__ import annotations

from pathlib import Path


def test_live_gate_files_are_present() -> None:
    root = Path(__file__).resolve().parents[3]
    assert (root / "scripts/z2like-demo-browser-live-acceptance.py").is_file()
    assert (root / ".github/workflows/z2like-demo-browser-live-acceptance.yml").is_file()

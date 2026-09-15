from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"


def test_negative_browser_mutations_are_exercised_before_runtime_maintenance() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    negative_markers = (
        "lifecycle PATCH without capability",
        "cross-origin lifecycle mutation",
        "tampered maintenance capability",
        "cross-origin Bootstrap mutation",
        "commissioned Bootstrap upload",
        "commissioned Bootstrap deployment",
    )
    disable_index = source.index('_set_lifecycle(session, args.alias, "disabled", timeout_s=30.0)')
    for marker in negative_markers:
        assert source.index(marker) < disable_index


def test_live_gate_never_uses_direct_qemu_bootstrap_mutation_url() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "172.30.77.2:18081" not in source
    assert "/api/manager/registry/{alias}/bootstrap" in source
    assert "/__plasma/bootstrap/v1/status" in source

"""Host-only helper: seed the LOM-P2A-2 PPU controller record for tests.

Replaces the retired ``provision-token`` fixture. Writes the same atomic,
root-private records the real enrollment engine commits (via
``ControllerStore``); it does not enroll anything on real hardware.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _controller():
    name = "plasma_ppu_controller_test_fixture"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "ppu_controller.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def seed_controller(state_root: Path, credential: str, *, generation: int | None = None,
                    mode: str = "NORMAL") -> str:
    """Install ``credential`` as the current controller (next generation)."""
    module = _controller()
    store = module.ControllerStore(Path(state_root))
    with store.locked():
        ledger = store.ledger()
        current = store.get("controller")
        if generation is None:
            generation = max(ledger["high_water"], current["generation"] if current else 0) + 1
        store.put("controller", {
            "schema": module.CONTROLLER_RECORD_SCHEMA, "generation": generation,
            "credential": credential, "mode": mode, "controller_id": "0" * 32,
            "label": "host-test", "last_enrollment": {"source": "host-test"}})
        ledger["high_water"] = max(ledger["high_water"], generation)
        store.put("ledger", ledger)
    return credential


def clear_controller(state_root: Path) -> None:
    store = _controller().ControllerStore(Path(state_root))
    with store.locked():
        store.delete("controller")


def current_credential(state_root: Path) -> str | None:
    record = _controller().ControllerStore(Path(state_root)).get("controller")
    return record["credential"] if record else None

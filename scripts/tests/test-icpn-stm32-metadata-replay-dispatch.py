#!/usr/bin/env python3
"""Unprivileged routing regression for STM32 metadata replay consolidation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "scripts/ci/icpn_stm32_metadata_replay_dispatch.py"
spec = importlib.util.spec_from_file_location("icpn_stm32_metadata_replay_dispatch", path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.self_test()
assert module.matrix_for(["f2", "f7"]) == {
    "include": [{"family":"f2","runner":"ubuntu-24.04"}, {"family":"f7","runner":"ubuntu-24.04"}]
}
assert module.affected_families([module.ARCHIVED["wl3"]["test"]]) == ["wl3"]
assert module.affected_families([module.CONTRACT_TEST]) == list(module.FAMILIES)
print("STM32 metadata replay consolidation routing tests: PASS")

#!/usr/bin/env python3
"""ADR-0002 single-authority governance checks.

ADR-0002 is the only normative cross-manufacturer policy for IC discovery,
Catalog Level 1/2/3, Registry/Selector visibility, and execution separation.
This test validates the ADR text; it does not define a second policy.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs/adr/0002-openocd-software-qualified-catalog-visibility.md"


def main() -> int:
    text = ADR.read_text(encoding="utf-8")

    required = (
        "Catalog Level 1 — IC Identity",
        "Catalog Level 2 — Programming Qualified",
        "Catalog Level 3 — PLASMA Verified",
        "Catalog Level 1 `IDENTIFIED`",
        "Catalog Level 2 `PROGRAMMABLE`",
        "Catalog Level 3 `PLASMA_VERIFIED`",
        "Level 3 PLASMA_VERIFIED ⊆ Level 2 PROGRAMMABLE ⊆ Level 1 IDENTIFIED",
        "Canonical Device Registry",
        "Programming Catalog / IC Selector View",
        "ProgrammingQualification.state == SUPPORTED",
        "Cross-vendor discovery execution order",
        "現階段的 ST、NXP、Microchip 與未來任何 Manufacturer 一律使用相同的 discovery 執行順序",
        "本 ADR-0002 是上述 discovery 方法的唯一規範來源",
        "Device Registry、但不出現在一般 IC Selector",
        "Programming Catalog／IC Selector 顯示永遠不直接授權燒錄",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(f"ADR-0002 required policy text missing: {missing}")

    forbidden_patterns = {
        "legacy S1/S2/S3 alias": r"\bS[123](?:_complete)?\b",
        "legacy P0/P1/P2 priority": r"\bP[012]\b",
        "legacy Phase 1 heading": r"Phase 1 — IC Information",
        "legacy Phase 2 heading": r"Phase 2 — Programming",
        "legacy Phase 3 heading": r"Phase 3 — PLASMA Compatibility",
        "secondary canonical discovery contract": r"IC Discovery Canonical Contract",
    }
    for label, pattern in forbidden_patterns.items():
        if re.search(pattern, text):
            raise SystemExit(f"ADR-0002 contains forbidden {label}")

    for maker in ("ST", "NXP", "Microchip"):
        if maker not in text:
            raise SystemExit(f"ADR-0002 lost representative manufacturer: {maker}")
    if "差異只允許存在於原廠資料取得介面" not in text:
        raise SystemExit("ADR-0002 no longer constrains manufacturer-specific acquisition to source adapters")
    if "相同證據強度必須得到相同 Catalog Level 判定" not in text:
        raise SystemExit("ADR-0002 lost cross-manufacturer equal-evidence rule")

    print("ADR-0002 single-authority cross-manufacturer Catalog Level contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

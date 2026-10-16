#!/usr/bin/env python3
"""ADR-0002 single-authority governance checks.

ADR-0002 is the only normative cross-manufacturer policy for IC discovery,
Catalog Level 0/1/2/3, Registry/Selector visibility, and execution separation.
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
        "Level 0 — DISCOVERED",
        "Level 1 — PROGRAMMING_CANDIDATE",
        "Level 2 — PROGRAMMABLE",
        "Level 3 — PLASMA_VERIFIED",
        "Level 3 PLASMA_VERIFIED ⊆ Level 2 PROGRAMMABLE ⊆ Level 1 PROGRAMMING_CANDIDATE ⊆ Level 0 DISCOVERED",
        "Internal Research Registry",
        "Customer-facing IC Selector View",
        "Job Picker",
        "ProgrammingQualification.state == SUPPORTED",
        "Cross-vendor discovery execution order",
        "現階段的 ST、NXP、Microchip 與未來任何 Manufacturer 一律使用相同的 discovery 執行順序",
        "本 ADR-0002 是上述 discovery 方法的唯一規範來源",
        "L0 `DISCOVERED` 決定 Internal Research Registry membership",
        "L1 `PROGRAMMING_CANDIDATE` 起即可進一般 Customer IC Selector",
        "L2 `PROGRAMMABLE` 起才可進 Job Picker",
        "Catalog visibility、Job selection 與最終 execution entitlement 是三個不同 gate",
        "不得保留** `phase1_*`／`phase2_*`／`phase3_*` 欄位",
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

    active_contract_files = (
        ROOT / "software/python/plasma_web/device_catalog.py",
        ROOT / "software/python/plasma_web/programming_qualification.py",
        ROOT / "software/python/plasma_web/gateway.py",
        ROOT / "software/web/app/device-catalog-api.ts",
    )
    forbidden_active_tokens = (
        "phase1_",
        "phase2_",
        "phase3_",
        "microchip_phase1_ic_information",
        "selector_visibility_authority",
    )
    for path in active_contract_files:
        active = path.read_text(encoding="utf-8")
        for token in forbidden_active_tokens:
            if token in active:
                raise SystemExit(f"active Catalog contract retained forbidden token {token!r}: {path}")

    print("ADR-0002 single-authority cross-manufacturer Catalog Level contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

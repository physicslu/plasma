#!/usr/bin/env python3
"""ADR-0002 single-authority governance checks.

ADR-0002 is the only normative cross-vendor policy for IC discovery,
Phase 1/2/3 status, Selector visibility, and execution separation.
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
        "Phase 1 — IC Information",
        "Phase 2 — Programming",
        "Phase 3 — PLASMA Compatibility",
        "Phase 1 `IDENTIFIED`",
        "Phase 1 `INFORMATION_COMPLETE`",
        "Phase 2 `SUPPORTED`",
        "Phase 3 `PASSED`",
        "Phase 3 `PASSED` ⊆ Phase 2 `SUPPORTED` ⊆ Phase 1 `IDENTIFIED`",
        "Cross-vendor discovery execution order",
        "ST、NXP、Microchip 與未來 Brand 一律使用相同的 discovery 執行順序",
        "本 ADR-0002 是上述 discovery 方法的唯一規範來源",
        "Phase 1 `IDENTIFIED` 的 Exact ICPN 應可由 Catalog／IC Selector 查詢",
        "Catalog／IC Selector 顯示永遠不直接授權燒錄",
        "Phase 2 `UNKNOWN／CANDIDATE／SUPPORTED／UNSUPPORTED`",
        "Phase 3 `NOT_TESTED／PASSED／FAILED`",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(f"ADR-0002 required policy text missing: {missing}")

    forbidden_patterns = {
        "legacy S1/S2/S3 alias": r"\bS[123](?:_complete)?\b",
        "legacy P0/P1/P2 priority": r"\bP[012]\b",
        "SUPPORTED-only selector policy": r"SUPPORTED-only",
        "secondary canonical discovery contract": r"IC Discovery Canonical Contract",
    }
    for label, pattern in forbidden_patterns.items():
        if re.search(pattern, text):
            raise SystemExit(f"ADR-0002 contains forbidden {label}")

    for maker in ("ST", "NXP", "Microchip"):
        if maker not in text:
            raise SystemExit(f"ADR-0002 lost representative vendor: {maker}")
    if "差異只允許存在於原廠資料取得介面" not in text:
        raise SystemExit("ADR-0002 no longer constrains vendor-specific acquisition to source adapters")
    if "相同證據強度必須得到相同 Phase 判定" not in text:
        raise SystemExit("ADR-0002 lost cross-vendor equal-evidence rule")

    print("ADR-0002 single-authority cross-vendor contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

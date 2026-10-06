#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

ACTIVE = HERE / "st-stm32f2-active-exact-mpn-v3.8.txt"
GAP = HERE / "stm32f2-active-exact-gap-v3.8.txt"
CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F7_PUBLICATION = HERE / "stm32f7-layer1-production-publication-v3.7.json"

EXPECTED_ACTIVE = 105
EXPECTED_CURRENT = 33
EXPECTED_GAP = 72
EXPECTED_ACTIVE_SHA256 = "60bf4cfcc07c5ec13bb11b290ea5e71da95f56f0fc4b1cdc2a05beaabe17986a"
EXPECTED_GAP_SHA256 = "1ba037ac5bba68ab4907742e97be0d9d56fd15f5e32b89899a67359c6703f584"
EXPECTED_ACTIVE_SERIES = {
    "STM32F205": 47,
    "STM32F207": 33,
    "STM32F215": 12,
    "STM32F217": 13,
}
EXPECTED_GAP_SERIES = {
    "STM32F205": 35,
    "STM32F207": 25,
    "STM32F215": 7,
    "STM32F217": 5,
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def lines(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def digest(rows: list[str]) -> str:
    return hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    active = lines(ACTIVE)
    gap = lines(GAP)
    req(active == sorted(active), "F2 Active ledger must be sorted")
    req(gap == sorted(gap), "F2 gap ledger must be sorted")
    req(len(active) == EXPECTED_ACTIVE and len(set(active)) == EXPECTED_ACTIVE,
        "F2 Active count/unique drift")
    req(len(gap) == EXPECTED_GAP and len(set(gap)) == EXPECTED_GAP,
        "F2 gap count/unique drift")
    req(digest(active) == EXPECTED_ACTIVE_SHA256, "F2 Active exact-set digest drift")
    req(digest(gap) == EXPECTED_GAP_SHA256, "F2 gap exact-set digest drift")
    req(all(x.startswith("STM32F2") for x in active + gap), "non-F2 identity in F2 ledgers")

    current_rows = read_csv(CANONICAL)
    current = sorted(row["icpn"] for row in current_rows)
    req(len(current) == EXPECTED_CURRENT and len(set(current)) == EXPECTED_CURRENT,
        "F2 Production canonical count/unique drift")
    req(set(current) <= set(active), "F2 Production identity outside locked Active set")
    req(sorted(set(active) - set(current)) == gap,
        "F2 gap is not exact Active-minus-current-Production difference")

    active_series = dict(sorted(Counter(x[:9] for x in active).items()))
    gap_series = dict(sorted(Counter(x[:9] for x in gap).items()))
    req(active_series == EXPECTED_ACTIVE_SERIES, "F2 Active series distribution drift")
    req(gap_series == EXPECTED_GAP_SERIES, "F2 gap series distribution drift")
    req(sum(x.endswith("TR") for x in active) == 41, "F2 Active TR distribution drift")
    req(sum(x.endswith("TR") for x in gap) == 29, "F2 gap TR distribution drift")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    f2_sources = [
        s for s in manifest["sources"]
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32F2"
    ]
    req(len(f2_sources) == 1, "Production F2 source missing/duplicated")
    source = f2_sources[0]
    req(source["row_count"] == 33
        and source["git_blob_sha"] == "1bec0770179f3849c6cfbb66aea9ad9d63610f55"
        and source["sha256"] == "69a9e02be14237bd2c683bc63eed4bd132ba62c5e8c334ef0e85671f868003d0",
        "F2 Production source prestate drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"]) == 4242,
        "Production exact total prestate drift")

    f7 = json.loads(F7_PUBLICATION.read_text(encoding="utf-8"))
    cov = f7["coverage_effect"]
    req(cov["whole_st_active_exact_denominator"] == 4550,
        "whole-ST Active denominator post-F7 drift")
    req(cov["whole_st_active_intersection_after"] == 4163,
        "whole-ST Active intersection post-F7 drift")
    req(cov["whole_st_active_gap_after"] == 387,
        "whole-ST Active gap post-F7 drift")

    summary = {
        "audit_id": "stm32f2-active-exact-gap-lock-v3.8",
        "current_active_exact_count": len(active),
        "current_production_f2_exact_count": len(current),
        "active_exact_gap_count": len(gap),
        "active_exact_set_sha256": EXPECTED_ACTIVE_SHA256,
        "active_exact_gap_sha256": EXPECTED_GAP_SHA256,
        "active_series_counts": active_series,
        "gap_series_counts": gap_series,
        "tr_active_count": 41,
        "tr_gap_count": 29,
        "catalog_layer1_only": True,
        "backend_or_profile_scope": False,
        "metadata_authority_replay_complete": False,
        "production_write_authorized": False,
        "projected_if_all_72_later_approved": {
            "production_exact_total": 4314,
            "whole_st_active_intersection": 4235,
            "whole_st_active_gap": 315,
            "whole_st_active_coverage_percent": 93.0769,
        },
        "next_gate": (
            "Replay all 72 missing STM32F2 exact identities against official ST Ordering "
            "Information authority before preparing any Layer-1 admission proposal."
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32F2_ACTIVE_EXACT_GAP_LOCK_V38_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

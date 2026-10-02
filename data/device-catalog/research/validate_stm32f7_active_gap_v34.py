#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

GAP = HERE / "stm32f7-active-exact-gap-v3.4.txt"
FAMILY_BREAKDOWN = HERE / "st-estore-v13-family-coverage-v1.4.csv"
SOURCE_LOCK = HERE / "st-estore-active-exact-coverage-lock-v1.4.json"
CANONICAL = HERE / "stm32f7-commercial-icpn.csv"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F3_PUBLICATION = HERE / "stm32f3-layer1-production-publication-v3.3.json"

EXPECTED_ACTIVE = 173
EXPECTED_CURRENT = 19
EXPECTED_GAP = 154
EXPECTED_ACTIVE_SHA256 = "1b4b4692ed4a4f98984d2474e498ed8593739c093e7fb403bb966fcf70f7a736"
EXPECTED_GAP_SHA256 = "ec93408ecec154bf40a6fcd4d5ddb063e5e36cb023bc19bbed13b306a3b4a931"

FROZEN_CURRENT = {
    "STM32F722ICK6",
    "STM32F722ICT6",
    "STM32F723ICK6",
    "STM32F723ICT6",
    "STM32F730I8K6",
    "STM32F730I8K6TR",
    "STM32F732IEK6",
    "STM32F732IET6",
    "STM32F733IEK6",
    "STM32F733IET6",
    "STM32F745IEK6",
    "STM32F745IEK6TR",
    "STM32F745IEK7",
    "STM32F745IEK7TR",
    "STM32F745IET6",
    "STM32F745IET7",
    "STM32F750N8H6",
    "STM32F778AIY6TR",
    "STM32F779AIY6TR",
}

EXPECTED_ACTIVE_SERIES = {
    "STM32F722": 20,
    "STM32F723": 14,
    "STM32F730": 7,
    "STM32F732": 6,
    "STM32F733": 6,
    "STM32F745": 20,
    "STM32F746": 22,
    "STM32F750": 4,
    "STM32F756": 8,
    "STM32F765": 27,
    "STM32F767": 19,
    "STM32F769": 5,
    "STM32F777": 11,
    "STM32F778": 1,
    "STM32F779": 3,
}

EXPECTED_GAP_SERIES = {
    "STM32F722": 18,
    "STM32F723": 12,
    "STM32F730": 5,
    "STM32F732": 4,
    "STM32F733": 4,
    "STM32F745": 14,
    "STM32F746": 22,
    "STM32F750": 3,
    "STM32F756": 8,
    "STM32F765": 27,
    "STM32F767": 19,
    "STM32F769": 5,
    "STM32F777": 11,
    "STM32F779": 2,
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def load_gap() -> list[str]:
    rows = [x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "F7 gap ledger must be sorted")
    req(len(rows) == EXPECTED_GAP and len(set(rows)) == EXPECTED_GAP,
        "F7 gap ledger count/unique drift")
    req(digest(rows) == EXPECTED_GAP_SHA256, "F7 gap digest drift")
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    gap = load_gap()

    source_lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    req(source_lock["source_workflow_run_id"] == 36797087427, "source run provenance drift")
    req(source_lock["source_workflow_head_sha"] ==
        "5b016c0fd54cb186080806efd3f2660472f5b6a4", "source head provenance drift")
    req(source_lock["source_result_artifact_id"] == 11134202297, "source artifact id drift")
    req(source_lock["source_result_artifact_zip_sha256"] ==
        "663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d",
        "source artifact digest drift")
    req(source_lock["estore_active_exact_denominator"] == 4550,
        "whole-ST Active denominator drift")

    family_rows = read_csv(FAMILY_BREAKDOWN)
    f7 = [row for row in family_rows if row["family"] == "STM32F7"]
    req(len(f7) == 1, "F7 family-breakdown row missing/duplicated")
    row = f7[0]
    req(int(row["estore_active_exact"]) == EXPECTED_ACTIVE, "F7 Active denominator drift")
    req(int(row["production_active_intersection"]) == EXPECTED_CURRENT,
        "frozen F7 Active intersection drift")
    req(int(row["active_missing_from_production"]) == EXPECTED_GAP,
        "frozen F7 gap count drift")

    current_rows = read_csv(CANONICAL)
    current = {row["icpn"] for row in current_rows}
    req(len(current) == EXPECTED_CURRENT and current == FROZEN_CURRENT,
        "F7 Production prestate exact set drift")
    req(current.isdisjoint(gap), "F7 gap overlaps current Production")

    active = sorted(current | set(gap))
    req(len(active) == EXPECTED_ACTIVE, "F7 reconstructed Active count drift")
    req(digest(active) == EXPECTED_ACTIVE_SHA256, "F7 reconstructed Active-set digest drift")
    req(all(x.startswith("STM32F7") for x in active), "non-F7 identity in reconstructed Active set")

    active_counts = dict(sorted(Counter(x[:9] for x in active).items()))
    gap_counts = dict(sorted(Counter(x[:9] for x in gap).items()))
    req(active_counts == EXPECTED_ACTIVE_SERIES, "F7 Active series distribution drift")
    req(gap_counts == EXPECTED_GAP_SERIES, "F7 gap series distribution drift")
    req(sum(x.endswith("TR") for x in active) == 39, "F7 Active TR distribution drift")
    req(sum(x.endswith("TR") for x in gap) == 34, "F7 gap TR distribution drift")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    f7_sources = [
        s for s in manifest["sources"]
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32F7"
    ]
    req(len(f7_sources) == 1, "Production F7 source missing/duplicated")
    source = f7_sources[0]
    req(source["row_count"] == 19
        and source["git_blob_sha"] == "d61ebd2c56edf6bb7b1cadc381c23d071fe7967f"
        and source["sha256"] == "c71434cc85068353a1aabdfe24059573c3e8092505fcdb1d6eda7f2374fa64d7",
        "F7 Production source prestate drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"]) == 4088,
        "Production exact total prestate drift")

    f3 = json.loads(F3_PUBLICATION.read_text(encoding="utf-8"))
    coverage = f3["coverage_effect"]
    req(coverage["whole_st_active_exact_denominator"] == 4550,
        "whole-ST Active denominator post-F3 drift")
    req(coverage["whole_st_active_intersection_after"] == 4009,
        "whole-ST Active intersection post-F3 drift")
    req(coverage["whole_st_active_gap_after"] == 541,
        "whole-ST Active gap post-F3 drift")

    summary = {
        "audit_id": "stm32f7-active-exact-gap-lock-v3.4",
        "source": {
            "workflow_run_id": 36797087427,
            "head_sha": "5b016c0fd54cb186080806efd3f2660472f5b6a4",
            "artifact_id": 11134202297,
            "artifact_zip_sha256":
                "663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d",
        },
        "current_active_exact_count": len(active),
        "current_production_f7_exact_count": len(current),
        "active_exact_gap_count": len(gap),
        "active_exact_set_sha256": EXPECTED_ACTIVE_SHA256,
        "active_exact_gap_sha256": EXPECTED_GAP_SHA256,
        "active_series_counts": active_counts,
        "gap_series_counts": gap_counts,
        "tr_active_count": 39,
        "tr_gap_count": 34,
        "catalog_layer1_only": True,
        "backend_or_profile_scope": False,
        "metadata_authority_replay_complete": False,
        "production_write_authorized": False,
        "projected_if_all_154_later_approved": {
            "production_exact_total": 4242,
            "whole_st_active_intersection": 4163,
            "whole_st_active_gap": 387,
            "whole_st_active_coverage_percent": 91.4945,
        },
        "next_gate": (
            "Replay all 154 missing exact identities against official ST STM32F7 "
            "Ordering Information authority, preserving package-specific pin semantics "
            "and the existing narrow STM32F750 metadata boundary."
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32F7_ACTIVE_EXACT_GAP_LOCK_V34_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

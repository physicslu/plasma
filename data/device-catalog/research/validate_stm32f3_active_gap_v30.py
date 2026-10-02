#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

ACTIVE = HERE / "st-stm32f3-active-exact-mpn-v3.0.txt"
GAP = HERE / "stm32f3-active-exact-gap-v3.0.txt"
CANONICAL = HERE / "stm32f3-commercial-icpn.csv"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
SOURCE_LOCK = HERE / "st-estore-active-exact-coverage-lock-v1.4.json"
H5_PUBLICATION = HERE / "stm32h5-layer1-production-publication-v2.9.json"

EXPECTED_ACTIVE = 192
EXPECTED_CURRENT = 10
EXPECTED_GAP = 182
EXPECTED_ACTIVE_SHA256 = "e3149bf214375dd50c20919fb2b42ec127626ba6440f62ea90f62e7fe6cde641"
EXPECTED_GAP_SHA256 = "1514c8edd3d190a8fd2bc9c27960c47f05ab4536640e008d73e4d5ab2f5a01d7"
EXPECTED_SERIES_ACTIVE = {
    "STM32F301": 24,
    "STM32F302": 51,
    "STM32F303": 56,
    "STM32F318": 4,
    "STM32F328": 1,
    "STM32F334": 24,
    "STM32F358": 3,
    "STM32F373": 23,
    "STM32F378": 5,
    "STM32F398": 1,
}
EXPECTED_SERIES_GAP = {
    "STM32F301": 21,
    "STM32F302": 50,
    "STM32F303": 55,
    "STM32F318": 2,
    "STM32F328": 1,
    "STM32F334": 23,
    "STM32F358": 3,
    "STM32F373": 21,
    "STM32F378": 5,
    "STM32F398": 1,
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_lines(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    active = load_lines(ACTIVE)
    gap = load_lines(GAP)
    current_rows = read_csv(CANONICAL)
    current = sorted(row["icpn"] for row in current_rows)

    req(len(active) == EXPECTED_ACTIVE and len(set(active)) == EXPECTED_ACTIVE,
        "F3 Active exact ledger count/unique drift")
    req(len(gap) == EXPECTED_GAP and len(set(gap)) == EXPECTED_GAP,
        "F3 gap ledger count/unique drift")
    req(active == sorted(active), "F3 Active ledger must be sorted")
    req(gap == sorted(gap), "F3 gap ledger must be sorted")
    req(all(x.startswith("STM32F3") for x in active + gap), "non-F3 identity in F3 ledgers")
    req(digest(active) == EXPECTED_ACTIVE_SHA256, "F3 Active exact-set digest drift")
    req(digest(gap) == EXPECTED_GAP_SHA256, "F3 gap exact-set digest drift")

    req(len(current) == EXPECTED_CURRENT and len(set(current)) == EXPECTED_CURRENT,
        "F3 Production canonical prestate drift")
    req(set(current) <= set(active), "published F3 identity is outside locked current Active set")
    req(sorted(set(active) - set(current)) == gap,
        "F3 gap is not exact Active-minus-current-Production difference")

    active_counts = dict(sorted(Counter(x[:9] for x in active).items()))
    gap_counts = dict(sorted(Counter(x[:9] for x in gap).items()))
    req(active_counts == EXPECTED_SERIES_ACTIVE, "F3 Active series distribution drift")
    req(gap_counts == EXPECTED_SERIES_GAP, "F3 gap series distribution drift")

    source_lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    req(source_lock["source_workflow_run_id"] == 36797087427, "source run provenance drift")
    req(source_lock["source_workflow_head_sha"] == "5b016c0fd54cb186080806efd3f2660472f5b6a4",
        "source head provenance drift")
    req(source_lock["source_result_artifact_id"] == 11134202297, "source artifact id drift")
    req(source_lock["source_result_artifact_zip_sha256"] ==
        "663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d",
        "source artifact digest drift")
    req(source_lock["estore_active_exact_denominator"] == 4550,
        "whole-ST Active denominator drift")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    f3_sources = [
        s for s in manifest["sources"]
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32F3"
    ]
    req(len(f3_sources) == 1 and f3_sources[0]["row_count"] == EXPECTED_CURRENT,
        "Production F3 manifest prestate drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"]) == 3906,
        "Production exact total prestate drift")

    h5 = json.loads(H5_PUBLICATION.read_text(encoding="utf-8"))
    req(h5["coverage_effect"]["whole_st_active_intersection_after"] == 3827,
        "whole-ST Active intersection prestate drift")
    req(h5["coverage_effect"]["whole_st_active_gap_after"] == 723,
        "whole-ST Active gap prestate drift")

    summary = {
        "audit_id": "stm32f3-active-exact-gap-lock-v3.0",
        "source": {
            "workflow_run_id": 36797087427,
            "head_sha": "5b016c0fd54cb186080806efd3f2660472f5b6a4",
            "artifact_id": 11134202297,
            "artifact_zip_sha256": "663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d",
        },
        "current_active_exact_count": len(active),
        "current_production_f3_exact_count": len(current),
        "active_exact_gap_count": len(gap),
        "active_exact_set_sha256": EXPECTED_ACTIVE_SHA256,
        "active_exact_gap_sha256": EXPECTED_GAP_SHA256,
        "active_series_counts": active_counts,
        "gap_series_counts": gap_counts,
        "tr_active_count": sum(x.endswith("TR") for x in active),
        "tr_gap_count": sum(x.endswith("TR") for x in gap),
        "catalog_layer1_only": True,
        "backend_or_profile_scope": False,
        "metadata_authority_replay_complete": False,
        "production_write_authorized": False,
        "projected_if_all_182_later_approved": {
            "production_exact_total": 4088,
            "whole_st_active_intersection": 4009,
            "whole_st_active_gap": 541,
            "whole_st_active_coverage_percent": 88.1099,
        },
        "next_gate": (
            "Expand official ST Ordering Information authority across all ten active STM32F3 series "
            "and fail-closed replay the 182 missing exact identities before any Layer-1 admission proposal."
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32F3_ACTIVE_EXACT_GAP_LOCK_V30_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

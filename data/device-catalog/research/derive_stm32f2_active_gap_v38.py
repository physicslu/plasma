#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
FAMILY_BREAKDOWN = HERE / "st-estore-v13-family-coverage-v1.4.csv"
SOURCE_LOCK = HERE / "st-estore-active-exact-coverage-lock-v1.4.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F7_PUBLICATION = HERE / "stm32f7-layer1-production-publication-v3.7.json"

EXPECTED_ACTIVE = 105
EXPECTED_CURRENT = 33
EXPECTED_GAP = 72


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def read_lines(path: Path) -> list[str]:
    return sorted(x.strip().upper() for x in path.read_text(encoding="utf-8").splitlines() if x.strip())


def digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-root", type=Path, required=True)
    parser.add_argument("--output-active", type=Path)
    parser.add_argument("--output-gap", type=Path)
    args = parser.parse_args()

    active_all = read_lines(args.coverage_root / "active-exact-all.txt")
    frozen_missing_all = read_lines(args.coverage_root / "active-missing-from-production.txt")
    f2_active = [x for x in active_all if x.startswith("STM32F2")]
    f2_frozen_gap = [x for x in frozen_missing_all if x.startswith("STM32F2")]

    req(len(f2_active) == EXPECTED_ACTIVE and len(set(f2_active)) == EXPECTED_ACTIVE,
        f"F2 Active exact count/unique drift: {len(f2_active)}")
    req(len(f2_frozen_gap) == EXPECTED_GAP and len(set(f2_frozen_gap)) == EXPECTED_GAP,
        f"F2 frozen gap count/unique drift: {len(f2_frozen_gap)}")

    current_rows = read_csv(CANONICAL)
    current = sorted(row["icpn"].strip().upper() for row in current_rows)
    req(len(current) == EXPECTED_CURRENT and len(set(current)) == EXPECTED_CURRENT,
        "F2 Production canonical count/unique drift")
    req(set(current) <= set(f2_active), "current F2 Production includes identity outside locked Active set")

    current_gap = sorted(set(f2_active) - set(current))
    req(current_gap == f2_frozen_gap,
        "current F2 Active-minus-Production differs from frozen #685 gap")

    family_rows = read_csv(FAMILY_BREAKDOWN)
    f2 = [row for row in family_rows if row["family"] == "STM32F2"]
    req(len(f2) == 1, "F2 family-breakdown row missing/duplicated")
    req(int(f2[0]["estore_active_exact"]) == EXPECTED_ACTIVE, "F2 family Active denominator drift")
    req(int(f2[0]["production_active_intersection"]) == EXPECTED_CURRENT,
        "F2 frozen Active intersection drift")
    req(int(f2[0]["active_missing_from_production"]) == EXPECTED_GAP,
        "F2 frozen gap drift")

    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    req(lock["source_workflow_run_id"] == 36797087427, "source run provenance drift")
    req(lock["source_workflow_head_sha"] == "5b016c0fd54cb186080806efd3f2660472f5b6a4",
        "source head provenance drift")
    req(lock["source_result_artifact_id"] == 11134202297, "source artifact id drift")
    req(lock["source_result_artifact_zip_sha256"] ==
        "663d733cd6112bcffa4f7cf3d436b8a6e98ea91039e17dfb8493d8c4dbaf7d1d",
        "source artifact digest drift")
    req(lock["estore_active_exact_denominator"] == 4550, "whole-ST Active denominator drift")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    f2_sources = [
        s for s in manifest["sources"]
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32F2"
    ]
    req(len(f2_sources) == 1 and f2_sources[0]["row_count"] == EXPECTED_CURRENT,
        "Production F2 source prestate drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"]) == 4242,
        "Production exact total prestate drift")

    f7 = json.loads(F7_PUBLICATION.read_text(encoding="utf-8"))
    cov = f7["coverage_effect"]
    req(cov["whole_st_active_exact_denominator"] == 4550, "whole-ST denominator post-F7 drift")
    req(cov["whole_st_active_intersection_after"] == 4163, "whole-ST intersection post-F7 drift")
    req(cov["whole_st_active_gap_after"] == 387, "whole-ST gap post-F7 drift")

    active_series = dict(sorted(Counter(x[:9] for x in f2_active).items()))
    gap_series = dict(sorted(Counter(x[:9] for x in current_gap).items()))

    if args.output_active:
        args.output_active.write_text("\n".join(f2_active) + "\n", encoding="utf-8")
    if args.output_gap:
        args.output_gap.write_text("\n".join(current_gap) + "\n", encoding="utf-8")

    summary = {
        "audit_id": "stm32f2-active-exact-gap-derivation-v3.8",
        "current_active_exact_count": len(f2_active),
        "current_production_f2_exact_count": len(current),
        "active_exact_gap_count": len(current_gap),
        "active_exact_set_sha256": digest(f2_active),
        "active_exact_gap_sha256": digest(current_gap),
        "active_series_counts": active_series,
        "gap_series_counts": gap_series,
        "tr_active_count": sum(x.endswith("TR") for x in f2_active),
        "tr_gap_count": sum(x.endswith("TR") for x in current_gap),
        "projected_if_all_72_later_approved": {
            "production_exact_total": 4314,
            "whole_st_active_intersection": 4235,
            "whole_st_active_gap": 315,
            "whole_st_active_coverage_percent": round(4235 / 4550 * 100, 4),
        },
        "production_write_authorized": False,
        "backend_or_profile_scope": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("===STM32F2_ACTIVE_EXACT_BEGIN===")
    print("\n".join(f2_active))
    print("===STM32F2_ACTIVE_EXACT_END===")
    print("===STM32F2_GAP_BEGIN===")
    print("\n".join(current_gap))
    print("===STM32F2_GAP_END===")
    print("STM32F2_ACTIVE_GAP_DERIVATION_V38_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

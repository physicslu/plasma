#!/usr/bin/env python3
"""Validate the STM32 missing-family Active exact-MPN evidence lock v1.2.

Offline mode validates checked-in identities, frozen Production boundaries and
source-lock metadata. With --capture-dir it additionally requires a fresh live
acquisition to reproduce the four newly locked exact sets byte-for-set.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LOCK = HERE / "st-missing-family-active-evidence-lock-v1.2.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
C5 = HERE / "st-c5-estore-172-active-exact-mpn-v0.7.txt"

FILES = {
    "STM32H5": HERE / "st-stm32h5-active-exact-mpn-v1.2.txt",
    "STM32N6": HERE / "st-stm32n6-active-exact-mpn-v1.2.txt",
    "STM32WB0": HERE / "st-stm32wb0-active-exact-mpn-v1.2.txt",
    "STM32WL3": HERE / "st-stm32wl3-active-exact-mpn-v1.2.txt",
}
EXPECTED = {
    "STM32C5": (172, "32d81e2491f1c8973a778cf62828a0c76662f4fb1813bc611d8b8959607b36a3"),
    "STM32H5": (190, "33b3d084b635a39f71e9d724aae3456bfb65c1e7e904b0b6547a849bd9dbee9b"),
    "STM32N6": (32, "f3ae0640f7e28c14b40b7b2ff83570e0bd95c7d0bd3bd98baac6edbcfc78bd50"),
    "STM32WB0": (24, "5f6adbd574ca751487c256a806764b1046cd5150cba757f73fd9d3269d167447"),
    "STM32WL3": (47, "4d7a67a26dbe6fe65ed492f0143116ae1898e183c9f57001f724a12af654b60d"),
}

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def exact_set(path: Path) -> list[str]:
    names = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    require(names == sorted(names), f"{path.name}: exact set must remain sorted")
    require(len(names) == len(set(names)), f"{path.name}: duplicate exact MPN")
    return names

def set_hash(names: list[str]) -> str:
    return hashlib.sha256(("\n".join(names) + "\n").encode()).hexdigest()

def validate(capture_dir: Path | None = None) -> dict:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["audit_id"] == "st-missing-family-active-evidence-lock-v1.2" and
            lock["record_state"] == "RESEARCH_ONLY_NOT_PRODUCTION_ADMISSION",
            "evidence-lock identity/scope drift")
    acquisition = lock["acquisition"]
    require(acquisition["workflow_run_id"] == 36795822483 and
            acquisition["workflow_job_id"] == 110158893612 and
            acquisition["acquisition_head_sha"] == "42efffba030ea375830469c44b617c4c2009e5b4" and
            acquisition["artifact_id"] == 11133966049 and
            acquisition["artifact_digest"] == "sha256:8da0686c05b2b2f10b10087a1efc68630d672de033bc5abdcec228b52669b8db" and
            acquisition["raw_manufacturer_bytes_retained_in_artifact"] is True,
            "live acquisition provenance drift")
    raw_manifest = PRODUCTION.read_bytes()
    production = json.loads(raw_manifest)
    sources = production["sources"]
    require(git_blob(raw_manifest) == "c8012b211a28b0a7811bfe978e7e697bc169c6f3" and
            len(sources) == 23 and sum(int(x["row_count"]) for x in sources) == 2683,
            "frozen Production ST baseline drift")
    prod_families = {x["family"] for x in sources}
    require(not (set(EXPECTED) & prod_families), "one missing family is already in Production")

    sets = {"STM32C5": exact_set(C5)}
    for family, path in FILES.items():
        sets[family] = exact_set(path)
    prefix = {
        "STM32C5": "STM32C5", "STM32H5": "STM32H5", "STM32N6": "STM32N6",
        "STM32WB0": "STM32WB0", "STM32WL3": "STM32WL",
    }
    for family, names in sets.items():
        expected_count, expected_hash = EXPECTED[family]
        require(len(names) == expected_count and set_hash(names) == expected_hash,
                f"{family}: exact identity count/hash drift")
        require(all(name.startswith(prefix[family]) for name in names),
                f"{family}: cross-family identity in locked set")
        row = lock["families"][family]
        require(row["exact_active_count"] == expected_count and
                row["exact_set_sha256"] == expected_hash and
                row["production_family_absent"] is True,
                f"{family}: evidence lock does not match exact set")

    union = set().union(*(set(v) for v in sets.values()))
    require(sum(map(len, sets.values())) == len(union) == 465,
            "missing-family exact sets overlap or count drifted")
    result = lock["result"]
    require(result == {
        "confirmed_missing_family_active_exact_count": 465,
        "confirmed_missing_family_active_exact_set_components_sum": 465,
        "confirmed_set_inventory_denominator": 3148,
        "confirmed_set_inventory_coverage_percent": 85.2287,
        "true_whole_st_active_coverage_percent": None,
        "existing_23_family_in_family_gap_audit_complete": False,
    }, "coverage boundary/result drift")
    claims = lock["claims"]
    require(claims["missing_five_family_exact_active_cohort_observed"] is True and
            claims["all_23_existing_production_families_reenumerated_current_active"] is False and
            claims["whole_st_active_exact_denominator_complete"] is False and
            claims["production_write_authorized"] is False and
            claims["backend_support_implied"] is False and
            claims["physical_validation_implied"] is False,
            "research-only coverage claims promoted")

    if capture_dir is not None:
        for family in ("STM32H5", "STM32N6", "STM32WB0", "STM32WL3"):
            path = capture_dir / family.lower() / "observed-active-exact.csv"
            require(path.is_file(), f"fresh acquisition missing {family} CSV")
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            fresh = sorted(row["exact_icpn"] for row in rows
                           if row.get("marketing_status") == "Active")
            require(fresh == sets[family],
                    f"fresh manufacturer acquisition changed locked {family} exact set")
        summary = json.loads((capture_dir / "capture-summary.json").read_text(encoding="utf-8"))
        require(summary["status"] == "OBSERVED_MISSING_FAMILY_ACTIVE_EXACT_COHORT_REQUIRES_REVIEW" and
                summary["confirmed_missing_family_active_exact_count"] == 465 and
                summary["confirmed_set_inventory_coverage_percent"] == 85.2287,
                "fresh acquisition summary differs from v1.2 evidence lock")

    return {
        "status": "ST_MISSING_FAMILY_ACTIVE_LOCK_V12_PASS",
        "production_exact_icpns": 2683,
        "missing_family_active_exact": 465,
        "confirmed_set_inventory_denominator": 3148,
        "confirmed_set_inventory_coverage_percent": 85.2287,
        "whole_st_active_coverage_percent": None,
        "production_write_authorized": False,
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture-dir", type=Path)
    args = ap.parse_args()
    print(json.dumps(validate(args.capture_dir), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

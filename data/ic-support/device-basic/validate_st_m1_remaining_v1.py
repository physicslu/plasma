#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
MANIFEST = REPO_ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
LEDGER = HERE / "st-m1-evidence-gaps-v1.json"
PROFILE_ROOT = HERE

BASELINE_FAMILIES = {"STM32C0", "STM32F1", "STM32F2", "STM32G0", "STM32G4"}


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    require(isinstance(value, dict), f"{path}: top level must be object")
    return value


def load_production_st() -> dict[str, set[str]]:
    manifest = load_json(MANIFEST)
    result: dict[str, set[str]] = {}
    for source in manifest["sources"]:
        if source["manufacturer"] != "STMicroelectronics":
            continue
        family = source["family"]
        path = (MANIFEST.parent / source["path"]).resolve()
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        icpns = {row["icpn"] for row in rows}
        require(len(icpns) == source["row_count"], f"{family}: source count drift")
        result[family] = icpns
    return result


def main() -> int:
    ledger = load_json(LEDGER)
    production = load_production_st()

    require(ledger["schema_version"] == "1.0.0", "ledger schema drift")
    require(ledger["status"] == "research_classification_complete", "ledger not complete")
    require(ledger["manufacturer"] == "STMicroelectronics", "manufacturer drift")

    boundary = ledger["authority_boundary"]
    for key in (
        "programming_profile_authority",
        "runtime_authority",
        "hardware_authority",
        "physical_programming_qualified",
    ):
        require(boundary[key] is False, f"{key} must remain false")
    require(
        set(boundary["allowed_surfaces"]) == {"st_product_selector", "st_estore"},
        "allowed source surface drift",
    )
    require(
        {"OpenOCD", "family_name_inference", "programming_guide", "datasheet"}
        <= set(boundary["prohibited_derivation_sources"]),
        "prohibited derivation boundary drift",
    )

    st_total = sum(len(v) for v in production.values())
    require(st_total == 4629, f"ST Production count drift: {st_total}")

    baseline = ledger["baseline"]
    require(baseline["production_exact_icpns"] == st_total, "baseline ST total drift")
    require(set(baseline["already_m1_families"]) == BASELINE_FAMILIES, "baseline family drift")
    baseline_count = sum(len(production[f]) for f in BASELINE_FAMILIES)
    require(baseline_count == baseline["m1_exact_icpns_before_program"] == 1290, "baseline M1 drift")

    remaining_families = set(production) - BASELINE_FAMILIES
    remaining_count = sum(len(production[f]) for f in remaining_families)
    require(
        remaining_count == baseline["remaining_exact_icpns_before_program"] == 3339,
        "remaining ST M1 scope drift",
    )

    admitted = ledger["admitted"]
    blocked = ledger["blocked"]
    admitted_families = set(admitted)
    blocked_families = set(blocked)

    require(not (admitted_families & blocked_families), "family classified twice")
    require(
        admitted_families | blocked_families == remaining_families,
        "remaining ST families are not classified exactly once",
    )

    admitted_count = 0
    for family, item in sorted(admitted.items()):
        require(item["count"] == len(production[family]), f"{family}: admitted count drift")
        profile_path = REPO_ROOT / item["profile"]
        require(profile_path.is_file(), f"{family}: admitted profile missing")
        profile = load_json(profile_path)
        require(profile["manufacturer"] == "STMicroelectronics", f"{family}: profile manufacturer drift")
        require(profile["family"] == family, f"{family}: profile family drift")
        require(profile["binding_count"] == len(production[family]), f"{family}: binding_count drift")
        require(set(profile["bindings"]) == production[family], f"{family}: exact binding set drift")
        require(
            isinstance(item.get("basis"), str) and item["basis"].strip(),
            f"{family}: admitted basis missing",
        )
        admitted_count += len(production[family])

    blocked_count = 0
    profile_by_family: dict[str, Path] = {}
    for path in sorted(PROFILE_ROOT.glob("*-device-basic-v1.json")):
        profile = load_json(path)
        family = profile["family"]
        require(family not in profile_by_family, f"{family}: duplicate profile")
        profile_by_family[family] = path

    for family, item in sorted(blocked.items()):
        require(item["count"] == len(production[family]), f"{family}: blocked count drift")
        require(family not in profile_by_family, f"{family}: blocked family has an admitted profile")
        for key in ("reason_code", "finding", "next_evidence_needed"):
            require(
                isinstance(item.get(key), str) and item[key].strip(),
                f"{family}: {key} missing",
            )
        urls = item.get("evidence_urls")
        require(
            isinstance(urls, list)
            and urls
            and all(
                isinstance(url, str)
                and (
                    url.startswith("https://www.st.com/")
                    or url.startswith("https://estore.st.com/")
                )
                for url in urls
            ),
            f"{family}: allowed-source evidence URL missing",
        )
        blocked_count += len(production[family])

    totals = ledger["totals"]
    require(admitted_count == totals["admitted_exact_icpns"] == 370, "admitted total drift")
    require(blocked_count == totals["blocked_exact_icpns"] == 2969, "blocked total drift")
    require(admitted_count + blocked_count == totals["classified_exact_icpns"] == 3339, "classified total drift")
    require(
        baseline_count + admitted_count == totals["m1_exact_icpns_after_admitted_profiles"] == 1660,
        "post-program M1 total drift",
    )
    require(
        totals["remaining_not_m1_exact_icpns"] == blocked_count,
        "remaining non-M1 total drift",
    )

    expected_profile_families = BASELINE_FAMILIES | admitted_families
    require(
        set(profile_by_family) == expected_profile_families,
        "Manufacturer Device Basic profile family set drift",
    )

    print(
        "ST remaining M1 classification PASS: "
        f"{admitted_count} admitted + {blocked_count} blocked = {remaining_count}; "
        f"M1 total {baseline_count + admitted_count}/{st_total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

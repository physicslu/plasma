#!/usr/bin/env python3
"""Replay ST's TWO official structural product sources against Plasma's frozen ST catalog.

MX1 open_pin_data is a subset of CubeMX and includes MCU/XML patterns plus
STM32MP/MPU; newer MX2-only C5 uses its separate DFP JSON descriptor repository.
Neither structural source proves exact commercial identity or lifecycle status.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import audit_st_portfolio_coverage_gap as st_v02

HERE = Path(__file__).resolve().parent
MX1_PATH = HERE / "sources/st-open-pin-mcu-tree-7d1f1514.tsv"
C5_PATH = HERE / "sources/st-c5-dfp-pinout-tree-a5f65bc6.tsv"
REPORT = HERE / "st-multisource-structural-coverage-v0.4.json"
MX1_SHA = "d8715ae7453883f62377e87b529f94012323f062"
MX2_C5_SHA = "7068a7c4fb580c3f1e7f7d523d13693e54034fbd"
MX1_COMMIT = "7d1f1514ed5583ec5007ad91236b4e1d377295b1"
MX2_C5_COMMIT = "a5f65bc64535cfa723e9d25f58d7ce23d0937aed"
ST_OFFER_COMMIT = "3ba0d378f9da6cb480d0293f0ce2fcb53c2f1a21"
ST_OFFER_README_BLOB = "6600232eee622f1f8a493b82da6c506468f08929"
MX1_README_BLOB = "9cb536b93ccb3c821ef0861d1710040a04f3b03b"
ST_MANIFEST_BLOB = "c8012b211a28b0a7811bfe978e7e697bc169c6f3"

ST_NATIVE_SERIES = (
    "C0", "C5", "F0", "F1", "F2", "F3", "F4", "F7",
    "G0", "G4", "H5", "H7", "H7RS", "L0", "L1", "L4",
    "L5", "N6", "U0", "U3", "U5", "WB", "WB0", "WBA", "WL", "WL3",
)
UNREPRESENTED = ("STM32C5", "STM32H5", "STM32N6", "STM32WB0", "STM32WL3")
EXPECTED_MX1_GAP_COUNTS = {
    "STM32C5": 0, "STM32H5": 151, "STM32N6": 28,
    "STM32WB0": 10, "STM32WL3": 22,
}
EXPECTED_GROUPS = {
    "STM32C0": 84, "STM32C5": 0, "STM32F0": 89, "STM32F1": 58,
    "STM32F2": 16, "STM32F3": 53, "STM32F4": 116, "STM32F7": 92,
    "STM32G0": 98, "STM32G4": 118, "STM32H5": 151, "STM32H7": 141,
    "STM32H7RS": 34, "STM32L0": 113, "STM32L1": 90,
    "STM32L4": 193, "STM32L5": 32, "STM32N6": 28, "STM32U0": 48,
    "STM32U3": 171, "STM32U5": 162, "STM32WB": 22,
    "STM32WB0": 10, "STM32WBA": 39, "STM32WL": 28, "STM32WL3": 22,
}
EXPECTED_EXACT_SAMPLES = {
    "STM32H5": "STM32H503CBTx.xml",
    "STM32N6": "STM32N657A0HxQ.xml",
    "STM32WB0": "STM32WB05KZVx.xml",
    "STM32WL3": "STM32WL33CCVx.xml",
    "STM32C5_MX2": "STM32C531C(B-C)Tx_pinout.json",
}

def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)

def read_git_tree_snapshot(path: Path, pinned_tree_sha: str) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    require(len(lines) > 3, f"{path}: missing provenance and tree records")
    require(lines[0] == f"# official_git_tree_sha={pinned_tree_sha}",
            f"{path}: upstream tree provenance mismatch")
    require(lines[1].startswith("# origin=https://api.github.com/repos/STMicroelectronics/"),
            f"{path}: non-official source provenance")
    require(lines[2] == "mode\tsha\tname", f"{path}: incompatible source schema")
    rows: list[dict[str, str]] = []
    names: set[str] = set()
    raw_git_tree = bytearray()
    for line in lines[3:]:
        parts = line.split("\t")
        require(len(parts) == 3, f"{path}: invalid entry")
        mode, sha, name = parts
        require(mode in ("040000", "100644", "100755", "120000"), f"{path}: invalid mode")
        require(len(sha) == 40 and all(c in "0123456789abcdef" for c in sha),
                f"{path}: invalid Git object ID")
        require("\x00" not in name and "/" not in name and name not in (".", "..", "") and
                name not in names, f"{path}: invalid or duplicated tree name")
        names.add(name)
        canonical_mode = mode.lstrip("0")
        raw_git_tree.extend(f"{canonical_mode} {name}".encode("utf-8"))
        raw_git_tree.extend(b"\0")
        raw_git_tree.extend(bytes.fromhex(sha))
        rows.append({"mode": mode, "sha": sha, "name": name})
    actual_sha = hashlib.sha1(
        f"tree {len(raw_git_tree)}\0".encode("ascii") + bytes(raw_git_tree),
        usedforsecurity=False,
    ).hexdigest()
    require(actual_sha == pinned_tree_sha,
            f"{path}: Git tree digest mismatch {actual_sha} != {pinned_tree_sha}")
    return rows

def classify_mx1(name: str) -> str:
    if name.startswith("STM32MP"):
        return "STM32MP_EXCLUDED"
    if name.startswith("STM32H7R") or name.startswith("STM32H7S"):
        return "STM32H7RS"
    for short in ("WB0", "WBA", "WL3", "C0", "C5", "F0", "F1", "F2",
                  "F3", "F4", "F7", "G0", "G4", "H5", "H7", "L0",
                  "L1", "L4", "L5", "N6", "U0", "U3", "U5", "WB", "WL"):
        if name.startswith("STM32" + short):
            return "STM32" + short
    raise ValueError(f"unknown STM32 structural family: {name}")

def render() -> dict:
    production = st_v02.render()
    require(production["production_baseline"]["original_manifest_git_blob_sha"] == ST_MANIFEST_BLOB,
            "Production baseline revision drifted")
    require(production["production_baseline"]["integrity_bound_source_count"] == 23 and
            production["production_baseline"]["unique_exact_icpns"] == 2683,
            "Production ST source scope drifted")
    mx1 = read_git_tree_snapshot(MX1_PATH, MX1_SHA)
    require(len(mx1) == 2241 and mx1[0]["name"] == "IP" and mx1[0]["mode"] == "040000",
            "MX1 tree root entry count / IP subdirectory drifted")
    xml = [r["name"] for r in mx1 if r["mode"] == "100644" and r["name"].endswith(".xml")]
    require(len(xml) == 2240 and len(mx1) == len(xml) + 1, "unexpected official MX1 file classification")
    groups = Counter(classify_mx1(s) for s in xml)
    require(groups.pop("STM32MP_EXCLUDED", 0) == 232, "STM32MP/MPU exclusion count drifted")
    require(sum(groups.values()) == 2008, "MX1 MCU-only XML pattern population drifted")
    for series in ST_NATIVE_SERIES:
        groups.setdefault("STM32" + series, 0)
    require(dict(groups) == EXPECTED_GROUPS, "Official structural pattern group counts drifted")
    require(set(groups) == {"STM32" + s for s in ST_NATIVE_SERIES}, "native family mapping incomplete")

    c5 = read_git_tree_snapshot(C5_PATH, MX2_C5_SHA)
    require(len(c5) == 46 and all(
        r["mode"] == "100644" and r["name"].startswith("STM32C5") and
        r["name"].endswith("_pinout.json") for r in c5
    ), "MX2 C5 DFP descriptor inventory drifted")
    c5names = {x["name"] for x in c5}
    names = set(xml)
    for series, sample in EXPECTED_EXACT_SAMPLES.items():
        require(sample in (c5names if series == "STM32C5_MX2" else names),
                f"Missing official {series} structural sample {sample}")

    published = production["production_baseline"]["family_counts"]
    require(all(not any(
        family == missing for family in published
    ) for missing in UNREPRESENTED), "One of the five sentinel families is now published; redo comparison")
    require(len(published) == 23, "Production family count drifted")
    return {
        "schema_version": 1,
        "audit_id": "st-stm32-dual-source-structural-audit-v0.4",
        "reference_date": "2026-09-29",
        "type": "manufacturer_pinned_structure_and_source_split_not_exact_commercial_coverage",
        "mx1_subset": {
            "repository": "STMicroelectronics/STM32_open_pin_data",
            "commit": MX1_COMMIT,
            "mcu_tree_sha": MX1_SHA,
            "upstream_readme_git_blob_sha": MX1_README_BLOB,
            "source_path": "sources/st-open-pin-mcu-tree-7d1f1514.tsv",
            "all_xml_records": len(xml),
            "excluded_stm32mp_mpu_xml": 232,
            "stm32_mcu_xml_pattern_count": sum(groups.values()),
            "family_xml_pattern_counts": dict(sorted(groups.items())),
            "subset_of_cube_mx_database": True,
            "exact_orderable_mpn_source": False,
            "manufacturer_marketing_lifecycle_authority": False,
        },
        "mx2_c5_dfp": {
            "repository": "STMicroelectronics/stm32c5xx-dfp",
            "commit": MX2_C5_COMMIT,
            "pinout_tree_sha": MX2_C5_SHA,
            "source_path": "sources/st-c5-dfp-pinout-tree-a5f65bc6.tsv",
            "c5_pinout_json_pattern_count": len(c5),
            "separate_mx2_only_format": True,
            "exact_orderable_mpn_source": False,
            "manufacturer_marketing_lifecycle_authority": False,
        },
        "official_portfolio_source": {
            "repository": "STMicroelectronics/STM32Cube_MCU_Overall_Offer",
            "commit": ST_OFFER_COMMIT,
            "readme_git_blob_sha": ST_OFFER_README_BLOB,
            "explicit_c5_family_in_hal2_list": True,
            "coverage_denominator_from_software_offer": False,
        },
        "production_st": {
            "original_manifest_git_blob_sha": ST_MANIFEST_BLOB,
            "exact_icpns": 2683,
            "catalog_families": 23,
        },
        "missing_five_family_structural_evidence": [
            {
                "family": series,
                "mx1_xml_pattern_count": EXPECTED_MX1_GAP_COUNTS[series],
                "mx2_c5_pinout_json_pattern_count": 46 if series == "STM32C5" else 0,
                "published_exact_icpn_count": 0,
                "commercial_active_sentinel_from_v02": True,
                "qualifier": "pattern_count_is_not_exact_mpn_count_or_active_count",
            }
            for series in UNREPRESENTED
        ],
        "key_conclusions": {
            "xml_tree_includes_excluded_mpu": True,
            "mx1_xml_alone_cannot_cover_mx2_only_c5": True,
            "mx1_and_mx2_snapshots_are_different_versioned_sources": True,
            "official_product_selector_commercial_lifecycle_enumeration_still_required": True,
            "missing_active_exact_icpn_total": None,
            "actual_active_exact_coverage_percent": None,
            "production_write_authorized": False,
            "backend_programming_authorized": False,
            "physical_qualification_claimed": False,
        },
        "next_gate": "obtain dated ST official exact commercial MPN + same-row marketing status from both MX1 and MX2 product families; use structural source only for scope reconciliation",
    }

def main() -> int:
    expected = render()
    retained = json.loads(REPORT.read_text(encoding="utf-8"))
    require(retained == expected, "Frozen v0.4 report differs from deterministic dual-source replay")
    print("ST multi-source structural audit v0.4: PASS")
    print("MX1: 2240 XML = 2008 STM32 MCU patterns + 232 STM32MP MPU patterns")
    print("MX2-only C5: 46 DFP pinout JSON patterns, no MX1 C5 entries")
    print("Five Production-missing families: C5 H5 N6 WB0 WL3")
    print("Production ST: 2683 exact ICPNs / 23 families; actual Active coverage=UNKNOWN")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

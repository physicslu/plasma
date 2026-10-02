#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXACT_PATH = HERE / "st-stm32h5-active-exact-mpn-v1.2.txt"
TREE_PATH = HERE / "sources" / "st-open-pin-mcu-tree-7d1f1514.tsv"
TARGET_CATALOG_PATH = HERE / "plasma_openocd_target_catalog.csv"

EXPECTED_EXACT = 190
EXPECTED_PATTERNS = 151
EXPECTED_TR = 51
EXPECTED_PREFIX_COUNTS = {
    "STM32H50": 14,
    "STM32H52": 39,
    "STM32H53": 14,
    "STM32H54": 4,
    "STM32H55": 2,
    "STM32H56": 59,
    "STM32H57": 23,
    "STM32H5E": 22,
    "STM32H5F": 13,
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def normalize_exact(icpn: str) -> str:
    return icpn[:-2] if icpn.endswith("TR") else icpn


def pattern_regex(pattern: str) -> re.Pattern[str]:
    return re.compile("^" + re.escape(pattern).replace("x", ".") + "$")


def matches_for(icpn: str, patterns: list[str]) -> list[str]:
    normalized = normalize_exact(icpn)
    return [pattern for pattern in patterns if pattern_regex(pattern).fullmatch(normalized)]


def load_exact() -> list[str]:
    rows = [x.strip() for x in EXACT_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(rows) == EXPECTED_EXACT, "STM32H5 exact ledger row count drift")
    req(len(set(rows)) == EXPECTED_EXACT, "STM32H5 exact ledger contains duplicates")
    req(all(x.startswith("STM32H5") for x in rows), "non-H5 identity in H5 exact ledger")
    return rows


def load_h5_patterns() -> list[str]:
    patterns = []
    for line in TREE_PATH.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        name = cols[2]
        if name.startswith("STM32H5") and name.endswith(".xml"):
            patterns.append(name[:-4])
    req(len(patterns) == EXPECTED_PATTERNS, "STM32H5 MX1 pattern count drift")
    req(len(set(patterns)) == EXPECTED_PATTERNS, "duplicate STM32H5 MX1 patterns")
    return sorted(patterns)


def current_h5_backend_entries() -> list[dict[str, str]]:
    with TARGET_CATALOG_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        row
        for row in rows
        if "STM32H5" in " ".join(str(v or "") for v in row.values())
        or "stm32h5" in " ".join(str(v or "") for v in row.values()).lower()
    ]


def analyze() -> dict:
    exact = load_exact()
    patterns = load_h5_patterns()

    unmatched = []
    ambiguous = []
    crosswalk = {}
    for icpn in exact:
        matches = matches_for(icpn, patterns)
        if len(matches) == 0:
            unmatched.append(icpn)
        elif len(matches) > 1:
            ambiguous.append({"icpn": icpn, "matches": matches})
        else:
            crosswalk[icpn] = matches[0]

    matched_patterns = sorted(set(crosswalk.values()))
    prefix_counts = dict(sorted(Counter(x[:8] for x in exact).items()))
    tr_count = sum(x.endswith("TR") for x in exact)
    backend_entries = current_h5_backend_entries()

    req(not unmatched, f"unmatched STM32H5 exact identities: {unmatched[:5]}")
    req(not ambiguous, f"ambiguous STM32H5 exact identities: {ambiguous[:5]}")
    req(len(crosswalk) == EXPECTED_EXACT, "H5 exact-to-MX1 crosswalk incomplete")
    req(len(matched_patterns) == EXPECTED_MATCHED_PATTERNS, "H5 Active-exercised MX1 pattern count drift")
    req(len(unexercised_patterns) == EXPECTED_UNEXERCISED_PATTERNS, "H5 current-Active-unexercised MX1 pattern count drift")
    req(prefix_counts == EXPECTED_PREFIX_COUNTS, "H5 exact prefix distribution drift")
    req(tr_count == EXPECTED_TR, "H5 TR count drift")
    req(not backend_entries, "current Plasma OpenOCD target catalog unexpectedly contains STM32H5")

    return {
        "audit_id": "stm32h5-layered-gap-v2.6",
        "layer1": {
            "official_active_exact_mpn_count": len(exact),
            "exact_identity_source": EXACT_PATH.name,
            "mx1_structural_pattern_count": len(patterns),
            "matched_exact_count": len(crosswalk),
            "matched_pattern_count": len(matched_patterns),
            "unmatched_exact_count": len(unmatched),
            "ambiguous_exact_count": len(ambiguous),
            "tr_exact_count": tr_count,
            "non_tr_exact_count": len(exact) - tr_count,
            "prefix_counts": prefix_counts,
            "identity_candidate_state": "manufacturer_active_exact_locked",
            "structural_crosswalk_state": "deterministic_unique",
        },
        "layer2": {
            "current_plasma_target_catalog_h5_entry_count": len(backend_entries),
            "mapping_candidate_exact_count": 0,
            "no_mapping_exact_count": len(exact),
            "mapping_status": "no_mapping",
            "reason": "No STM32H5 entry is present in the current Plasma OpenOCD target catalog; no route is synthesized.",
        },
        "claims": {
            "metadata_authority_replay_complete": False,
            "catalog_admission_ready": False,
            "programming_profile_applicability_expanded": False,
            "engineering_verified": False,
            "operational_field_evidence": False,
            "production_write_authorized": False,
        },
        "next_gate": (
            "Bind official ST Ordering Information authority for the H503/H52/H53/H54/H55/H56/H57/H5E/H5F "
            "surfaces and replay all 190 exact identities for metadata. Preserve Layer-2 no_mapping unless a "
            "separately pinned Plasma backend route is qualified."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

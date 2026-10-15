#!/usr/bin/env python3
"""Bounded NXP v0.12.0 OpenOCD-first Wave 4 research, NEVER programming admission.

Deterministic offline audit of pre-reviewed *observations* from three official
NXP web pages against exact upstream OpenOCD Tcl/Driver Git blobs and the
previously approved frozen NXP research inventory. Not a manufacturer HTML
original-byte replay, flash operation qualification, or NXP-wide enumeration.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEDGER = HERE / "nxp-openocd-source-first-wave4-v1.json"
ORIGINAL = HERE / "nxp-501-adr0002-core-transport-qualification-v10.csv"
WAVE2 = HERE / "nxp-openocd-exact-active-discovery-v2.json"
WAVE3 = HERE / "nxp-openocd-source-first-wave3-v1.json"
UPSTREAM_LOCK = HERE / "nxp-openocd-reverse-target-lock-v1.json"
RELEASE = ROOT / "release/openocd.json"
COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"

P81 = "https://www.nxp.com/products/LPC81X_LPC83X?tab=Package_Quality_Tab"
PU = "https://www.nxp.com/products/LPC11U00?tab=Package_Quality_Tab"
P1769 = "https://www.nxp.com/products/LPC1769FBD100"
IDENTITIES = {
    "LPC811": ["LPC811M001JDH16FP", "LPC811M001JDH16J"],
    "LPC812": ["LPC812M101JD20J", "LPC812M101JDH16FP",
               "LPC812M101JDH16J", "LPC812M101JDH20FP",
               "LPC812M101JDH20J", "LPC812M101JTB16X"],
    "LPC11U24": ["LPC11U24FHI33/301Y"],
    "LPC11U67": ["LPC11U67JBD100E", "LPC11U67JBD48E", "LPC11U67JBD64E"],
    "LPC11U68": ["LPC11U68JBD48E", "LPC11U68JBD48K", "LPC11U68JBD64E",
                 "LPC11U68JBD64K", "LPC11U68JBD64Y"],
    "LPC1769": ["LPC1769FBD100"],
    "LPC832": ["LPC832M101FDH20FP"],
    "LPC834": ["LPC834M101FHI33Y"],
}
DRIVER_IDS = {
    "LPC811": ["LPC811_001"],
    "LPC812": ["LPC812_101", "LPC812_101_1",
               "LPC812_101_2", "LPC812_101_3"],
    "LPC11U24": ["LPC11U24_301", "LPC11U24_401"],
    "LPC11U67": ["LPC11U67_1", "LPC11U67_2"],
    "LPC11U68": ["LPC11U68_1", "LPC11U68_2"],
    "LPC1769": ["LPC1769"],
    "LPC832": [],
    "LPC834": [],
}
PINNED_BLOBS = {
    "tcl/target/lpc8xx.cfg": "4c54a2a6670d6186297306112deee8d25e2627e4",
    "tcl/target/lpc11xx.cfg": "d288e2a32b08b5e9ad26b7c86fb7035e8e08b1b6",
    "tcl/target/lpc17xx.cfg": "35d8badea416e641babe6ccad3fd8503f3de7cae",
    "tcl/target/lpc1xxx.cfg": "70d26d2673900b06c6d5eef8e55b4542103e9e42",
    "src/flash/nor/lpc2000.c": "f12eef7e4ce68fc8830773f6c57da57dfb87d6b8",
}
FAMILY_URL = {
    **dict.fromkeys(("LPC811", "LPC812", "LPC832", "LPC834"), P81),
    **dict.fromkeys(("LPC11U24", "LPC11U67", "LPC11U68"), PU),
    "LPC1769": P1769,
}
FAMILY_TARGET = {
    **dict.fromkeys(("LPC811", "LPC812", "LPC832", "LPC834"), "tcl/target/lpc8xx.cfg"),
    **dict.fromkeys(("LPC11U24", "LPC11U67", "LPC11U68"), "tcl/target/lpc11xx.cfg"),
    "LPC1769": "tcl/target/lpc17xx.cfg",
}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("NXP OpenOCD wave4: " + reason)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(doc: dict | None = None, *, upstream: dict | None = None,
             baseline: set[str] | None = None,
             wave2: dict | None = None, wave3: dict | None = None) -> dict:
    doc = doc if doc is not None else load(LEDGER)
    upstream = upstream if upstream is not None else load(UPSTREAM_LOCK)
    wave2 = wave2 if wave2 is not None else load(WAVE2)
    wave3 = wave3 if wave3 is not None else load(WAVE3)
    release = load(RELEASE)

    require(doc.get("schema_version") == 1 and
            doc.get("kind") == "NXP_OPENOCD_CONFIG_REVERSE_DISCOVERY_WAVE4_SOURCE_ONLY" and
            doc.get("provider") == "openocd-org/openocd" and
            doc.get("openocd_version") == release.get("version") == "0.12.0" and
            doc.get("source_commit") == release.get("source_commit") ==
            upstream.get("source_commit") == COMMIT, "provider/source revision mismatch")
    require(doc.get("official_page_original_html_byte_custody") is False and
            doc.get("nxp_global_active_denominator") is None and
            doc.get("research_cohorts_existing") == [501, 27, 18] and
            doc.get("manufacturer_official_pages") == [P81, PU, P1769],
            "scope or manufacturer HTML source custody incorrectly expanded")

    names = {item["path"]: item["git_blob"] for item in upstream["target_files"]}
    names.update(upstream["verified_baseline_driver_blobs"])
    require(doc.get("openocd_source_git_blobs") == PINNED_BLOBS and
            all(names.get(k) == v for k, v in PINNED_BLOBS.items()),
            "upstream original Git blob SHA mismatch")

    if baseline is None:
        with ORIGINAL.open(encoding="utf-8", newline="") as f:
            original_rows = list(csv.DictReader(f))
        baseline = {row["icpn"] for row in original_rows}
        require(len(original_rows) == len(baseline) == 501,
                "historical 501 denominator changed")
    require(len(baseline) == 501 and len(wave2["records"]) == 27 and
            len(wave3["records"]) == 18 and
            wave2["source_commit"] == wave3["source_commit"] == COMMIT,
            "historical cohorts or provider changed")
    historical = set(baseline) | {r["icpn"] for r in wave2["records"]} | {
        r["icpn"] for r in wave3["records"]
    }
    require(len(historical) == 501+27+18, "existing cohort duplicate or identity drift")

    expected = {sku for family in IDENTITIES.values() for sku in family}
    rows = doc.get("records")
    require(isinstance(rows, list) and len(rows) == len(expected) == 20,
            "unapproved discovery candidate count")
    observed = [r["icpn"] for r in rows]
    require(observed == sorted(expected) and len(set(observed)) == 20,
            "candidate set changed, duplicated or unsorted")
    require(not expected.intersection(historical),
            "prior 501/27/18 exact ICPNs duplicated by new candidates")
    counts = Counter()
    for row in rows:
        family = row["family"]
        sku = row["icpn"]
        require(family in IDENTITIES and sku in IDENTITIES[family],
                "exact material code to family mismatch")
        ids = DRIVER_IDS[family]
        require((row["openocd_target"], row["openocd_helper"],
                 row["openocd_flash_driver"], row["openocd_driver_part_id_cases"]) ==
                (FAMILY_TARGET[family], "tcl/target/lpc1xxx.cfg",
                 "src/flash/nor/lpc2000.c", ids),
                "OpenOCD Target/Helper/Driver Part-ID evidence changed")
        p = urlparse(row["manufacturer_url"])
        require(row["manufacturer_url"] == FAMILY_URL[family] and
                p.scheme == "https" and p.netloc == "www.nxp.com",
                "official NXP source URL mismatch")
        require(row["manufacturer_evidence_scope"] ==
                ("PRODUCT_ACTIVE_MATERIAL_LIFECYCLE_UNVERIFIED"
                 if family == "LPC1769" else "MATERIAL_ACTIVE") and
                row["manufacturer_observed_lifecycle"] == "Active" and
                row["manufacturer_original_bytes_archived"] is False and
                row["exact_material_to_silicon_part_id_verified"] is False and
                row["flash_programming_qualified"] is False and
                row["production_admitted"] is False and
                row["physical_hil_verified"] is False,
                "manufacturer evidence or qualification improperly promoted")
        priority = ("P0_DISCOVERY_CANDIDATE_ONLY" if ids else
                    "P1_GENERIC_TARGET_EXPLICIT_ID_MISSING")
        require(row["priority"] == priority, "P1/P0 priority changed without Part ID evidence")
        counts[priority] += 1

    excluded = doc.get("excluded")
    require(excluded == [{
        "icpn": "LPC810M021FN8FP", "family": "LPC810",
        "manufacturer_url": P81,
        "manufacturer_observed_lifecycle": "No Longer Manufactured",
        "openocd_driver_part_id_cases": ["LPC810_021"],
        "priority": "EXCLUDED_FROM_ACTIVE_SOURCE_FIRST_DISCOVERY",
        "manufacturer_original_bytes_archived": False,
    }], "No Longer Manufactured NXP exclusion falsified or lost")
    require(counts == {"P0_DISCOVERY_CANDIDATE_ONLY": 18,
                       "P1_GENERIC_TARGET_EXPLICIT_ID_MISSING": 2},
            "discovery priority counts changed")
    return {
        "existing_cohorts": [501, 27, 18],
        "new_exact_observation_strings": len(rows),
        "p0_source_backed_discovery": counts["P0_DISCOVERY_CANDIDATE_ONLY"],
        "p1_bounded_driver_id_gap": counts["P1_GENERIC_TARGET_EXPLICIT_ID_MISSING"],
        "excluded_no_longer_manufactured": len(excluded),
        "manufacturer_official_pages": 3,
        "pinned_openocd_source_blobs": len(PINNED_BLOBS),
        "new_software_supported": 0,
        "new_production_admission": 0,
        "original_manufacturer_source_bytes_captured": False,
        "entire_nxp_vendor_complete": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
    print("NXP OPENOCD WAVE4 PASS: candidate-only, no programming claim")

#!/usr/bin/env python3
"""ADR-0002: bounded OpenOCD-first NXP discovery validation (NO software promotion).

This script is a deterministic, offline replay of *reviewed website observations*
plus pinned upstream source Git blobs. It does not replay original HTML bytes:
the evidence manifest explicitly records that gap. It must not be interpreted as
an official NXP Active portfolio audit or flash operations qualification.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CANDIDATES = HERE / "nxp-openocd-exact-active-discovery-v2.json"
PREVIOUS = HERE / "nxp-openocd-reverse-target-lock-v1.json"
BASELINE = HERE / "nxp-501-adr0002-core-transport-qualification-v10.csv"
RELEASE = ROOT / "release/openocd.json"
COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
EXPECTED = {"K40": 4, "K60": 5, "KL46": 7,
            "LPC1114": 1, "LPC1758": 2, "LPC1768": 2,
            "LPC4088": 2, "LPC4357": 4}
TARGETS = {
    "K40": ("tcl/target/k40.cfg", "tcl/target/kx.cfg", "src/flash/nor/kinetis.c"),
    "K60": ("tcl/target/k60.cfg", "tcl/target/kx.cfg", "src/flash/nor/kinetis.c"),
    "KL46": ("tcl/target/kl46.cfg", "tcl/target/klx.cfg", "src/flash/nor/kinetis.c"),
    "LPC1114": ("tcl/target/lpc11xx.cfg", "tcl/target/lpc1xxx.cfg", "src/flash/nor/lpc2000.c"),
    "LPC1758": ("tcl/target/lpc17xx.cfg", "tcl/target/lpc1xxx.cfg", "src/flash/nor/lpc2000.c"),
    "LPC1768": ("tcl/target/lpc17xx.cfg", "tcl/target/lpc1xxx.cfg", "src/flash/nor/lpc2000.c"),
    "LPC4088": ("tcl/target/lpc40xx.cfg", "tcl/target/lpc1xxx.cfg", "src/flash/nor/lpc2000.c"),
    "LPC4357": ("tcl/target/lpc4357.cfg", "tcl/target/lpc4350.cfg", "src/flash/nor/lpc2000.c"),
}
EXPECTED_PAGES = {
    "K40": "https://www.nxp.com/products/K40_100?tab=Package_Quality_Tab",
    "K60": "https://www.nxp.com/products/K60_100?tab=Package_Quality_Tab",
    "KL46": "https://www.nxp.com/products/KL4x?tab=Package_Quality_Tab",
    "LPC1114": "https://www.nxp.com/products/LPC1100?tab=Package_Quality_Tab",
    "LPC1758": "https://www.nxp.com/products/LPC1758FBD80?tab=Package_Quality_Tab",
    "LPC1768": "https://www.nxp.com/products/LPC1768FBD100?tab=Package_Quality_Tab",
    "LPC4088": "https://www.nxp.com/products/LPC4088FBD208?tab=Package_Quality_Tab",
}
LPC4357_PAGES = {
    "https://www.nxp.com/products/LPC4357FET256?tab=Package_Quality_Tab",
    "https://www.nxp.com/products/LPC4357JBD208?tab=Package_Quality_Tab",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("NXP OpenOCD reverse discovery: " + message)


def read_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(obj, dict), f"invalid JSON object: {path}")
    return obj


def validate(*, original: dict | None = None, previous: dict | None = None,
             baseline_rows: list[dict] | None = None) -> dict:
    doc = original if original is not None else read_json(CANDIDATES)
    prior = previous if previous is not None else read_json(PREVIOUS)
    release = read_json(RELEASE)
    require(doc.get("schema_version") == 1 and
            doc.get("scope") == "READ_ONLY_NXP_SOURCE_FIRST_NEW_EXACT_ACTIVE_OBSERVATIONS_NOT_ADR_SUPPORTED" and
            doc.get("phase") == "SOURCE_FIRST_RESEARCH_NOT_PROGRAMMING" and
            doc.get("permitted_change") == "research-only",
            "unapproved research scope or schema")
    require(release.get("version") == "0.12.0" and
            release.get("source_commit") == COMMIT and
            doc.get("pinned_openocd_version") == "0.12.0" and
            doc.get("source_commit") == prior.get("source_commit") == COMMIT and
            doc.get("upstream") == "openocd-org/openocd",
            "runtime source version / provider mismatch")
    require(doc.get("manufacturer_coverage") ==
            "BOUNDED_9_OFFICIAL_PACKAGE_QUALITY_PAGES_NO_ALL_VENDOR_DENOMINATOR"
            and doc.get("manufacturer_page_bytes_archived") is False,
            "cannot claim whole-vendor or archived original manufacturer evidence")

    locked = {x["path"]: x["git_blob"] for x in prior["target_files"]}
    locked.update(prior["verified_baseline_driver_blobs"])
    require(doc.get("source_entries_sha1_git_blob") == {
        k: locked[k] for k in doc.get("source_entries_sha1_git_blob", {})
    }, "source Git blob is not the independently locked OpenOCD commit")
    need_sources = {src for group in TARGETS.values() for src in group}
    require(set(doc["source_entries_sha1_git_blob"]) == need_sources,
            "the complete approved Target -> Helper -> Flash Driver graph must be locked")

    if baseline_rows is None:
        with BASELINE.open(encoding="utf-8", newline="") as stream:
            baseline_rows = list(csv.DictReader(stream))
    baseline_ids = [r["icpn"] for r in baseline_rows]
    require(len(baseline_ids) == len(set(baseline_ids)) == 501 and
            all(r["manufacturer"] == "NXP" for r in baseline_rows),
            "prior 501-row review baseline changed")

    rows = doc.get("records")
    require(isinstance(rows, list) and len(rows) == 27,
            "candidate list count changed; requires new review")
    identifiers = [x["icpn"] for x in rows]
    require(identifiers == sorted(set(identifiers)), "candidate exact identifiers must be unique, sorted")
    require(not set(identifiers) & set(baseline_ids), "candidate overlaps the original NXP 501")
    require(doc.get("baseline_reviewed_icpns") == len(baseline_ids),
            "baseline population claim drifted")

    counts = Counter()
    observed_urls = set()
    for row in rows:
        sku, family = row["icpn"], row["family"]
        require(family in EXPECTED and sku.startswith(family if family.startswith("LPC") else "MK" + family[1:] if family.startswith("K") else family),
                "invalid SKU/family pairing: " + sku)
        target, helper, driver = TARGETS[family]
        require((row["openocd_target"], row["openocd_helper"], row["openocd_flash_driver"]) ==
                (target, helper, driver), "source route drift: " + sku)
        url = row["manufacturer_url"]
        p = urlparse(url)
        require(p.scheme == "https" and p.netloc == "www.nxp.com" and
                (url == EXPECTED_PAGES.get(family) if family != "LPC4357"
                 else url in LPC4357_PAGES), "unreviewed official page: " + sku)
        if family == "LPC4357":
            require(sku.startswith("LPC4357FET256") if "FET256" in url
                    else sku.startswith("LPC4357JBD208"), "LPC4357 product-page ambiguity")
        require(row["manufacturer_active_status"] == "Active" and
                row["manufacturer_observation"] ==
                "NXP_OFFICIAL_PACKAGE_QUALITY_VISIBLE_NOT_RAW_BYTE_ARCHIVED" and
                row["priority_proposal"] ==
                "P0_SOURCE_BACKED_DISCOVERY_CANDIDATE_NOT_QUALIFIED" and
                row["exact_to_silicon_id"] == "UNVERIFIED" and
                row["flash_geometry_and_operations"] == "UNVERIFIED" and
                row["manufacturer_orderable_identity"] ==
                "RAW_OFFICIAL_DISPLAY_CODE_REQUIRES_FINAL_ORDERING_NORMALIZATION" and
                row["production_admission"] is False and
                row["openocd_software_supported"] is False,
                "source-only evidence was silently promoted: " + sku)
        counts[family] += 1
        observed_urls.add(url)
    require(dict(counts) == EXPECTED, "family candidate counts differ from approved list")
    require(len(observed_urls) == 9, "official source page observations changed")
    return {
        "reviewed_original": len(baseline_ids),
        "new_discovery_candidates": len(rows),
        "new_software_qualified": 0,
        "new_production_admissions": 0,
        "groups": dict(sorted(counts.items())),
        "pages": len(observed_urls),
        "openocd_source_paths": len(need_sources),
        "official_original_html_sha256_pinned": False,
        "nxp_global_portfolio_coverage": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    report = validate()
    print(json.dumps(report, indent=2, sort_keys=True))
    print("NXP SOURCE-FIRST DISCOVERY PASS (candidate-only, no software admission)")


if __name__ == "__main__":
    main()

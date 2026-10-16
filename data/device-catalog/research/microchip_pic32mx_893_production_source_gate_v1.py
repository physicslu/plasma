#!/usr/bin/env python3
"""Fail-closed Microchip PIC32MX 893 Product source admission verification.

The only identity authority is the frozen original manufacturer MCP replay
2441-row index (not OpenOCD). The only programming-route relevance authority
is the pinned exact Flash Driver DEVID table from OpenOCD v0.12.0. Every
commercial exact ICPN is checked separately. This never invokes OpenOCD.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ORIGINAL_INDEX = "data/device-catalog/research/microchip-phase1-remaining2441-exact-identity-v1.csv"
PRODUCT_SOURCE = "data/device-catalog/research/microchip-pic32mx-893-commercial-l1-v1.csv"
SOURCE_INDEX_BLOB = "2f7a2b1b768e2c4ccb0eb184330c405cc3826357"
DRIVER_GIT_BLOB = "9a1a6341256039bf9fd68e41a109e7483a5f694e"
DRIVER_SOURCE_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
EXPECTED_EXACT = 893
EXPECTED_BASES = 85

from microchip_pic32mx_devid_route_review_v1 import extract_device_table


def ensure(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("PIC32MX 893 Production identity gate: " + reason)


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False
    ).hexdigest()


def check(original_path: Path, product_path: Path, driver_path: Path) -> dict:
    original_raw = original_path.read_bytes()
    ensure(blob_sha(original_raw) == SOURCE_INDEX_BLOB,
           "manufacturer original 2441 source index Git blob changed")
    original = list(csv.DictReader(original_raw.decode("utf-8").splitlines()))
    ensure(len(original) == 2441, "official exact identity index count drift")
    original_by_key = {}
    for row in original:
        icpn = row["icpn"].upper()
        ensure(icpn not in original_by_key, "duplicate official exact identity")
        original_by_key[icpn] = row
    source = driver_path.read_bytes()
    ensure(blob_sha(source) == DRIVER_GIT_BLOB, "OpenOCD driver Git blob changed")
    devs = extract_device_table(source)
    eligible = {
        r["icpn"].upper(): r for r in original
        if r["openocd_cfg_research_only"] == "tcl/target/pic32mx.cfg"
        and r["base_device"] in devs
    }
    ensure(len(eligible) == EXPECTED_EXACT
           and len({r["base_device"] for r in eligible.values()}) == EXPECTED_BASES,
           "manufacturer-to-driver exact Base Device mapping drift")
    rows = list(csv.DictReader(product_path.read_text(encoding="utf-8").splitlines()))
    ensure(len(rows) == EXPECTED_EXACT, "Product source exact ICPN count drift")
    seen = set()
    for row in rows:
        icpn = row["icpn"].upper()
        ensure(icpn not in seen and icpn in eligible,
               f"unapproved or duplicated Exact ICPN: {icpn}")
        seen.add(icpn)
        o = eligible[icpn]
        base = o["base_device"]
        ref = row["source_reference"]
        sha_refs = o["original_mcp_response_sha256_refs"]
        ensure(len(sha_refs) == 64 and all(c in "0123456789abcdef" for c in sha_refs),
               f"original official MCP response evidence invalid: {icpn}")
        ensure(
            row["manufacturer"] == o["manufacturer"] == "Microchip"
            and row["family"] == row["series"] == "PIC32MX"
            and row["base_device"] == base
            and row["mapping_status"] == "no_mapping"
            and not row["openocd_target_config"]
            and not row["existing_identifier"]
            and not row["existing_identifier_kind"]
            and row["source_authority"] == "Microchip Technology official"
            and row["verification_status"] ==
                "verified_microchip_mcp_exact_ordering_and_pinned_openocd_devid"
            and row["source_type"] ==
                "microchip_official_mcp_replayed_identity_openocd_driver_devid"
            and all(not row[k] for k in (
                "package", "pin_count", "flash_size", "temperature_grade",
                "option_suffix", "cmsis_device_name"))
            and f"partNumber={icpn}" in ref
            and f"basePartNumber={base}" in ref
            and f"original_response_sha256={sha_refs};" in ref
            and f"git_blob={SOURCE_INDEX_BLOB}" in ref
            and f"driver_blob={DRIVER_GIT_BLOB}" in ref
            and f"source_commit={DRIVER_SOURCE_COMMIT}" in ref
            and f"expected_devid={devs[base]}" in ref
            and "candidate_only_no_executable_mapping" in ref,
            f"{icpn}: Product identity or source lock would claim unsupported fact",
        )
    ensure(seen == set(eligible), "Product Exact ICPN membership incomplete")
    return {
        "source_identity_rows": len(original),
        "exact_icpns_admitted": len(rows),
        "source_pinned_base_devices": EXPECTED_BASES,
        "driver_source_commit": DRIVER_SOURCE_COMMIT,
        "software_supported_claimed": False,
        "job_execution_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-index", type=Path, default=REPO / ORIGINAL_INDEX)
    parser.add_argument("--product-source", type=Path, default=REPO / PRODUCT_SOURCE)
    parser.add_argument("--driver-source", type=Path, required=True)
    args = parser.parse_args()
    print(check(args.original_index, args.product_source, args.driver_source))


if __name__ == "__main__":
    main()

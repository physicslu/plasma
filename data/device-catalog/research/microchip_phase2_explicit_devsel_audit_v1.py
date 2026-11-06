#!/usr/bin/env python3
"""Microchip Phase-2 exact Part/DEVSEL source audit (Research only).

Preserves the 1,015 Product L1 admission from PR #965.  The 1,548 remaining
Research candidates require original manufacturer identity plus a provable
programming-relevant route.  The only positively classified candidates here
are exact entries in the pinned OpenOCD at91samd.c / atsame5.c chip tables.

This does NOT mutate Production, admit identities or grant Job/L2/HIL.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[3]
ORIGINAL = REPO / "data/device-catalog/research/microchip-phase1-remaining2441-exact-identity-v1.csv"
PIC_ADMITTED = REPO / "data/device-catalog/research/microchip-pic32mx-893-commercial-l1-v1.csv"
ORIGINAL_BLOB = "2f7a2b1b768e2c4ccb0eb184330c405cc3826357"
PINNED_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
CFG_SAMD = "tcl/target/at91samdXX.cfg"
CFG_SAME5 = "tcl/target/atsame5x.cfg"
BLOBS = {
    "at91samd": "33e86c76e9f8310510844793da3f3074ed5dae8f",
    "atsame5": "fdd610f5f38bcbeddd3131105f046c7b67f30381",
}
DRIVER_PATHS = {
    "at91samd": "src/flash/nor/at91samd.c",
    "atsame5": "src/flash/nor/atsame5.c",
}
PART = re.compile(
    r'\{\s*0x([0-9a-fA-F]{1,2})\s*,\s*"((?:SAMC|SAMD|SAML|SAMR|SAME)[A-Z0-9]+)"\s*,'
    r'\s*([0-9]+)\s*,\s*([0-9]+)\s*\}'
)
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
EXPECTED_PER_CFG = {
    "tcl/target/pic32mx.cfg": 1241,
    CFG_SAMD: 667,
    CFG_SAME5: 354,
    "tcl/target/atsamv.cfg": 175,
    "tcl/target/atsaml1x.cfg": 4,
}


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("Microchip 1548 explicit part review: " + why)


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False,
    ).hexdigest()


def original_rows(raw: bytes) -> list[dict[str, str]]:
    require(git_blob(raw) == ORIGINAL_BLOB, "original MCP exact identity index blob drift")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    require(len(rows) == 2441, "original 2441 source cohort count drift")
    require(dict(Counter(r["openocd_cfg_research_only"] for r in rows)) ==
            EXPECTED_PER_CFG, "source-replayed CFG cohort membership drift")
    seen = set()
    for row in rows:
        part = row["icpn"].upper()
        require(part not in seen, "duplicate official commercial identity")
        seen.add(part)
        require(row["manufacturer"] == "Microchip"
                and row["phase1_identity_status"] == "IDENTIFIED"
                and row["source_scope"] == "official_mcp_search_products_exact_partNumber_row"
                and row["official_material_source_uri"] == "https://api.microchip.com/mcp/resources"
                and bool(row["base_device"])
                and HEX64.fullmatch(row["original_mcp_response_sha256_refs"]) is not None
                and row["phase2_programming_state"] == "UNKNOWN"
                and row["phase3_compatibility_state"] == "NOT_TESTED"
                and row["executable_mapping_status"] == "no_mapping",
                "original exact manufacturer evidence is incomplete")
    return rows


def driver_parts(raw: bytes, *, driver: str) -> dict[str, dict[str, object]]:
    require(driver in BLOBS, "unknown driver")
    require(git_blob(raw) == BLOBS[driver], "upstream driver blob differs from pinned v0.12.0")
    entries = PART.findall(raw.decode("utf-8"))
    expect = 156 if driver == "at91samd" else 25
    require(len(entries) == expect, "upstream part table entry count drift")
    parts: dict[str, dict[str, object]] = {}
    for did, part, flash_kb, ram_kb in entries:
        require(part not in parts, "duplicate driver part entry")
        parts[part] = {
            "driver_devsel": "0x" + did.upper().zfill(2),
            "driver_flash_kb_research_only": int(flash_kb),
            "driver_ram_kb_research_only": int(ram_kb),
        }
    return parts


def audit(original: bytes, previous: bytes, driver_d: bytes, driver_e: bytes) -> dict:
    rows = original_rows(original)
    prev = list(csv.DictReader(io.StringIO(previous.decode("utf-8"))))
    previously_admitted = {r["icpn"].upper() for r in prev}
    require(len(prev) == len(previously_admitted) == 893
            and all(r["family"] == "PIC32MX" for r in prev),
            "PR965 PIC32MX cohort membership drift")
    all_source = {r["icpn"].upper(): r for r in rows}
    require(previously_admitted.issubset(all_source)
            and all(all_source[icpn]["openocd_cfg_research_only"] ==
                    "tcl/target/pic32mx.cfg" for icpn in previously_admitted),
            "previous admitted cohort does not match original manufacturer sources")
    d = driver_parts(driver_d, driver="at91samd")
    e = driver_parts(driver_e, driver="atsame5")
    statuses = Counter()
    by_cfg = Counter()
    accepted_bases = defaultdict(set)
    queue = []
    for row in rows:
        icpn = row["icpn"]
        if icpn.upper() in previously_admitted:
            continue
        cfg = row["openocd_cfg_research_only"]
        base = row["base_device"]
        part = None
        route = None
        driver = None
        if cfg in {CFG_SAMD, CFG_SAME5}:
            # Manufacturer verified Base Device is e.g. ATSAMD51J18A.
            # The pinned upstream Part Table uses SAMD51J18A.
            # Only this well-defined Atmel brand prefix is normalized.
            require(base.startswith("AT") and len(base) > 2,
                    "unverified Microchip/Atmel Base Device naming")
            part = base[2:]
            driver = "at91samd" if cfg == CFG_SAMD else "atsame5"
            route = (d if cfg == CFG_SAMD else e).get(part)
        state = ("EXACT_DRIVER_PART_DEVSEL_REVIEW_CANDIDATE"
                 if route is not None
                 else "NO_EXPLICIT_DRIVER_PART_TABLE_MATCH")
        statuses[state] += 1
        by_cfg[cfg] += 1
        if route is not None:
            accepted_bases[cfg].add(base)
        queue.append({
            "manufacturer": "Microchip",
            "exact_icpn": icpn,
            "official_base_device": base,
            "official_original_response_sha256":
                row["original_mcp_response_sha256_refs"],
            "identity_index_git_blob": ORIGINAL_BLOB,
            "driver_named_part": part if route else None,
            "driver_devsel": route["driver_devsel"] if route else None,
            "openocd_version": "0.12.0",
            "openocd_source_commit": PINNED_COMMIT,
            "route_source": DRIVER_PATHS[driver] if route else None,
            "route_source_git_blob": BLOBS[driver] if route else None,
            "research_review_state": state,
            "canonical_identity_admitted": False,
            "canonical_route_admitted": False,
            "catalog_level": None,
            "job_selectable": False,
            "execution_authorized": False,
        })
    require(len(queue) == 1548, "not exactly 1548 remaining Research ICPNs")
    require(dict(by_cfg) == {
        "tcl/target/pic32mx.cfg": 348,
        CFG_SAMD: 667,
        CFG_SAME5: 354,
        "tcl/target/atsamv.cfg": 175,
        "tcl/target/atsaml1x.cfg": 4,
    }, "remaining group counts drift")
    require(dict(statuses) == {
        "EXACT_DRIVER_PART_DEVSEL_REVIEW_CANDIDATE": 892,
        "NO_EXPLICIT_DRIVER_PART_TABLE_MATCH": 656,
    }, "new direct candidate count drift")
    require({key: len(value) for key, value in accepted_bases.items()} == {
        CFG_SAMD: 59,
        CFG_SAME5: 25,
    }, "positive Base Device review population drift")
    queue.sort(key=lambda x: x["exact_icpn"].casefold())
    return {
        "schema_version": 1,
        "scope": "MICROCHIP_RESEARCH_PHASE2_1548_NON_EXECUTABLE",
        "manufacturer_identity_index_git_blob": ORIGINAL_BLOB,
        "openocd_source_commit": PINNED_COMMIT,
        "original_replay_source_count": len(rows),
        "previously_admitted_pic32mx_exact_icpns": len(prev),
        "remaining_icpns": len(queue),
        "candidate_counts": dict(sorted(statuses.items())),
        "by_cfg": dict(sorted(by_cfg.items())),
        "direct_base_device_counts": {k: len(v) for k, v in sorted(accepted_bases.items())},
        "production_write_authorized": False,
        "openocd_software_supported_claimed": False,
        "job_execution_authorized": False,
        "rows": queue,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-index", type=Path, default=ORIGINAL)
    parser.add_argument("--prior-pic32mx", type=Path, default=PIC_ADMITTED)
    parser.add_argument("--driver-d", required=True, type=Path)
    parser.add_argument("--driver-e", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require("production" not in {p.lower() for p in args.output.resolve().parts},
            "no Research ledger may be written to Product Production")
    result = audit(args.original_index.read_bytes(), args.prior_pic32mx.read_bytes(),
                   args.driver_d.read_bytes(), args.driver_e.read_bytes())
    output = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    if args.verify:
        require(args.output.read_bytes() == output, "Research ledger non-deterministic")
    else:
        require(not args.output.exists(), "refuse to overwrite existing audit result")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
    print(json.dumps({key: result[key] for key in
                      ("remaining_icpns", "candidate_counts", "direct_base_device_counts")},
                     sort_keys=True))


if __name__ == "__main__":
    main()

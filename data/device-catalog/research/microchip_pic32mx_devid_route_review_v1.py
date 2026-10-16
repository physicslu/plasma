#!/usr/bin/env python3
"""Audit Microchip PIC32MX L1 route applicability using pinned OpenOCD DEVID table.

Only source-locked manufacturer Base Devices matching an explicit OpenOCD
pic32mx_devs[] entry get DIRECT_DEVICE_ID_ROUTE_EVIDENCE. This is an L1
research evidence class, NOT Product admission, L2 support or execution.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

EXPECTED_PROVIDER_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
EXPECTED_DRIVER_PATH = "src/flash/nor/pic32mx.c"
EXPECTED_DRIVER_BLOB = "9a1a6341256039bf9fd68e41a109e7483a5f694e"
EXPECTED_CFG = "tcl/target/pic32mx.cfg"
EXPECTED_CFG_BLOB = "df68e807aeb504ab8b23b547803405df586b3928"
EXPECTED_LEDGER_REPORT = "548c1a61c311bdad1c153565e966c768785f7ecaf28311693bd19c212ae734f0"
ENTRY = re.compile(r'\{\s*0x([A-Fa-f0-9]{8}),\s*"([0-9A-Z]+)"\s*\}')


def require(test: bool, message: str) -> None:
    if not test:
        raise ValueError(f"PIC32MX DEVID applicability: {message}")


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def extract_device_table(driver_source: bytes, *, strict_source_lock: bool = True) -> dict[str, str]:
    if strict_source_lock:
        require(blob_sha(driver_source) == EXPECTED_DRIVER_BLOB,
                "pinned OpenOCD driver bytes changed")
    text = driver_source.decode("utf-8")
    start = text.find("} pic32mx_devs[] = {")
    end = text.find("{0x00000000, NULL}", start)
    require(start >= 0 and end > start, "cannot locate driver PIC32MX DEVID table")
    entries = ENTRY.findall(text[start:end])
    require(len(entries) == 89, "driver DEVID entry count changed")
    devs: dict[str, str] = {}
    ids = set()
    for devid, device_name in entries:
        key = "PIC32MX" + device_name
        require(key not in devs and devid not in ids,
                "duplicated OpenOCD DEVID / device name")
        devs[key] = "0x" + devid.upper()
        ids.add(devid)
    return devs


def build(ledger: dict, driver_source: bytes, *, strict_source_lock: bool = True) -> dict:
    require(ledger.get("scope") == "microchip_original_source_replayed_l1_admission_review_queue"
            and ledger.get("source_report_sha256") == EXPECTED_LEDGER_REPORT
            and ledger.get("provider_source_commit") == EXPECTED_PROVIDER_COMMIT
            and ledger.get("research_cfg_candidates") == 2563
            and ledger.get("identity_canonical_admitted_by_this_tool") == 0
            and ledger.get("route_canonical_admitted_by_this_tool") == 0
            and ledger.get("production_write_authorized") is False,
            "untrusted original replay ledger/provenance")
    devices = extract_device_table(driver_source, strict_source_lock=strict_source_lock)
    rows = ledger.get("rows")
    require(isinstance(rows, list) and len(rows) == 2563,
            "Research ledger row population drift")
    bases = defaultdict(set)
    classifications = Counter()
    result = []
    for row in rows:
        if row.get("target_config") != EXPECTED_CFG:
            continue
        require(row.get("manufacturer") == "Microchip"
                and row.get("target_config_git_blob_sha1") == EXPECTED_CFG_BLOB
                and row.get("flash_driver_source") == EXPECTED_DRIVER_PATH
                and row.get("flash_driver_git_blob_sha1") == EXPECTED_DRIVER_BLOB
                and row.get("identity_replay_status") ==
                    "SOURCE_REPLAYED_PENDING_CANONICAL_ADMISSION"
                and row.get("canonical_admission") == "PENDING"
                and row.get("job_selectable") is False
                and row.get("execution_authorized") is False,
                "PIC32MX source / permission boundary mismatch")
        base = row["base_device"]
        exact = base in devices
        disposition = ("DIRECT_DRIVER_DEVID_ROUTE_EVIDENCE"
                       if exact else "DRIVER_DEVID_NOT_LISTED_REVIEW_REQUIRED")
        classifications[disposition] += 1
        bases[disposition].add(base)
        result.append({
            "manufacturer": "Microchip",
            "exact_icpn": row["exact_icpn"],
            "base_device": base,
            "original_mcp_response_sha256_refs":
                row["identity_original_response_sha256_refs"],
            "openocd_source_commit": EXPECTED_PROVIDER_COMMIT,
            "target_config": EXPECTED_CFG,
            "target_config_git_blob_sha1": EXPECTED_CFG_BLOB,
            "flash_driver_source": EXPECTED_DRIVER_PATH,
            "flash_driver_git_blob_sha1": EXPECTED_DRIVER_BLOB,
            "flash_driver_devid": devices.get(base),
            "route_evidence_review": disposition,
            "canonical_admission": "PENDING",
            "catalog_level": None,
            "job_selectable": False,
            "execution_authorized": False,
        })
    require(len(result) == 1241, "PIC32MX Research exact ICPN count drift")
    require(dict(classifications) == {
        "DIRECT_DRIVER_DEVID_ROUTE_EVIDENCE": 893,
        "DRIVER_DEVID_NOT_LISTED_REVIEW_REQUIRED": 348,
    }, "OpenOCD driver device applicability population drift")
    require({key: len(value) for key, value in bases.items()} == {
        "DIRECT_DRIVER_DEVID_ROUTE_EVIDENCE": 85,
        "DRIVER_DEVID_NOT_LISTED_REVIEW_REQUIRED": 31,
    }, "Base Device review population drift")
    return {
        "schema_version": 1,
        "scope": "pic32mx_source_locked_driver_devid_route_review_only",
        "driver_git_blob": EXPECTED_DRIVER_BLOB,
        "provider_source_commit": EXPECTED_PROVIDER_COMMIT,
        "route_review_counts": dict(sorted(classifications.items())),
        "base_device_review_counts": {
            key: len(value) for key, value in sorted(bases.items())
        },
        "source_rows": len(result),
        "production_write_authorized": False,
        "l2_supported": False,
        "execution_authorized": False,
        "rows": sorted(result, key=lambda row: row["exact_icpn"].casefold()),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--driver-source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    require("production" not in {part.lower() for part in args.output.resolve().parts},
            "forbid Research evidence being written into Production")
    result = build(json.loads(args.ledger.read_bytes()), args.driver_source.read_bytes())
    encoded = (json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    if args.verify:
        require(args.output.read_bytes() == encoded,
                "non-deterministic PIC32MX route evidence review")
    else:
        require(not args.output.exists(), "refuse overwrite review evidence")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    print(json.dumps({
        "icpns": result["source_rows"],
        "route_review_counts": result["route_review_counts"],
        "base_device_review_counts": result["base_device_review_counts"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()

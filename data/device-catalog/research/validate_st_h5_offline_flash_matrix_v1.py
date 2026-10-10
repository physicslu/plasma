#!/usr/bin/env python3
"""Deterministic ST H5 exact-ICPN / pinned ST-fork driver static crosswalk.

No production admission or backend selection, no device access and no vendor
binaries. Driver/target facts are source-reviewed against pinned Git blobs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
FACTS = ROOT / "data/device-catalog/research/st-h5-offline-flash-matrix-v1.json"
GAP = ROOT / "data/device-catalog/research/st-h5-c5-runtime-gap-v1.json"
CSV_RELATIVE = "../research/stm32h5-commercial-icpn.csv"
EXPECTED_SERIES = {
    "STM32H503": 14, "STM32H523": 39, "STM32H533": 14,
    "STM32H543": 4, "STM32H553": 2,
    "STM32H562": 22, "STM32H563": 37, "STM32H573": 23,
    "STM32H5E4": 13, "STM32H5E5": 9, "STM32H5F4": 9, "STM32H5F5": 4,
}
EXPECTED_NO_MAPPING = 190
EXPECTED_GROUPS = {
    # source driver stm32h5x.h DEVID_* and stm32h5x.c dev_info_db
    "STM32H50xx": ("0x474", 128, False, 1),
    "STM32H52/H53xx": ("0x478", 512, True, 4),
    "STM32H54/H55xx": ("0x47C", 1024, True, 4),
    "STM32H56/H57xx": ("0x484", 2048, True, 4),
    "STM32H5E/H5Fxx": ("0x47A", 4096, True, 4),
}


class OfflineMatrixError(ValueError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OfflineMatrixError(f"cannot read JSON authority {path}") from exc
    if not isinstance(payload, dict):
        raise OfflineMatrixError(f"expected JSON object in {path}")
    return payload


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\\0".encode() + data).hexdigest()


def _load(root: Path) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    facts = _read_json(root / FACTS.relative_to(ROOT))
    gap = _read_json(root / GAP.relative_to(ROOT))
    manifest = _read_json(root / MANIFEST.relative_to(ROOT))
    if facts.get("schema_version") != 1 or facts.get("candidate_status") != "RESEARCH_ONLY_NOT_PRODUCTION_MAPPED":
        raise OfflineMatrixError("H5 matrix schema/candidate boundary invalid")
    if facts.get("evidence_level") != "source_and_catalog_static_crosswalk_only":
        raise OfflineMatrixError("H5 matrix evidence boundary drifted")
    if manifest.get("schema_version") != 1 or manifest.get("status") != "production":
        raise OfflineMatrixError("Production manifest schema/state invalid")
    source = facts["source"]
    pinned = gap["candidate_st_fork"]
    if source["repository"] != "https://github.com/STMicroelectronics/OpenOCD.git":
        raise OfflineMatrixError("unexpected source repository")
    if pinned["repository"] != "STMicroelectronics/OpenOCD" or source["commit"] != pinned["commit"]:
        raise OfflineMatrixError("H5 ST fork source commit drift")
    for matrix_key, gap_key, suffix in (
        ("header_git_blob", "h5_flash_header", "header_path"),
        ("driver_git_blob", "h5_flash_driver", "driver_path"),
        ("target_config_git_blob", "h5_cfg", "target_config_path"),
    ):
        expected = pinned["files"][gap_key]
        if source[matrix_key] != expected["blob"] or source[suffix] != expected["path"]:
            raise OfflineMatrixError(f"H5 ST fork source blob or path drift: {matrix_key}")

    invariants = {
        "flash_driver": "stm32h5x",
        "flash_base_address": "0x08000000",
        "secure_flash_alias_address": "0x0C000000",
        "dbgmcu_idcode_register": "0x44024000",
        "flash_size_register": "0x08FFF80C",
        "flash_register_base": "0x40022000",
        "flash_sector_kib": 8,
        "flash_write_alignment_bytes": 16,
        "driver_flash_size_failure_falls_back_to_max": True,
        "driver_assumes_dual_bank": True,
    }
    for k, expected in invariants.items():
        if facts.get(k) != expected:
            raise OfflineMatrixError(f"H5 source-reviewed invariant changed: {k}")
    group_map: dict[str, dict[str, Any]] = {}
    series_map: dict[str, dict[str, Any]] = {}
    seen_ids = set()
    groups = facts.get("device_groups")
    if not isinstance(groups, list) or len(groups) != 5:
        raise OfflineMatrixError("expected five pinned ST H5 driver device groups")
    for group in groups:
        if not isinstance(group, dict) or group.get("group") not in EXPECTED_GROUPS:
            raise OfflineMatrixError("unrecognized H5 driver device group")
        group_id = group["group"]
        if group_id in group_map:
            raise OfflineMatrixError(f"duplicate H5 driver group {group_id}")
        expected_id, max_kib, tz, wpsn = EXPECTED_GROUPS[group_id]
        if (group.get("expected_device_id"), group.get("max_flash_kib"), group.get("has_trustzone"),
                group.get("wps_group_sectors")) != (expected_id, max_kib, tz, wpsn):
            raise OfflineMatrixError(f"source-reviewed H5 group property mismatch: {group_id}")
        if group.get("expected_icpns", 0) < 1:
            raise OfflineMatrixError("invalid group count")
        if expected_id in seen_ids:
            raise OfflineMatrixError("duplicate H5 device ID")
        seen_ids.add(expected_id)
        series_list = group.get("series")
        if not isinstance(series_list, list) or not series_list:
            raise OfflineMatrixError("empty driver group series")
        for series in series_list:
            if series in series_map or series not in EXPECTED_SERIES:
                raise OfflineMatrixError(f"duplicate/unknown H5 series: {series}")
            series_map[series] = group
        group_map[group_id] = group
    if set(group_map) != set(EXPECTED_GROUPS) or set(series_map) != set(EXPECTED_SERIES):
        raise OfflineMatrixError("H5 source group coverage incomplete")

    qual = facts.get("qualification")
    if not isinstance(qual, dict) or qual.get("driver_source_identity_locked") is not True:
        raise OfflineMatrixError("H5 matrix requires source pin")
    if qual.get("expected_device_ids_inferred_from_family") is not True:
        raise OfflineMatrixError("H5 IDs must remain family-inferred, not measured")
    for key in ("silicon_device_id_measured", "flash_size_register_measured",
                "flash_geometry_hardware_verified", "flash_erase_program_verify_passed",
                "physical_hardware_runtime_ready", "production_backend_mapping_authorized",
                "unsafe_vendor_commands_authorized"):
        if qual.get(key) is not False:
            raise OfflineMatrixError(f"hardware/production security gate must be false: {key}")

    sources = [s for s in manifest.get("sources", [])
               if s.get("manufacturer") == "STMicroelectronics" and s.get("family") == "STM32H5"]
    if len(sources) != 1:
        raise OfflineMatrixError("expected exactly one canonical ST H5 Production source")
    source_meta = sources[0]
    if source_meta.get("row_count") != EXPECTED_NO_MAPPING or source_meta.get("path") != CSV_RELATIVE:
        raise OfflineMatrixError("H5 Production manifest count/path drift")
    csv_path = (root / MANIFEST.relative_to(ROOT)).parent / CSV_RELATIVE
    try:
        data = csv_path.read_bytes()
    except OSError as exc:
        raise OfflineMatrixError("missing Production-linked H5 CSV") from exc
    if _sha256(data) != source_meta.get("sha256") or _git_blob_sha(data) != source_meta.get("git_blob_sha"):
        raise OfflineMatrixError("H5 canonical CSV hash mismatch")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    rows = list(reader)
    if len(rows) != EXPECTED_NO_MAPPING:
        raise OfflineMatrixError("H5 exact MPN count drift")
    if len({r["icpn"] for r in rows}) != EXPECTED_NO_MAPPING:
        raise OfflineMatrixError("duplicate exact H5 ICPN")
    if Counter(r["series"] for r in rows) != Counter(EXPECTED_SERIES):
        raise OfflineMatrixError("H5 per-series Production snapshot changed")
    if Counter(g["group"] for g in (series_map[r["series"]] for r in rows)) != Counter(
        {g["group"]: g["expected_icpns"] for g in groups}
    ):
        raise OfflineMatrixError("H5 driver group per-ICPN count mismatch")
    return rows, facts, source_meta


def make_records(rows: list[dict[str, str]], facts: dict[str, Any]) -> list[dict[str, Any]]:
    series_map = {series: group for group in facts["device_groups"] for series in group["series"]}
    result = []
    for row in rows:
        icpn = row["icpn"]
        if row["manufacturer"] != "STMicroelectronics" or row["family"] != "STM32H5":
            raise OfflineMatrixError(f"unexpected manufacturer/family: {icpn}")
        if row["mapping_status"] != "no_mapping" or row["openocd_target_config"].strip():
            raise OfflineMatrixError(f"H5 Production backend must stay unbound: {icpn}")
        series = row["series"]
        if series not in series_map or not icpn.startswith(series):
            raise OfflineMatrixError(f"unrecognized exact H5 series: {icpn}")
        match = re.fullmatch(r"([1-9][0-9]*) KiB", row["flash_size"])
        if not match:
            raise OfflineMatrixError(f"invalid authoritative H5 flash_size: {icpn}")
        kib = int(match.group(1))
        group = series_map[series]
        if kib > group["max_flash_kib"] or kib % facts["flash_sector_kib"]:
            raise OfflineMatrixError(f"H5 declared capacity outside driver capabilities: {icpn}")
        sectors = kib // facts["flash_sector_kib"]
        wpsn = group["wps_group_sectors"]
        if sectors % (2 * wpsn):
            raise OfflineMatrixError(f"derived H5 bank/protection geometry invalid: {icpn}")
        result.append({
            "icpn": icpn,
            "series": series,
            "base_device": row["base_device"],
            "official_catalog_flash_kib": kib,
            "official_catalog_source": row["source_reference"],
            "candidate_provider": "STMicroelectronics/OpenOCD",
            "candidate_source_commit": facts["source"]["commit"],
            "target_config": facts["source"]["target_config_path"],
            "target_config_git_blob": facts["source"]["target_config_git_blob"],
            "flash_driver": facts["flash_driver"],
            "flash_driver_git_blob": facts["source"]["driver_git_blob"],
            "driver_device_group": group["group"],
            "expected_device_id_from_series": group["expected_device_id"],
            "actual_silicon_device_id": None,
            "driver_max_flash_kib": group["max_flash_kib"],
            "flash_size_register_address": facts["flash_size_register"],
            "actual_flash_size_register_kib": None,
            "flash_base_address": facts["flash_base_address"],
            "driver_flash_sector_kib": facts["flash_sector_kib"],
            "estimated_sector_count_if_catalog_size_confirmed": sectors,
            "estimated_per_bank_sectors_if_confirmed": sectors // 2,
            "driver_wps_group_sectors": wpsn,
            "estimated_protection_blocks_if_confirmed": sectors // wpsn,
            "write_alignment_bytes": facts["flash_write_alignment_bytes"],
            "driver_has_trustzone": group["has_trustzone"],
            "driver_flash_size_probe_max_fallback": True,
            "device_geometry_verification_required": True,
            "security_state_verification_required": True,
            "production_mapping_status": "no_mapping",
            "candidate_status": "research_only_not_production_mapped",
            "qualification_status": "static_source_and_catalog_only",
            "hardware_runtime_ready": False,
            "programming_write_authorized": False,
        })
    return sorted(result, key=lambda r: r["icpn"])


def audit(root: Path = ROOT) -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    rows, facts, source_meta = _load(root)
    records = make_records(rows, facts)
    if len(records) != EXPECTED_NO_MAPPING:
        raise OfflineMatrixError("H5 records count mismatch")
    jsonl = ("\\n".join(json.dumps(r, sort_keys=True, separators=(",", ":"))
                       for r in records) + "\\n").encode("utf-8")
    summary = {
        "schema_version": 1,
        "audit_id": facts["audit_id"],
        "candidate_status": facts["candidate_status"],
        "production_mapping_modified": False,
        "h5_exact_icpns": len(records),
        "st_driver_device_id_groups": len(facts["device_groups"]),
        "group_counts": dict(sorted(Counter(r["driver_device_group"] for r in records).items())),
        "series_counts": dict(sorted(Counter(r["series"] for r in records).items())),
        "catalog_source_sha256": source_meta["sha256"],
        "candidate_source_commit": facts["source"]["commit"],
        "records_jsonl_sha256": _sha256(jsonl),
        "hardware_runtime_ready": False,
        "real_silicon_qualifications": 0,
        "production_backend_mapping_authorized": False,
    }
    return records, summary, jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icpn", help="print the exact STM32H5 Production ICPN static candidate evidence")
    parser.add_argument("--output-dir", type=Path, help="export all 190 H5 records and a content-hash summary")
    args = parser.parse_args(argv)
    try:
        records, summary, jsonl = audit()
    except (OSError, KeyError, TypeError, OfflineMatrixError) as exc:
        print(f"STM32H5 offline matrix validation FAILED: {exc}", file=sys.stderr)
        return 1
    if args.icpn:
        matched = [r for r in records if r["icpn"].casefold() == args.icpn.strip().casefold()]
        if len(matched) != 1:
            print("ICPN not found in exact H5 Production catalog", file=sys.stderr)
            return 2
        print(json.dumps(matched[0], indent=2, sort_keys=True))
    elif not args.output_dir:
        print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "st-h5-offline-flash-matrix-v1.jsonl").write_bytes(jsonl)
        (args.output_dir / "st-h5-offline-flash-matrix-v1-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
        print(f"H5 offline matrix PASS: {len(records)} records SHA256={summary['records_jsonl_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

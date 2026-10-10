#!/usr/bin/env python3
"""172 exact ST C5 ICPN -> DFP STLDR research readiness, no device execution.

Rejoins the current SHA-bound Production C5 catalog with the earlier source-pinned
DFP crosswalk. The 33 absent DFP exact variants have official Production metadata;
they still lack exact DFP algorithm applicability evidence.
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

import validate_st_c5_dfp_loader_crosswalk_v09 as v09

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
CSV_REL = "../research/stm32c5-commercial-icpn.csv"
DFP_REPORT = HERE / "st-c5-dfp-commercial-loader-crosswalk-v0.9.json"
FORK_REPORT = HERE / "st-c5-ps-backend-static-gate-v1.1.json"
EXPECTED_FAMILY = {
    "C53": ("0x44F", "Flash/STM32C5[34]x.xldr", 65536, 262144),
    "C54": ("0x44F", "Flash/STM32C5[34]x.xldr", 65536, 262144),
    "C55": ("0x44E", "Flash/STM32C5[56]x.xldr", 131072, 524288),
    "C56": ("0x44E", "Flash/STM32C5[56]x.xldr", 131072, 524288),
    "C59": ("0x45A", "Flash/STM32C5[9A]x.xldr", 262144, 1048576),
    "C5A": ("0x45A", "Flash/STM32C5[9A]x.xldr", 262144, 1048576),
}
EXPECTED_COUNTS = {"0x44F": (63, 48, 15), "0x44E": (60, 46, 14), "0x45A": (49, 45, 4)}
EXPECTED_SERIES = {
    "STM32C531": 29, "STM32C532": 22, "STM32C542": 12,
    "STM32C551": 29, "STM32C552": 19, "STM32C562": 12,
    "STM32C591": 20, "STM32C593": 19, "STM32C5A3": 10,
}


class MatrixError(ValueError):
    pass


def ensure(ok: bool, explanation: str) -> None:
    if not ok:
        raise MatrixError(explanation)


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()


def get_catalog() -> tuple[list[dict[str, str]], dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ensure(manifest.get("schema_version") == 1 and manifest.get("status") == "production",
           "Production manifest must remain schema 1")
    sources = manifest["sources"]
    ensure(len(sources) == 28 and sum(s["row_count"] for s in sources) == 4629,
           "Production exact catalog baseline drift")
    c5 = [s for s in sources if s.get("manufacturer") == "STMicroelectronics"
          and s.get("family") == "STM32C5"]
    ensure(len(c5) == 1 and c5[0]["path"] == CSV_REL and c5[0]["row_count"] == 172,
           "canonical C5 Production source mismatch")
    raw = (MANIFEST.parent / CSV_REL).read_bytes()
    ensure(hashlib.sha256(raw).hexdigest() == c5[0]["sha256"] and
           blob_sha(raw) == c5[0]["git_blob_sha"], "Production C5 catalog SHA/blob mismatch")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    ensure(len(rows) == 172 and len({r["icpn"] for r in rows}) == 172,
           "current C5 exact identities invalid")
    ensure(Counter(r["series"] for r in rows) == Counter(EXPECTED_SERIES),
           "current C5 series distribution drift")
    return rows, c5[0]


def source_authority() -> tuple[dict, dict, dict]:
    # v0.9 is a historical source ledger. Its validate() transitively asserts
    # the superseded ST Production 2683-exact/23-source state and CANNOT be
    # replayed as a current baseline. Reuse immutable source facts/row checks
    # here while get_catalog() independently locks today's 4629/172 snapshot.
    dfp = json.loads(DFP_REPORT.read_text(encoding="utf-8"))
    fork = json.loads(FORK_REPORT.read_text(encoding="utf-8"))
    ensure(dfp["record_state"] == "RESEARCH_ONLY_NOT_PRODUCTION_ADMISSION" and
           fork["research_only"] is True, "research provenance was promoted")
    upstream = dfp["official_dfp_source"]
    ensure(upstream["pinned_commit"] == "a5f65bc64535cfa723e9d25f58d7ce23d0937aed" and
           upstream["pdsc_git_blob_sha"] == v09.EXPECTED_DFP_BLOB,
           "official DFP commit/PDSC blob drift")
    st = fork["manufacturer_openocd_fork"]
    ensure(st["pinned_commit"] == "c8d973bdad9a6fddb51459eda109b3b95d23b57a" and
           st["target_cfg_blob_sha"] == v09.EXPECTED_FORK_CFG_BLOB,
           "ST fork target config provenance drift")
    fix = st["source_tcl_defect"]
    ensure(fix["flash_fallback_original"] == "set die_max_flash_size {" and
           fix["flash_fallback_candidate"] == "array set die_max_flash_size {" and
           fix["loader_table_original"] == "set dev_id_loader {\n}" and
           fix["loader_table_candidate"] == "array set dev_id_loader {\n}" and
           fix["loader_table_remains_empty_in_research_fix"] is True,
           "Tcl repairs unexpectedly promoted or fork defect drift")
    ensure(st["target_default_workarea_bytes"] == 32768 and
           st["loader_missing_device_id_remains_blocked"] is True,
           "source work area or empty-loader boundary changed")
    gates = fork["gates"]
    for gate in ("official_vendor_binary_license_approved",
                 "stldr_compiled_in_plasma_chosen_binary_verified",
                 "plasma_target_cfg_deployed_and_loader_map_populated",
                 "pinned_loader_ram_compatibility_hil_verified",
                 "real_dev_id_flash_geometry_readback_verified",
                 "source_only_candidate_executable",
                 "production_catalog_update_authorized",
                 "production_programming_authorized"):
        ensure(gates.get(gate) is False, f"C5 original research gate incorrectly opened: {gate}")
    ensure(dfp["commercial_cohort"]["exact_pdsc_variant_matches"] == 139 and
           dfp["commercial_cohort"]["parent_dname_only_missing_exact_dfp_variant"] == 33,
           "historical C5 DFP cohort counts drift")
    return dfp, fork, st


def build_rows(catalog: list[dict[str, str]], crosswalk: list[dict[str, str]],
               dfp: dict, fork: dict, st: dict) -> list[dict]:
    ensure(len(catalog) == len(crosswalk) == 172, "C5 records count invalid")
    by_icpn = {r["icpn"]: r for r in catalog}
    ensure(len(by_icpn) == len(catalog), "C5 catalog has duplicates")
    ensure(set(by_icpn) == {r["icpn"] for r in crosswalk},
           "commercial/DFP identity mismatch")
    loader_map = {r["path"]: r for r in dfp["official_dfp_source"]["loader_files"]}
    ensure(len(loader_map) == 3, "expected three source-pinned DFP loaders")
    results = []
    for row in crosswalk:
        icpn = row["icpn"]
        prod = by_icpn[icpn]
        ensure(prod["manufacturer"] == "STMicroelectronics" and
               prod["family"] == "STM32C5" and prod["mapping_status"] == "no_mapping" and
               not prod["openocd_target_config"], f"Production C5 backend unexpectedly mapped: {icpn}")
        ensure(prod["verification_status"].startswith("verified_") and
               prod["source_reference"].startswith("https://www.st.com/"),
               f"Production C5 exact metadata provenance missing: {icpn}")
        ensure(prod["series"].startswith("STM32C5") and icpn.startswith(prod["series"]),
               f"invalid exact C5 series: {icpn}")
        family = prod["series"][5:8]
        ensure(family in EXPECTED_FAMILY, f"unknown C5 device family: {icpn}")
        expected_id, expected_loader, expected_ram, fallback = EXPECTED_FAMILY[family]
        ensure(row["series"] == family and row["candidate_dev_id"] == expected_id and
               row["candidate_xldr_path"] == expected_loader, f"wrong C5 loader/device ID: {icpn}")
        match = re.fullmatch(r"([1-9]\d*) KiB", prod["flash_size"])
        ensure(match is not None, f"missing official C5 flash capacity: {icpn}")
        declared_bytes = int(match.group(1)) * 1024
        ensure(declared_bytes == int(row["parent_flash_bytes"]) and
               declared_bytes <= fallback, f"C5 Production vs DFP parent geometry mismatch: {icpn}")
        exact = row["dfp_evidence_state"] == "EXACT_DFP_VARIANT"
        ensure(row["dfp_evidence_state"] in ("EXACT_DFP_VARIANT", "BASE_DEVICE_ONLY_NOT_EXACT") and
               (int(row["exact_variant_flash_bytes"]) == declared_bytes if exact
                else row["exact_variant_flash_bytes"] == ""),
               f"C5 exact DFP variant evidence inconsistent: {icpn}")
        ensure(row["dfp_parent_dname"] == prod["base_device"] and
               row["plasma_route_ready"] == "false", f"DFP parent/route unauthorized: {icpn}")
        ensure(row["dfp_loader_ram_start"] == "0x20000000" and
               int(row["dfp_loader_ram_bytes"]) == expected_ram and
               fork["dfp"]["loader_family_alg_ram_bytes"][expected_loader] == expected_ram and
               st["fallback_die_flash_bytes"][expected_id] == fallback,
               f"C5 DFP RAM/fallback mismatch: {icpn}")
        loader = loader_map[expected_loader]
        ensure(loader["dev_id"] == expected_id and
               loader["sha256"] == v09.EXPECTED_LOADER_SHA256[expected_loader] and
               loader["git_blob_sha"] == v09.EXPECTED_LOADERS[expected_loader],
               f"C5 DFP loader digest/identity mismatch: {icpn}")
        results.append({
            "icpn": icpn,
            "series": prod["series"],
            "base_device": prod["base_device"],
            "official_catalog_flash_bytes": declared_bytes,
            "official_exact_catalog_metadata_verified": True,
            "official_catalog_source": prod["source_reference"],
            "dfp_exact_dvariant_present": exact,
            "dfp_evidence_state": row["dfp_evidence_state"],
            "dfp_absence_is_not_catalog_metadata_gap": True,
            "dfp_parent_candidate_flash_bytes": int(row["parent_flash_bytes"]),
            "dfp_exact_variant_flash_bytes": declared_bytes if exact else None,
            "expected_device_id_from_series": expected_id,
            "actual_silicon_device_id": None,
            "actual_flash_size_readback_bytes": None,
            "candidate_loader_path": expected_loader,
            "candidate_loader_source_git_blob": loader["git_blob_sha"],
            "candidate_loader_sha256": loader["sha256"],
            "candidate_dfp_commit": dfp["official_dfp_source"]["pinned_commit"],
            "candidate_openocd_fork_commit": st["pinned_commit"],
            "candidate_openocd_target_cfg_blob": st["target_cfg_blob_sha"],
            "candidate_stldr_driver_blob": st["stldr_driver_blob_sha"],
            "dfp_declared_algorithm_ram_bytes": expected_ram,
            "fork_default_workarea_bytes": st["target_default_workarea_bytes"],
            "ram_compatibility": "unverified_not_assumed_incompatible",
            "fork_flash_size_fallback_bytes_untrusted": fallback,
            "fork_tcl_scalar_array_defects_unresolved": True,
            "fork_dev_id_loader_table_empty": True,
            "official_loader_runtime_staging_verified": False,
            "vendor_binary_redistribution_approved": False,
            "plasma_stldr_backend_qualified": False,
            "physical_device_probe_verified": False,
            "production_mapping_status": "no_mapping",
            "candidate_status": "research_only_not_executable",
            "hardware_runtime_ready": False,
            "erase_program_verify_authorized": False,
        })
    return sorted(results, key=lambda r: r["icpn"])


def audit() -> tuple[list[dict], dict, bytes]:
    catalog, source = get_catalog()
    dfp, fork, st = source_authority()
    crosswalk = v09.read_rows(v09.CROSSWALK.read_text(encoding="utf-8"))
    records = build_rows(catalog, crosswalk, dfp, fork, st)
    by_id = Counter(r["expected_device_id_from_series"] for r in records)
    by_exact = Counter(r["expected_device_id_from_series"] for r in records
                       if r["dfp_exact_dvariant_present"])
    ensure({k: (by_id[k], by_exact[k], by_id[k] - by_exact[k])
            for k in EXPECTED_COUNTS} == EXPECTED_COUNTS, "C5 three-group cohort counts drift")
    ensure(len(records) == 172 and sum(r["dfp_exact_dvariant_present"] for r in records) == 139,
           "C5 exact DFP crosswalk population invalid")
    ensure(all(r["hardware_runtime_ready"] is False and
               r["erase_program_verify_authorized"] is False for r in records),
           "C5 unsafe programming claim")
    raw = ("\n".join(json.dumps(r, sort_keys=True, separators=(",", ":"))
                      for r in records) + "\n").encode("utf-8")
    summary = {
        "schema_version": 1,
        "audit_id": "st-c5-exact-loader-readiness-matrix-v1",
        "status": "RESEARCH_ONLY_NOT_EXECUTABLE",
        "production_exact_st_icpns": 4629,
        "production_c5_exact_icpns": len(records),
        "dfp_exact_dvariant_present": 139,
        "dfp_exact_dvariant_missing": 33,
        "production_exact_metadata_missing": 0,
        "candidate_loader_group_count": 3,
        "candidate_group_counts": {k: {"total": by_id[k], "dfp_exact": by_exact[k],
                                        "dfp_base_only": by_id[k] - by_exact[k]}
                                   for k in sorted(EXPECTED_COUNTS)},
        "catalog_c5_sha256": source["sha256"],
        "dfp_source_commit": dfp["official_dfp_source"]["pinned_commit"],
        "st_fork_source_commit": st["pinned_commit"],
        "records_jsonl_sha256": hashlib.sha256(raw).hexdigest(),
        "production_backend_mapping_modified": False,
        "plasma_stldr_backend_qualified": False,
        "hardware_runtime_ready": False,
        "production_write_authorized": False,
        "real_silicon_qualifications": 0,
    }
    return records, summary, raw


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--icpn", help="inspect one existing exact Production C5 ICPN")
    p.add_argument("--output-dir", type=Path, help="export metadata-only JSONL/summary")
    args = p.parse_args(argv)
    try:
        records, summary, jsonl = audit()
        if args.icpn:
            matches = [r for r in records if r["icpn"] == args.icpn.strip().upper()]
            ensure(len(matches) == 1, "ICPN not in exact Production C5 catalog")
            print(json.dumps(matches[0], indent=2, sort_keys=True))
        elif not args.output_dir:
            print(json.dumps(summary, indent=2, sort_keys=True))
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "st-c5-exact-loader-readiness-v1.jsonl").write_bytes(jsonl)
            (args.output_dir / "st-c5-exact-loader-readiness-v1-summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"C5 matrix PASS: {len(records)} SHA256={summary['records_jsonl_sha256']}")
        return 0
    except (MatrixError, ValueError, KeyError, OSError, json.JSONDecodeError) as e:
        print(f"C5 matrix FAIL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

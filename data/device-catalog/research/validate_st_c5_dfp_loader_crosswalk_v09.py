#!/usr/bin/env python3
"""Fail-closed offline ST C5 exact-MPN/DFP/loader evidence crosswalk.

No backend execution, network by default, Production publication, physical
programming, security mutation, or guessed variants. Optional source arguments
allow cryptographic replay against independently fetched pinned ST raw files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import validate_st_c5_estore_evidence_lock_v07 as prior

HERE = Path(__file__).resolve().parent
REPORT = HERE / "st-c5-dfp-commercial-loader-crosswalk-v0.9.json"
CROSSWALK = HERE / "st-c5-dfp-commercial-loader-crosswalk-v0.9.csv"
HEADERS = (
    "icpn", "series", "dfp_evidence_state", "dfp_parent_dname",
    "candidate_dev_id", "candidate_xldr_path", "parent_flash_bytes",
    "exact_variant_flash_bytes", "dfp_loader_ram_start",
    "dfp_loader_ram_bytes", "plasma_route_ready",
)
SERIES = {
    "C53": ("0x44F", "Flash/STM32C5[34]x.xldr"),
    "C54": ("0x44F", "Flash/STM32C5[34]x.xldr"),
    "C55": ("0x44E", "Flash/STM32C5[56]x.xldr"),
    "C56": ("0x44E", "Flash/STM32C5[56]x.xldr"),
    "C59": ("0x45A", "Flash/STM32C5[9A]x.xldr"),
    "C5A": ("0x45A", "Flash/STM32C5[9A]x.xldr"),
}
EXPECTED_GROUPS = {
    "C53": (51, 39, 12), "C54": (12, 9, 3),
    "C55": (48, 36, 12), "C56": (12, 10, 2),
    "C59": (39, 35, 4), "C5A": (10, 10, 0),
}
EXPECTED_LOADERS = {
    "Flash/STM32C5[34]x.xldr": "ef1d74c6c9cbc7cfe992be476897f621512154a0",
    "Flash/STM32C5[56]x.xldr": "c8f1dfbd183477f79db8fc8174d5d08d3b2fbdb7",
    "Flash/STM32C5[9A]x.xldr": "9b5326edebbed8f7ade21029d6d014aa56d66bba",
}
EXPECTED_DFP_BLOB = "859649be212ea43bc524eb977e1279e45da644c8"
EXPECTED_FORK_CFG_BLOB = "03bce02b166b669ca0d7515656bca68ff4db8b84"
EXPECTED_LICENSE_BLOB = "f404bd9d1021334ecfbbb82da1ee4bbe68a82173"


def require(test: bool, message: str) -> None:
    if not test:
        raise ValueError(message)


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode("ascii") + raw, usedforsecurity=False
    ).hexdigest()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_rows(raw: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw))
    require(tuple(reader.fieldnames or ()) == HEADERS, "crosswalk schema drift")
    rows = []
    for row in reader:
        require(None not in row and None not in row.values(),
                "malformed, missing or excess CSV columns")
        rows.append(row)
    return rows


def build_from_pdsc(raw: bytes, names: list[str]) -> tuple[list[dict[str, str]], int, int]:
    require(git_blob(raw) == EXPECTED_DFP_BLOB, "official DFP PDSC Git blob mismatch")
    root = ET.fromstring(raw)
    require(root.findtext("vendor") == "STMicroelectronics" and
            root.findtext("name") == "stm32c5xx_dfp" and
            root.findtext("license") == "LICENSE.md",
            "unexpected DFP vendor, pack identity or license binding")
    release = root.find("./releases/release")
    require(release is not None and release.get("version") == "2.1.0" and
            release.get("date") == "2026-05-04", "DFP release scope drift")

    base = []
    variants: dict[str, dict] = {}
    for d in root.iter("device"):
        dn = d.get("Dname", "")
        mem = d.find("memory[@name='FLASH']")
        algo = d.find("algorithm")
        require(dn.startswith("STM32C5") and mem is not None and algo is not None,
                "DFP parent has no declared FLASH algorithm")
        item = {
            "dn": dn,
            "flash": int(mem.get("size", "0"), 0),
            "loader": algo.get("name", ""),
            "ram_start": algo.get("RAMstart", ""),
            "ram_bytes": int(algo.get("RAMsize", "0"), 0),
        }
        require(item["flash"] > 0 and item["ram_bytes"] > 0 and
                item["loader"] in EXPECTED_LOADERS, "unexpected DFP flash/loader metadata")
        base.append(item)
        for v in d.iter("variant"):
            code = v.get("Dvariant", "")
            require(code not in variants, "duplicate exact DFP Dvariant")
            variants[code] = item

    require(len(base) == 80 and len(variants) == 157, "DFP base/variant population drift")
    counts = Counter(b["loader"] for b in base)
    require(counts == {
        "Flash/STM32C5[34]x.xldr": 25,
        "Flash/STM32C5[56]x.xldr": 25,
        "Flash/STM32C5[9A]x.xldr": 30,
    }, "DFP per-loader base-device population drift")
    rows = []
    for icpn in names:
        series = icpn[5:8]
        require(series in SERIES, f"unreviewed commercial C5 series {icpn}")
        possible = [b for b in base if icpn.startswith(b["dn"])]
        require(len(possible) == 1, f"no unique DFP parent device for exact {icpn}")
        p = possible[0]
        dev_id, filename = SERIES[series]
        require(p["loader"] == filename,
                f"official DFP algorithm disagrees with DEV_ID family crosswalk {icpn}")
        exact = variants.get(icpn) is p
        rows.append({
            "icpn": icpn,
            "series": series,
            "dfp_evidence_state": (
                "EXACT_DFP_VARIANT" if exact else "BASE_DEVICE_ONLY_NOT_EXACT"
            ),
            "dfp_parent_dname": p["dn"],
            "candidate_dev_id": dev_id,
            "candidate_xldr_path": filename,
            "parent_flash_bytes": str(p["flash"]),
            "exact_variant_flash_bytes": str(p["flash"]) if exact else "",
            "dfp_loader_ram_start": p["ram_start"],
            "dfp_loader_ram_bytes": str(p["ram_bytes"]),
            "plasma_route_ready": "false",
        })
    return rows, len(base), len(variants)


def validate(pdsc: Path | None = None, loader_dir: Path | None = None,
             cfg_path: Path | None = None, license_path: Path | None = None) -> dict:
    old = prior.validate()
    require(old["observed_c5_category_exact_active_mpns"] == 172 and
            old["frozen_st_production"] == 2683, "frozen ST source evidence changed")
    names = prior.validate_set(prior.CODES.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    require(report["audit_id"] == "st-c5-dfp-commercial-loader-crosswalk-v0.9" and
            report["record_state"] == "RESEARCH_ONLY_NOT_PRODUCTION_ADMISSION",
            "report scope drifted")
    official = report["official_dfp_source"]
    require(official["pinned_commit"] == "a5f65bc64535cfa723e9d25f58d7ce23d0937aed" and
            official["pdsc_git_blob_sha"] == EXPECTED_DFP_BLOB and
            official["license_git_blob_sha"] == EXPECTED_LICENSE_BLOB and
            official["device_dname_count"] == 80 and
            official["exact_dvariant_count"] == 157,
            "manufacturer DFP source lock drift")
    observed = report["commercial_cohort"]
    require(observed["canonical_exact_set_sha256"] == prior.EXPECTED_SET_SHA and
            observed["exact_set_git_blob_sha"] == "9240f423ccca0ba7c43a6a0ac800be8cd86e3470" and
            observed["observed_public_estore_active_exact_mpns"] == 172 and
            observed["exact_pdsc_variant_matches"] == 139 and
            observed["parent_dname_only_missing_exact_dfp_variant"] == 33 and
            observed["dfp_and_estore_snapshot_not_atomic"] is True,
            "commercial exact-MPN observation incorrectly promoted or drifted")
    loaders = official["loader_files"]
    require(len(loaders) == 3 and
            {x["path"]: x["git_blob_sha"] for x in loaders} == EXPECTED_LOADERS and
            {x["dev_id"]: tuple(x["family"]) for x in loaders} == {
                "0x44F": ("C53", "C54"),
                "0x44E": ("C55", "C56"),
                "0x45A": ("C59", "C5A"),
            }, "loader source or family map drifted")
    fork = report["fork_vs_proposal"]
    require(fork["pinned_target_cfg_git_blob_sha"] == EXPECTED_FORK_CFG_BLOB and
            all(fork[key] is True for key in (
                "pinned_fork_defines_dev_id_loader_as_scalar_set",
                "pinned_fork_defines_die_max_flash_size_as_scalar_set",
                "pinned_fork_uses_array_index_lookup_for_both",
                "plasma_requires_local_content_locked_loader_no_runtime_network",
            )) and fork["upstream_patch_merge_and_runtime_qualification_unverified"] is True,
            "incomplete fork patch or remote loader wrongly promoted")
    gates = report["safety_gates"]
    require(gates["frozen_production_st_exact_icpns"] == 2683 and
            gates["frozen_production_st_families"] == 23 and
            gates["true_whole_st_coverage_percent"] is None and
            all(gates[key] is False for key in (
                "loader_sha256_retained_in_research_report",
                "independent_license_and_binary_distribution_signoff",
                "exact_metadata_review_for_33_complete",
                "compiled_plasma_openocd_stldr_qualified",
                "safe_local_loader_selection_qualified",
                "physical_hil_verified",
                "destructive_security_ops_authorized",
                "catalog_admission_ready",
                "production_write_authorized",
            )), "unqualified C5 evidence incorrectly admitted")

    rows = read_rows(CROSSWALK.read_text(encoding="utf-8"))
    require(len(rows) == len(names) == 172 and [r["icpn"] for r in rows] == names,
            "crosswalk must preserve exact frozen commercial identity set and sort")
    observed_groups = {}
    exact_count = 0
    for r in rows:
        series = r["series"]
        require(series == r["icpn"][5:8] and series in SERIES, "series/group drift")
        expected_dev_id, expected_loader = SERIES[series]
        require((r["candidate_dev_id"], r["candidate_xldr_path"]) ==
                (expected_dev_id, expected_loader), "non-official family loader selection")
        require(r["dfp_parent_dname"].startswith("STM32C5") and
                r["icpn"].startswith(r["dfp_parent_dname"]) and
                r["plasma_route_ready"] == "false",
                "no unique read-only structural parent or unsafe route readiness")
        require(r["dfp_loader_ram_start"] == "0x20000000" and
                int(r["dfp_loader_ram_bytes"]) > 0 and
                int(r["parent_flash_bytes"]) in (131072, 262144, 524288, 1048576),
                "unreviewed DFP memory candidate")
        group = observed_groups.setdefault(series, [0, 0, 0])
        group[0] += 1
        if r["dfp_evidence_state"] == "EXACT_DFP_VARIANT":
            require(r["exact_variant_flash_bytes"] == r["parent_flash_bytes"],
                    "wrong exact variant source flash candidate")
            exact_count += 1
            group[1] += 1
        else:
            require(r["dfp_evidence_state"] == "BASE_DEVICE_ONLY_NOT_EXACT" and
                    r["exact_variant_flash_bytes"] == "",
                    "base-only metadata must remain explicitly unqualified")
            group[2] += 1
    require(exact_count == 139 and len(rows) - exact_count == 33 and
            {k: tuple(v) for k, v in observed_groups.items()} == EXPECTED_GROUPS and
            report["commercial_cohort"]["group_counts"] == {
                k: dict(zip(("observed","exact_dfp_variant","base_only"), v))
                for k, v in observed_groups.items()
            }, "crosswalk source-population cohort drift")

    if pdsc is not None:
        derived, _, _ = build_from_pdsc(pdsc.read_bytes(), names)
        require(derived == rows, "DFP source reparse does not match frozen crosswalk")
    if loader_dir is not None:
        for relative, blob in EXPECTED_LOADERS.items():
            file = loader_dir / Path(relative).name
            raw = file.read_bytes()
            require(git_blob(raw) == blob, f"official pinned Xldr blob mismatch: {file}")
            require(len(raw) > 4096 and raw[:4] == b"\x7fELF" and
                    raw[4] == 1 and raw[5] == 1,
                    f"official Xldr not an expected ELF32 little-endian source: {file}")
            print(f"Xldr {file.name}: sha256={sha256(raw)} blob={blob}")
    if cfg_path is not None:
        raw = cfg_path.read_bytes()
        require(git_blob(raw) == EXPECTED_FORK_CFG_BLOB,
                "original official fork Tcl cfg provenance drift")
        cfg = raw.decode("utf-8")
        require("set dev_id_loader {\n}" in cfg and
                "set die_max_flash_size {\n" in cfg and
                "info exists dev_id_loader($dev_id)" in cfg and
                "info exists die_max_flash_size($dev_id)" in cfg,
                "original fork Tcl scalar/array mismatch no longer matches pinned evidence")
    if license_path is not None:
        raw = license_path.read_bytes()
        require(git_blob(raw) == EXPECTED_LICENSE_BLOB and
                b"BSD-3-Clause" in raw and b"STMicroelectronics" in raw,
                "pinned DFP license file provenance drift")
    return {
        "status":"PASS_RESEARCH_ONLY",
        "observed_c5_exact_active_cohort":len(rows),
        "official_DFP_exact_variant_observations":exact_count,
        "parent_only_not_exact":len(rows)-exact_count,
        "official_loader_source_files":len(EXPECTED_LOADERS),
        "raw_dfp_replayed":pdsc is not None,
        "raw_xldr_blobs_replayed":loader_dir is not None,
        "raw_fork_cfg_replayed":cfg_path is not None,
        "production_unchanged":2683,
        "catalog_admission_ready":False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdsc", type=Path)
    parser.add_argument("--loader-dir", type=Path)
    parser.add_argument("--fork-cfg", type=Path)
    parser.add_argument("--license", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.pdsc, args.loader_dir, args.fork_cfg, args.license),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

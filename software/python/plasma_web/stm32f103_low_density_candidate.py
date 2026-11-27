"""Source-locked STM32F103 low-density documentary qualification validation.

Shared by the existing provider registry and host-only evidence tests. This
validates qualification data; it never executes a programming operation.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .device_catalog import DeviceCatalogIntegrityError
from .runtime_evidence_root import default_runtime_evidence_root

ROOT = default_runtime_evidence_root()
SOURCE = "release/openocd-qualification/stm32f103-low-density-ds5936-source-lock-v1.json"
APP = "release/openocd-qualification/stm32f103-low-density-exact-12-applicability-v1.json"
QUAL = "release/openocd-qualification/openocd-0.12.0-stm32f103-low-density-12-v1.json"
V10 = "release/openocd-qualification/openocd-0.12.0-stm32f103-v10.json"
V9 = "release/openocd-qualification/openocd-0.12.0-stm32f103-v9.json"
CATALOG = "data/device-catalog/research/stm32f1-commercial-icpn.csv"
EXPECTED = frozenset({
    "STM32F103C4T6A", "STM32F103C6T6A", "STM32F103C6T6ATR",
    "STM32F103C6T7A", "STM32F103C6T7ATR", "STM32F103C6U6A",
    "STM32F103R4H6A", "STM32F103R4T6A", "STM32F103R6H6A",
    "STM32F103R6T6A", "STM32F103R6T6ATR", "STM32F103R6T7A",
})
EXCLUDED = frozenset({"STM32F103T4U6A", "STM32F103T6U6A", "STM32F103T6U7A"})
SIZES = {"C4": 16384, "C6": 32768, "R4": 16384, "R6": 32768}
OPERATIONS = frozenset(("probe", "erase", "program", "read", "verify"))


class LowDensityEvidenceError(DeviceCatalogIntegrityError):
    """Fail-closed pre-admission evidence error."""


def need(condition: bool, detail: str) -> None:
    if not condition:
        raise LowDensityEvidenceError(detail)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha1(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()


def load_snapshot(root: Path = ROOT) -> dict[str, Any]:
    with (root / CATALOG).open(encoding="utf-8", newline="") as f:
        catalog = {row["icpn"]: row for row in csv.DictReader(f)}
    return {
        "source": read_json(root / SOURCE),
        "app": read_json(root / APP),
        "qual": read_json(root / QUAL),
        "v10": read_json(root / V10),
        "v9": read_json(root / V9),
        "catalog": catalog,
        "program": read_json(root / "data/ic-support/profiles/programming/stm32f1-low-density-flash-v0.json"),
        "geometries": {
            base: read_json(root / f"data/ic-support/profiles/memory-geometry/stm32f103{base.lower()}-{size // 1024}k-v0.json")
            for base, size in SIZES.items()
        },
    }


def verify_snapshot(s: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """Validate precisely the reviewed cohort and its operation boundaries."""
    v, q, a, src = s["v10"], s["qual"], s["app"], s["source"]
    proof = src["evidence"]["official_datasheet"]
    need(proof["document_number"] == "DS5936"
         and proof["document_id"] == "DocID15060"
         and proof["revision"] == "7", "official datasheet identity mismatch")
    # Byte custody is a separate truthful attestation, not a universal L2 gate.
    need(proof["sha256"] is None and proof["byte_length"] is None
         and proof["original_bytes_attested"] is False,
         "unexpected source custody state; separate verified promotion required")
    need(src["status"] == "REVIEWED_DOCUMENTARY_EVIDENCE"
         and proof["byte_attestation_status"] == "NOT_ATTESTED"
         and proof["url"] == "https://www.st.com/resource/en/datasheet/stm32f103c6.pdf"
         and proof["documentary_review"]["status"] == "VERIFIED"
         and proof["documentary_review"]["original_bytes_required_for_l2"] is False
         and len(proof["documentary_review"]["sections"]) == 4,
         "manufacturer documentary review missing")
    pm = src["evidence"]["programming_manual"]
    need(pm["sha256"] == "2296c5d528f71ddc7502baa907a0d6a7473ad10f1c67e8b07bb046f291dd4a8a"
         and pm["source_lock_git_blob_sha1"] == git_blob_sha1(root / pm["source_lock"]),
         "manufacturer programming manual provenance drift")
    need(src["evidence"]["openocd"]["commit"] ==
         "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
         and src["evidence"]["openocd"]["device_id"] == "0x412",
         "OpenOCD source/device identity mismatch")

    old = v["predecessor_qualification"]
    need(old["path"] == V9 and old["git_blob_sha1"] == git_blob_sha1(root / V9)
         and old["supported_exact_icpn_count"] == 77
         and s["v9"]["supported_exact_icpn_count"] == 77,
         "existing 77 L2 manifest not retained")
    pending = v["pending_cohort"]
    need(pending["path"] == QUAL and pending["git_blob_sha1"] == git_blob_sha1(root / QUAL)
         and pending["candidate_exact_icpn_count"] == 12
         and pending["supported_exact_icpn_count"] == 12 and pending["blocked"] is False,
         "pending cohort integrity or support status mismatch")
    need(v["status"] == "reviewed_source_only"
         and v["supported_exact_icpn_count"] == 89
         and v["possible_supported_after_all_gates"] == 89
         and v["active_provider_registry_changed"] is True
         and v["production_catalog_changed"] is False
         and v["acceptance_boundary"]["l2_promotion_authorized"] is True,
         "v10 would silently promote unsupported silicon")
    need(q["status"] == "reviewed_source_only"
         and q["supported_exact_icpn_count"] == 12
         and q["candidate_exact_icpn_count"] == 12,
         "cohort qualification does not fail closed")
    need(q["provider"]["low_density_device_id"] == "0x412"
         and q["provider"]["version"] == "0.12.0"
         and q["provider"]["source_commit"] == src["evidence"]["openocd"]["commit"],
         "provider not pinned to low-density source")
    need(q["source_lock"]["path"] == SOURCE
         and q["source_lock"]["git_blob_sha1"] == git_blob_sha1(root / SOURCE),
         "official evidence source lock drift")
    need(q["applicability"]["path"] == APP
         and q["applicability"]["git_blob_sha1"] == git_blob_sha1(root / APP),
         "applicability lock drift")
    need(a["production_catalog"]["path"] == CATALOG
         and a["production_catalog"]["git_blob_sha1"] == git_blob_sha1(root / CATALOG),
         "canonical identity source changed")

    program = s["program"]
    pd = program["data"]
    need(program["status"] == "reviewed_source_only"
         and pd["expected_device_id"] == "0x412"
         and pd["page_size_bytes"] == 1024
         and pd["program_granularity_bytes"] == 2
         and pd["supported_flash_sizes_bytes"] == [16384, 32768]
         and pd["flash_size_read_fail_closed"] is True
         and pd["user_flash_size_override_as_authority"] is False
         and pd["prohibit_full_bank_erase_until_separately_approved"] is True,
         "programming profile misrepresents density or safety")
    need({"mass_erase", "option_write", "readout_unlock"}.issubset(
         set(pd["disallowed_operations"])), "unsafe operations not denied")
    program_lock = q["programming_profile"]
    need(program_lock["git_blob_sha1"] == git_blob_sha1(root / program_lock["path"])
         and program_lock["profile_id"] == program["profile_id"], "programming profile drift")

    by_app = {r["icpn"]: r for r in a["records"]}
    by_qual = {r["icpn"]: r for r in q["records"]}
    need(len(a["records"]) == len(q["records"]) == 12
         and set(by_app) == set(by_qual) == EXPECTED, "exact 12 candidate set mismatch")
    need(frozenset(a["excluded_exact_icpns"]) == EXCLUDED
         and frozenset(q["excluded_exact_icpns"]) == EXCLUDED
         and frozenset(v["excluded_exact_icpns"]) == EXCLUDED,
         "three conflicting VFQFPN36 variants not excluded")
    need(a["acceptance_boundary"]["supported_count"] == 12
         and a["acceptance_boundary"]["execution_authorized"] is False,
         "candidate applicability accidentally authorized")

    for base, size in SIZES.items():
        g = s["geometries"][base]
        d = g["data"]
        need(g["scope"]["base_device"] == "STM32F103" + base
             and g["status"] == "reviewed_source_only"
             and d["main_flash_start"] == "0x08000000"
             and d["main_flash_size_bytes"] == size
             and int(d["main_flash_end"], 16) == 0x08000000 + size - 1
             and d["page_size_bytes"] == 1024
             and d["page_count"] == size // 1024
             and d["program_granularity_bytes"] == 2,
             "low-density geometry invalid: " + base)

    group = q["manufacturer_programming_group"]
    need(group["density_class"] == "low"
         and group["silicon_identity"]["openocd_device_id"] == "0x412"
         and group["manufacturer_evidence"]["programming_profile_id"] == program["profile_id"]
         and group["shared_flash_geometry"] == {
             "main_flash_start": "0x08000000", "erase_unit": "page", "erase_unit_bytes": 1024,
             "program_unit": "halfword", "program_unit_bytes": 2}
         and set(group["operation_qualification"]) == OPERATIONS
         and all(x["state"] == "SUPPORTED" and x["openocd_basis"] and x["manufacturer_basis"]
                 for x in group["operation_qualification"].values())
         and group["operation_qualification"]["program"]["implicit_erase"] is False
         and {"MASS_ERASE", "FULL_BANK_ERASE", "OPTION_PROGRAM", "OPTION_ERASE",
              "RDP_ENABLE", "RDP_DISABLE", "WRITE_PROTECTION_CHANGE"}.issubset(group["blocked_operations"]),
         "low-density shared method or operation scope drift")
    for icpn, r in by_app.items():
        catalog = s["catalog"].get(icpn)
        need(catalog is not None and catalog["manufacturer"] == "STMicroelectronics"
             and catalog["icpn"] == icpn and catalog["base_device"] == r["base_device"]
             and catalog["package"] == r["package"]
             and int(catalog["pin_count"]) == r["pin_count"]
             and int(catalog["flash_size"].split()[0]) * 1024 == r["flash_size_bytes"],
             "exact Catalog identity or package mismatch: " + icpn)
        base = r["base_device"].removeprefix("STM32F103")
        need(base in SIZES and r["flash_size_bytes"] == SIZES[base],
             "incorrect exact base/flash match: " + icpn)
        g = s["geometries"][base]
        need(r["geometry_profile_id"] == g["profile_id"]
             and r["geometry_git_blob_sha1"] == git_blob_sha1(root / r["geometry_profile_path"]),
             "geometry blob mismatch: " + icpn)
        order = icpn.removesuffix("TR")
        package = {"T": "LQFP", "U": "UFQFPN", "H": "TFBGA"}.get(order[-3])
        pins = {"C": 48, "R": 64}.get(order[9])
        temp = {"6": "-40 to 85 C", "7": "-40 to 105 C"}.get(order[-2])
        need(r["package"] == package and r["pin_count"] == pins
             and r["temperature_grade"] == temp
             and r["manufacturer_internal_code"] == "A" and order[-1] == "A"
             and r["tape_and_reel"] == icpn.endswith("TR")
             and r["programming_profile_id"] == program["profile_id"],
             "DS5936 exact ordering applicability mismatch: " + icpn)
        if icpn.endswith("TR"):
            base_icpn = icpn[:-2]
            need(r["source_nontr_exact_icpn"] == base_icpn
                 and base_icpn in by_app
                 and by_app[base_icpn]["base_device"] == r["base_device"]
                 and by_app[base_icpn]["package"] == r["package"]
                 and by_app[base_icpn]["flash_size_bytes"] == r["flash_size_bytes"],
                 "TR may not inherit a different exact part: " + icpn)
        else:
            need(r["source_nontr_exact_icpn"] is None, "unexpected TR ancestry")
        if base.startswith("C"):
            need((r["package"], r["pin_count"]) in {("LQFP", 48), ("UFQFPN", 48)},
                 "C package unsupported")
        else:
            need((r["package"], r["pin_count"]) in {("LQFP", 64), ("TFBGA", 64)},
                 "R package unsupported")
        need(r["software_state"] == "SUPPORTED"
             and set(r["supported_operations"]) == OPERATIONS
             and set(r["requested_operations"]) == OPERATIONS
             and r["runtime_execution_authorized"] is False,
             "unsupported operation upgraded without evidence: " + icpn)
        qr = by_qual[icpn]
        need(qr["manufacturer"] == r["manufacturer"] == "STMicroelectronics"
             and qr["base_device"] == r["base_device"]
             and qr["programming_profile_id"] == program["profile_id"]
             and qr["memory_geometry_profile_id"] == r["geometry_profile_id"]
             and qr["main_flash_size_bytes"] == SIZES[base]
             and qr["page_count"] == SIZES[base] // 1024,
             "qualification exact geometry mismatch: " + icpn)
        need(qr["software_state"] == "SUPPORTED"
             and set(qr["operations"]) == OPERATIONS
             and all(v["state"] == "SUPPORTED"
                     and v["exact_icpn_qualified"] is True
                     for v in qr["operations"].values())
             and qr["qualification_blockers"] == r["blockers"] == [],
             "qual ledger falsely asserts SUPPORTED: " + icpn)

    return {"state": "SUPPORTED", "candidate_exact_icpns": 12,
            "supported_added": 12, "retained_existing_l2": 77,
            "excluded_exact_icpns": sorted(EXCLUDED),
            "source_byte_attestation": "NOT_ATTESTED"}


def audit_candidate(root: Path = ROOT) -> dict[str, Any]:
    try:
        return verify_snapshot(load_snapshot(root), root)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise LowDensityEvidenceError("low-density qualification evidence invalid: " + str(exc)) from exc

#!/usr/bin/env python3
"""STM32C5 source-only, fail-closed *non-executable* local-loader preflight v1.0.

No networking, process execution, physical target access, route registration,
catalog changes or device programming. "reported_" values are caller assertions
and are NOT authenticated hardware readback or HIL qualification.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import validate_st_c5_dfp_loader_crosswalk_v09 as v09

HERE = Path(__file__).resolve().parent
TRIAGE_CSV = HERE / "st-c5-dfp-33-exact-variant-triage-v1.0.csv"
TRIAGE_JSON = HERE / "st-c5-dfp-33-exact-variant-triage-v1.0.json"

REASONS = {
    "TR_WITH_PINNED_DFP_NONTR_EXACT_VARIANT",
    "TR_WITHOUT_PINNED_DFP_NONTR_EXACT_VARIANT",
    "NONTR_MPN_ABSENT_FROM_PINNED_DFP_VARIANTS",
}
# These nine identities are observations from the frozen official DFP v2.1.0,
# not a rule permitting suffix-stripping for admission/route qualification.
DFP_EXACT_NONTR_FOR_MISSING_TR = frozenset({
    "STM32C531FBU6TR", "STM32C531FCU6TR",
    "STM32C532FBU6TR", "STM32C532FCU6TR",
    "STM32C542FCU6TR", "STM32C551CCT6TR",
    "STM32C551CEU6TR", "STM32C591CGU6TR", "STM32C591RET6TR",
})
EXACT = re.compile(r"STM32C5[A-Z0-9]{5,20}\Z")
DEV_ID = re.compile(r"0x[0-9A-F]{3}\Z")


def require(condition: bool, why: str) -> None:
    if not condition:
        raise ValueError(why)


def stable_result(status: str, icpn: str, note: str) -> dict:
    return {
        "schema_version": 1,
        "decision": status,
        "exact_icpn": icpn,
        "reason": note,
        "plan_only": True,
        "executable": False,
        "hardware_readback_authenticated": False,
        "hardware_runtime_ready": False,
        "catalog_admission_ready": False,
        "production_write_authorized": False,
        "security_mutation_authorized": False,
    }


def load_and_reconcile() -> dict[str, dict[str, str]]:
    base = v09.validate()
    require(base["observed_c5_exact_active_cohort"] == 172 and
            base["official_DFP_exact_variant_observations"] == 139 and
            base["parent_only_not_exact"] == 33 and
            base["production_unchanged"] == 2683,
            "unexpected v0.9 frozen evidence state")
    with v09.CROSSWALK.open(newline="", encoding="utf-8") as src:
        rows = list(csv.DictReader(src))
    candidates = {row["icpn"]: row for row in rows}
    require(len(rows) == len(candidates) == 172, "duplicate or missing C5 candidate")
    absent = {name: row for name, row in candidates.items()
              if row["dfp_evidence_state"] == "BASE_DEVICE_ONLY_NOT_EXACT"}
    require(len(absent) == 33, "expected exact DFP gap cohort changed")
    with TRIAGE_CSV.open(newline="", encoding="utf-8") as src:
        triage = list(csv.DictReader(src))
    require(len(triage) == len(absent) == 33 and
            [r["exact_icpn"] for r in triage] == sorted(absent),
            "triage exact part population differs from v0.9")
    report = json.loads(TRIAGE_JSON.read_text(encoding="utf-8"))
    require(report["audit_id"] == "st-c5-dfp-33-commercial-exact-variant-triage-v1.0" and
            report["source_lock"]["eStore_exact_set_sha256"] == v09.prior.EXPECTED_SET_SHA and
            report["source_lock"]["dfp_commit"] ==
                "a5f65bc64535cfa723e9d25f58d7ce23d0937aed" and
            report["source_lock"]["dfp_pdsc_git_blob_sha"] == v09.EXPECTED_DFP_BLOB and
            report["population"]["eStore_observed_active_exact"] == 172 and
            report["population"]["dfp_exact_match"] == 139 and
            report["population"]["dfp_exact_missing"] == 33,
            "triage source lock/count drift")
    groups = dict.fromkeys(REASONS, 0)
    for line in triage:
        icpn = line["exact_icpn"]
        require(icpn in absent and EXACT.fullmatch(icpn),
                "unknown or wildcard exact commercial identity")
        origin = absent[icpn]
        require(line["series"] == origin["series"] and
                line["dfp_parent_dname"] == origin["dfp_parent_dname"] and
                line["manufacturer_commercial_evidence"] ==
                    "v0.7_eStore_Active_exact" and
                line["exact_variant_metadata_verified"] == "false" and
                line["backend_route_ready"] == "false",
                "unverified exact commercial source promoted or altered")
        if icpn.endswith("TR"):
            if icpn in DFP_EXACT_NONTR_FOR_MISSING_TR:
                kind = "TR_WITH_PINNED_DFP_NONTR_EXACT_VARIANT"
                require(line["dfp_exact_nontr_counterpart"] == icpn[:-2],
                        "specific official DFP nonTR source mismatch")
            else:
                kind = "TR_WITHOUT_PINNED_DFP_NONTR_EXACT_VARIANT"
                require(line["dfp_exact_nontr_counterpart"] == "",
                        "unverified packaging counterpart inferred")
        else:
            kind = "NONTR_MPN_ABSENT_FROM_PINNED_DFP_VARIANTS"
            require(line["dfp_exact_nontr_counterpart"] == "",
                    "non-TR retail part cannot have TR-derived counterpart")
        require(line["dfp_absence_class"] == kind,
                "triage classification was not derived from pinned evidence")
        groups[kind] += 1
    require(groups == {
        "TR_WITH_PINNED_DFP_NONTR_EXACT_VARIANT": 9,
        "TR_WITHOUT_PINNED_DFP_NONTR_EXACT_VARIANT": 11,
        "NONTR_MPN_ABSENT_FROM_PINNED_DFP_VARIANTS": 13,
    } and report["population"]["classes"] == groups,
            "33-part missing exact variant disposition drift")
    require(report["gates"]["per_exact_mpn_missing_metadata_resolved"] == 0 and
            report["gates"]["production_ST_total"] == 2683 and
            report["gates"]["production_write_authorized"] is False and
            report["gates"]["backend_route_ready"] is False and
            report["gates"]["hardware_hil_verified"] is False and
            report["evidence_limitations"]["source_snapshots_not_atomic"] is True,
            "unreviewed C5 missing metadata unexpectedly admitted")
    return candidates


def local_loader_sha256(root: Path, expected_filename: str,
                        expected_digest: str) -> tuple[bool, str]:
    # The caller supplies an explicit local staging directory. The tool never
    # downloads source files, resolves URLs or assembles executable commands.
    if not isinstance(root, Path) or root.is_symlink() or not root.is_dir():
        return False, "missing/unsafe local-only loader staging directory"
    if re.fullmatch(r"STM32C5\[(?:34|56|9A)\]x\.xldr", expected_filename) is None:
        return False, "unreviewed loader filename"
    file = root / expected_filename
    if file.is_symlink() or not file.is_file():
        return False, "expected pinned local loader is absent or symlinked"
    try:
        if file.resolve(strict=True).parent != root.resolve(strict=True):
            return False, "resolved loader path escapes the staging directory"
        size = file.stat().st_size
        if not 4096 < size < 1024 * 1024:
            return False, "unexpected local loader byte length"
        data = file.read_bytes()
    except OSError:
        return False, "local loader cannot be read"
    if data[:6] != b"\x7fELF\x01\x01":
        return False, "local loader not ELF32 little-endian"
    if hashlib.sha256(data).hexdigest() != expected_digest:
        return False, "pinned manufacturer loader SHA256 mismatch"
    return True, "source-locked local loader bytes match"


def preflight(icpn: str, reported_dev_id: str | None = None,
              reported_flash_bytes: int | None = None,
              loader_dir: Path | None = None) -> dict:
    if not isinstance(icpn, str) or EXACT.fullmatch(icpn) is None:
        return stable_result("BLOCKED_NONEXACT_ICPN", str(icpn), "Exact C5 MPN required")
    candidates = load_and_reconcile()
    row = candidates.get(icpn)
    if row is None:
        return stable_result("BLOCKED_NOT_IN_FROZEN_C5_COHORT", icpn,
                             "No research basis for guessed commercial identities")
    if row["dfp_evidence_state"] != "EXACT_DFP_VARIANT":
        return stable_result("BLOCKED_NO_EXACT_DFP_VARIANT", icpn,
                             "One Base Device match does not qualify exact metadata")
    if reported_dev_id is None:
        return stable_result("BLOCKED_DEVICE_ID_READBACK_REQUIRED", icpn,
                             "Source crosswalk does not substitute for device ID readback")
    if not isinstance(reported_dev_id, str) or DEV_ID.fullmatch(reported_dev_id) is None:
        return stable_result("BLOCKED_NONCANONICAL_DEVICE_ID", icpn,
                             "No coercion of untrusted DEV_ID strings")
    if reported_dev_id != row["candidate_dev_id"]:
        return stable_result("BLOCKED_DEVICE_ID_MISMATCH", icpn,
                             "Reported DEV_ID is inconsistent with source-locked candidate")
    if type(reported_flash_bytes) is not int or reported_flash_bytes <= 0:
        return stable_result("BLOCKED_FLASH_READBACK_REQUIRED", icpn,
                             "An independently obtained integer flash-size observation is required")
    if reported_flash_bytes != int(row["exact_variant_flash_bytes"]):
        return stable_result("BLOCKED_FLASH_GEOMETRY_MISMATCH", icpn,
                             "Do not use source fallback for mismatched observed geometry")
    relative = row["candidate_xldr_path"]
    expected_sha = v09.EXPECTED_LOADER_SHA256.get(relative)
    if expected_sha is None or relative not in v09.EXPECTED_LOADERS:
        return stable_result("BLOCKED_UNREGISTERED_VENDOR_LOADER", icpn,
                             "No fixed-commit official DFP loader evidence")
    if loader_dir is None:
        return stable_result("BLOCKED_STAGED_LOCAL_LOADER_REQUIRED", icpn,
                             "Production cannot fetch an upstream loader at runtime")
    ok, reason = local_loader_sha256(loader_dir, Path(relative).name, expected_sha)
    if not ok:
        return stable_result("BLOCKED_LOCAL_LOADER_PROVENANCE", icpn, reason)
    result = stable_result("SOURCE_MATCHED_RESEARCH_ONLY", icpn,
                           "Caller-asserted DEV_ID/geometry matches pinned exact DFP; local loader bytes verified")
    result["loader_filename"] = Path(relative).name
    result["loader_sha256"] = expected_sha
    result["candidate_dev_id"] = row["candidate_dev_id"]
    result["candidate_flash_bytes"] = int(row["exact_variant_flash_bytes"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icpn", help="Exact manufacturer commercial part")
    parser.add_argument("--reported-dev-id", help="Caller-provided DEV_ID, e.g. 0x44F")
    parser.add_argument("--reported-flash-bytes", type=int)
    parser.add_argument("--loader-dir", type=Path,
                        help="A deliberately locally staged directory, no download")
    args = parser.parse_args()
    if args.icpn is None:
        candidates = load_and_reconcile()
        status = {
            "status": "RESEARCH_GATE_VALID",
            "total": len(candidates),
            "exact_dfp_variant": sum(
                x["dfp_evidence_state"] == "EXACT_DFP_VARIANT"
                for x in candidates.values()
            ),
            "dfp_parent_only_blocked": sum(
                x["dfp_evidence_state"] == "BASE_DEVICE_ONLY_NOT_EXACT"
                for x in candidates.values()
            ),
            "all_production_routes_still_closed": True,
            "frozen_ST_production": 2683,
        }
    else:
        status = preflight(args.icpn, args.reported_dev_id,
                           args.reported_flash_bytes, args.loader_dir)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if status.get("status") == "RESEARCH_GATE_VALID" else (
        0 if status.get("decision") == "SOURCE_MATCHED_RESEARCH_ONLY" else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())

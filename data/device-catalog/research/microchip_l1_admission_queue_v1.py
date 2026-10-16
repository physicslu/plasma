#!/usr/bin/env python3
"""Prepare a fail-closed Microchip 2,563-row L1 admission REVIEW ledger.

Consume only original-byte-replayed Research reports and the pinned OpenOCD
source lock. This prepares independent identity/route review; it NEVER produces
Production rows, executable mappings, or an actual Catalog Level promotion.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
EXPECTED_CFG = {
    "tcl/target/pic32mx.cfg": 1241,
    "tcl/target/at91samdXX.cfg": 667,
    "tcl/target/atsame5x.cfg": 354,
    "tcl/target/atsamv.cfg": 175,
    "tcl/target/atsaml1x.cfg": 126,
}
EXPECTED_STATES = {
    "EXACT_DFP_NAME_CFG_CANDIDATE": 2414,
    "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE": 23,
    "P1_TARGET_ONLY_CFG_CANDIDATE": 126,
    "NO_DFP_NAME_CFG_CROSSWALK": 20713,
}
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ICPN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._/\-]{1,95}\Z")


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(f"Microchip L1 review ledger: {why}")


def build(report: dict, lock: dict, *, report_sha256: str) -> dict:
    require(SHA256.fullmatch(report_sha256) is not None, "invalid report digest")
    replay = report.get("full_batch_original_source_replay")
    require(report.get("manufacturer") == "Microchip"
            and report.get("openocd_release") == "0.12.0"
            and report.get("openocd_source_commit") == lock.get("provider", {}).get("commit")
            and report.get("original_dfp_index_sha256_required")
                == "9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0"
            and report.get("all_icpn_original_bytes_replayed_in_this_command") is True
            and report.get("original_dfp_observation_available_in_this_run") is True,
            "missing original manufacturer source replay / source authority")
    require(isinstance(replay, dict)
            and replay.get("source_replay_status") == "REPLAYED_AGAINST_PINNED_ORIGINAL_BYTES"
            and replay.get("original_source_count") == 13
            and replay.get("original_batch_archives_replayed") == 313
            and replay.get("quarantined_batch_archives_not_admitted") == 8,
            "source replay cohort must be independently attested")
    require(report.get("production_write_authorized") is False
            and report.get("cfg_software_supported_claimed") is False
            and report.get("base_device_from_suffix_inference") is False,
            "research report crossed the production/support boundary")
    require(report.get("icpn_denominator_joined_in_this_run") == 23276
            and report.get("exact_icpn_cfg_candidate_count") == 2563
            and report.get("icpn_by_cfg_candidate_counts") == EXPECTED_CFG
            and report.get("icpn_mapping_state_counts") == EXPECTED_STATES,
            "frozen five-CFG Research cohort drift")
    require(lock.get("provider", {}).get("version") == "0.12.0"
            and lock.get("provider", {}).get("commit")
                == "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c",
            "OpenOCD provider source not locked")
    groups = {}
    for lead in lock.get("p0_research_leads", []):
        require(lead["target"] not in groups, "duplicate source CFG")
        require(lead.get("priority") == "P0_SOURCE_BACKED"
                and SHA1.fullmatch(lead.get("target_sha", "")) is not None
                and SHA1.fullmatch(lead.get("driver_sha", "")) is not None
                and lead.get("driver_source", "").startswith("src/flash/nor/"),
                "P0 source lacks versioned flash driver path")
        groups[lead["target"]] = lead
    for lead in lock.get("p1_bounded_leads", []):
        require(lead["target"] not in groups, "duplicate source CFG")
        require(SHA1.fullmatch(lead.get("target_sha", "")) is not None
                and not lead.get("driver_source"),
                "target-only route has unreviewed driver")
        groups[lead["target"]] = lead
    source_cfg = {g["openocd_target_cfg"]: g for g in report["cfg_group_rows"]}
    require(set(EXPECTED_CFG).issubset(groups) and set(EXPECTED_CFG).issubset(source_cfg),
            "Research CFG source lock incomplete")
    for cfg in EXPECTED_CFG:
        require(source_cfg[cfg]["openocd_target_git_blob_sha1"] == groups[cfg]["target_sha"],
                f"CFG blob mismatch: {cfg}")

    all_rows = report.get("icpn_rows")
    require(isinstance(all_rows, list) and len(all_rows) == 23276,
            "original commercial identity denominator drift")
    seen = set()
    candidates = []
    counts = Counter()
    states = Counter()
    for row in all_rows:
        icpn = row.get("icpn")
        require(isinstance(icpn, str) and ICPN.fullmatch(icpn) is not None,
                "invalid commercial ICPN from original manufacturer")
        key = icpn.casefold()
        require(key not in seen, f"duplicate manufacturer exact ICPN: {icpn}")
        seen.add(key)
        state = row.get("mapping_state")
        states[state] += 1
        cfg = row.get("openocd_target_cfg")
        if cfg is None:
            require(state == "NO_DFP_NAME_CFG_CROSSWALK",
                    "unmapped row has inconsistent research state")
            continue
        require(cfg in EXPECTED_CFG, "unreviewed target CFG inserted")
        require(state in EXPECTED_STATES and state != "NO_DFP_NAME_CFG_CROSSWALK",
                "mapped row has invalid source-backed classification")
        require(isinstance(row.get("base_device"), str) and row["base_device"]
                and isinstance(row.get("dfp_device_name"), str) and row["dfp_device_name"],
                "missing manufacturer base/DFP identity crosswalk")
        refs = row.get("original_mcp_response_sha256_refs")
        require(isinstance(refs, list) and bool(refs)
                and all(isinstance(x, str) and SHA256.fullmatch(x) for x in refs)
                and len(set(refs)) == len(refs),
                "missing, malformed, or duplicate manufacturer source digests")
        require(row.get("manufacturer_base_identity_evidence")
                == "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND"
                and row.get("cfg_applicability_reviewed") is False
                and row.get("software_supported_claimed") is False
                and row.get("production_write_authorized") is False,
                "source report fabricated product qualification")
        lead = groups[cfg]
        is_target_only = cfg == "tcl/target/atsaml1x.cfg"
        require(is_target_only == (state == "P1_TARGET_ONLY_CFG_CANDIDATE"),
                "target-only route misclassified")
        counts[cfg] += 1
        candidates.append({
            "manufacturer": "Microchip",
            "exact_icpn": icpn,
            "base_device": row["base_device"],
            "dfp_device_name": row["dfp_device_name"],
            "identity_original_response_sha256_refs": refs,
            "identity_replay_status": "SOURCE_REPLAYED_PENDING_CANONICAL_ADMISSION",
            "openocd_version": lock["provider"]["version"],
            "openocd_source_commit": lock["provider"]["commit"],
            "target_config": cfg,
            "target_config_git_blob_sha1": lead["target_sha"],
            "flash_driver_source": lead.get("driver_source"),
            "flash_driver_git_blob_sha1": lead.get("driver_sha"),
            "research_mapping_state": state,
            "programming_route_review": (
                "PROGRAMMING_PATH_UNPROVEN_TARGET_ONLY" if is_target_only
                else "STATIC_DRIVER_ROUTE_APPLICABILITY_REVIEW_REQUIRED"),
            "canonical_admission": "PENDING",
            "catalog_level": None,
            "job_selectable": False,
            "execution_authorized": False,
        })
    require(dict(counts) == EXPECTED_CFG and dict(states) == EXPECTED_STATES
            and len(candidates) == 2563, "five-CFG per-ICPN reconciliation failed")
    candidates.sort(key=lambda x: x["exact_icpn"].casefold())
    return {
        "schema_version": 1,
        "scope": "microchip_original_source_replayed_l1_admission_review_queue",
        "source_report_sha256": report_sha256,
        "provider_source_commit": lock["provider"]["commit"],
        "research_source_icpns": 23276,
        "research_cfg_candidates": 2563,
        "by_cfg": dict(sorted(counts.items())),
        "identity_canonical_admitted_by_this_tool": 0,
        "route_canonical_admitted_by_this_tool": 0,
        "production_write_authorized": False,
        "execution_authorized": False,
        "rows": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-lock", type=Path,
                        default=HERE / "microchip-openocd-first-source-lock-v1.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require("production" not in {part.lower() for part in args.output.resolve().parts},
            "never write Research queue into Production")
    raw = args.report.read_bytes()
    result = build(json.loads(raw), json.loads(args.source_lock.read_text(encoding="utf-8")),
                   report_sha256=hashlib.sha256(raw).hexdigest())
    encoded = (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    if args.verify:
        require(args.output.read_bytes() == encoded, "non-deterministic review queue")
    else:
        require(not args.output.exists(), "refuse overwrite of existing review queue")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    print(json.dumps({"rows": len(result["rows"]), "counts": result["by_cfg"],
                      "admitted": result["route_canonical_admitted_by_this_tool"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import qualify_openocd_tier_a_identifiers_v65 as v65
import propose_openocd_tier_a_bounded_suffix_v613 as v613

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
C0_BRIDGE = HERE / "openocd-c0-bounded-identifier-bridge-v6.12.json"

EXPECTED_PRODUCTION_TOTAL = 4629
EXPECTED_SOURCE_COUNT = 28
EXPECTED_MAPPED_BEFORE = 3673
EXPECTED_NO_MAPPING_BEFORE = 956
EXPECTED_PROMOTION_COUNT = 364
EXPECTED_MAPPED_AFTER = 4037
EXPECTED_NO_MAPPING_AFTER = 592

EXPECTED_FAMILY_PROMOTIONS = {
    "STM32C0": 12,
    "STM32F2": 72,
    "STM32F3": 168,
    "STM32F4": 3,
    "STM32F7": 62,
    "STM32G0": 30,
    "STM32H7": 14,
    "STM32L1": 1,
    "STM32L4": 1,
    "STM32U3": 1,
}
EXPECTED_IDENTIFIER_KINDS = {
    "cmsis_device_name": 13,
    "ordering_pattern": 351,
}

DELTA_FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "authority","before_mapping_status","after_mapping_status",
    "after_existing_identifier","after_existing_identifier_kind",
    "after_cmsis_device_name","after_openocd_target_config",
    "programming_profile_state","programming_verified",
    "engineering_verified","hil_verified","production_write_authorized",
)

class ProposalError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ProposalError(msg)

def read_rows(path: Path) -> tuple[list[str], list[dict[str,str]]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)

def render(fields: list[str], rows: list[dict[str,str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

def build_bindings() -> dict[str,dict[str,str]]:
    qualified, blocked, _, _, summary65 = v65.build()
    req(summary65["identifier_qualified_exact_count"] == 320, "v6.5 qualified count drift")
    req(len(blocked) == 69, "v6.5 blocked count drift")

    bindings: dict[str,dict[str,str]] = {}
    for row in qualified:
        icpn = row["icpn"]
        bindings[icpn] = {
            "authority": "v6.5_identifier_qualification",
            "family": row["family"],
            "existing_identifier": row["resolved_existing_identifier"],
            "existing_identifier_kind": row["resolved_existing_identifier_kind"],
            "openocd_target_config": row["candidate_openocd_target_config"],
        }

    policy613 = v613.build()
    req(policy613["scope"]["exact_icpn_count"] == 33, "v6.13 exact scope drift")
    suffix_set = set(policy613["scope"]["exact_icpns"])
    req(not (set(bindings) & suffix_set), "v6.13 overlaps v6.5 exact set")
    for icpn, row in policy613["bridges"].items():
        bindings[icpn] = {
            "authority": "v6.13_bounded_suffix_normalization",
            "family": row["family"],
            "existing_identifier": row["existing_identifier"],
            "existing_identifier_kind": row["existing_identifier_kind"],
            "openocd_target_config": row["openocd_target_config"],
        }

    c0 = json.loads(C0_BRIDGE.read_text(encoding="utf-8"))
    req(c0["scope"]["exact_icpn_count"] == 11, "v6.12 exact scope drift")
    c0_set = set(c0["scope"]["exact_icpns"])
    req(not (set(bindings) & c0_set), "v6.12 overlaps v6.5/v6.13 exact set")
    for icpn, identifier in c0["bridges"].items():
        bindings[icpn] = {
            "authority": "v6.12_c0_bounded_identifier_bridge",
            "family": "STM32C0",
            "existing_identifier": identifier,
            "existing_identifier_kind": c0["identifier_kind"],
            "openocd_target_config": c0["openocd_target_config"],
        }

    req(len(bindings) == EXPECTED_PROMOTION_COUNT,
        f"consolidated exact count drift: {len(bindings)}")
    req(dict(sorted(Counter(v["family"] for v in bindings.values()).items()))
        == EXPECTED_FAMILY_PROMOTIONS, "family promotion partition drift")
    req(dict(sorted(Counter(v["existing_identifier_kind"] for v in bindings.values()).items()))
        == EXPECTED_IDENTIFIER_KINDS, "identifier-kind partition drift")
    return bindings

def build() -> tuple[list[dict[str,str]],dict[str,str],dict[str,Any]]:
    bindings = build_bindings()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    req(len(sources) == EXPECTED_SOURCE_COUNT, "Production source count drift")
    req(sum(int(s["row_count"]) for s in sources) == EXPECTED_PRODUCTION_TOTAL,
        "Production exact total drift")

    proposed_files: dict[str,str] = {}
    deltas: list[dict[str,str]] = []
    mapped_before = no_mapping_before = 0
    mapped_after = no_mapping_after = 0
    seen: set[str] = set()

    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        fields, rows = read_rows(path)
        req(len(rows) == int(source["row_count"]), f"{source['family']}: row-count drift")
        changed = 0
        proposed: list[dict[str,str]] = []

        for original in rows:
            row = dict(original)
            if row["mapping_status"] == "no_mapping":
                no_mapping_before += 1
            else:
                mapped_before += 1

            binding = bindings.get(row["icpn"])
            if binding is not None:
                icpn = row["icpn"]
                req(icpn not in seen, f"{icpn}: duplicate Production identity")
                seen.add(icpn)
                req(row["family"] == binding["family"], f"{icpn}: family mismatch")
                req(row["mapping_status"] == "no_mapping", f"{icpn}: prestate is no longer no_mapping")
                req(row.get("existing_identifier","") == "", f"{icpn}: prestate identifier is not empty")
                req(row.get("existing_identifier_kind","") == "", f"{icpn}: prestate identifier kind is not empty")
                req(row.get("openocd_target_config","") == "", f"{icpn}: prestate target config is not empty")
                req(row.get("cmsis_device_name","") == "", f"{icpn}: prestate CMSIS name is not empty")

                kind = binding["existing_identifier_kind"]
                identifier = binding["existing_identifier"]
                target = binding["openocd_target_config"]
                req(kind in {"ordering_pattern","cmsis_device_name"}, f"{icpn}: unsupported identifier kind")
                req(identifier != "" and target != "", f"{icpn}: incomplete route binding")

                row["existing_identifier"] = identifier
                row["existing_identifier_kind"] = kind
                row["mapping_status"] = (
                    "deterministic_cmsis_device_name"
                    if kind == "cmsis_device_name"
                    else "deterministic_ordering_pattern"
                )
                row["openocd_target_config"] = target
                row["cmsis_device_name"] = identifier if kind == "cmsis_device_name" else ""
                changed += 1

                deltas.append({
                    "manufacturer": row["manufacturer"],
                    "icpn": icpn,
                    "family": row["family"],
                    "series": row["series"],
                    "base_device": row["base_device"],
                    "authority": binding["authority"],
                    "before_mapping_status": "no_mapping",
                    "after_mapping_status": row["mapping_status"],
                    "after_existing_identifier": identifier,
                    "after_existing_identifier_kind": kind,
                    "after_cmsis_device_name": row["cmsis_device_name"],
                    "after_openocd_target_config": target,
                    "programming_profile_state": "unresolved",
                    "programming_verified": "false",
                    "engineering_verified": "false",
                    "hil_verified": "false",
                    "production_write_authorized": "false",
                })

            if row["mapping_status"] == "no_mapping":
                no_mapping_after += 1
            else:
                mapped_after += 1
            proposed.append(row)

        expected = EXPECTED_FAMILY_PROMOTIONS.get(source["family"], 0)
        req(changed == expected, f"{source['family']}: expected {expected} promotions, got {changed}")
        if changed:
            proposed_files[source["family"]] = render(fields, proposed)

    req(seen == set(bindings), "not all consolidated bindings were found in Production")
    req(len(deltas) == EXPECTED_PROMOTION_COUNT, "promotion delta cardinality drift")
    req((mapped_before, no_mapping_before) == (EXPECTED_MAPPED_BEFORE, EXPECTED_NO_MAPPING_BEFORE),
        f"Production prestate drift: mapped={mapped_before} no_mapping={no_mapping_before}")
    req((mapped_after, no_mapping_after) == (EXPECTED_MAPPED_AFTER, EXPECTED_NO_MAPPING_AFTER),
        f"proposed poststate drift: mapped={mapped_after} no_mapping={no_mapping_after}")

    deltas.sort(key=lambda r: r["icpn"])
    delta_csv = render(list(DELTA_FIELDS), deltas)
    exact_set_sha = hashlib.sha256(
        ("\n".join(r["icpn"] for r in deltas) + "\n").encode()
    ).hexdigest()
    binding_sha = hashlib.sha256(
        ("\n".join(
            "|".join((
                r["icpn"], r["authority"], r["after_existing_identifier_kind"],
                r["after_existing_identifier"], r["after_openocd_target_config"],
            ))
            for r in deltas
        ) + "\n").encode()
    ).hexdigest()

    proposed_file_bindings = {}
    for family, text in sorted(proposed_files.items()):
        raw = text.encode()
        proposed_file_bindings[family] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob_sha": hashlib.sha1(
                f"blob {len(raw)}\0".encode("ascii") + raw,
                usedforsecurity=False,
            ).hexdigest(),
        }

    summary = {
        "schema_version": 1,
        "proposal_id": "openocd-consolidated-backend-promotion-v6.14",
        "record_state": "RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized": False,
        "promotion_exact_count": EXPECTED_PROMOTION_COUNT,
        "promotion_exact_set_sha256": exact_set_sha,
        "promotion_binding_sha256": binding_sha,
        "promotion_delta_csv_sha256": hashlib.sha256(delta_csv.encode()).hexdigest(),
        "authority_counts": dict(sorted(Counter(r["authority"] for r in deltas).items())),
        "family_promotion_counts": dict(sorted(Counter(r["family"] for r in deltas).items())),
        "identifier_kind_counts": dict(sorted(Counter(r["after_existing_identifier_kind"] for r in deltas).items())),
        "affected_family_source_bindings_after_if_approved": proposed_file_bindings,
        "production_exact_total_before": EXPECTED_PRODUCTION_TOTAL,
        "production_exact_total_after_if_approved": EXPECTED_PRODUCTION_TOTAL,
        "production_source_count_before": EXPECTED_SOURCE_COUNT,
        "production_source_count_after_if_approved": EXPECTED_SOURCE_COUNT,
        "catalog_backend_partition_before": {
            "mapped": EXPECTED_MAPPED_BEFORE,
            "no_mapping": EXPECTED_NO_MAPPING_BEFORE,
        },
        "catalog_backend_partition_after_if_approved": {
            "mapped": EXPECTED_MAPPED_AFTER,
            "no_mapping": EXPECTED_NO_MAPPING_AFTER,
        },
        "active_openocd_route_before": 3594,
        "active_openocd_route_after_if_approved": 3958,
        "scoped_active_denominator": 4550,
        "active_openocd_route_coverage_after_if_approved_percent": 86.9890,
        "active_openocd_route_gap_after_if_approved": 592,
        "programming_profile_state_for_promotions": "unresolved",
        "route_evidence_validation_status": "not_verified",
        "claims": {
            "programming_verified": False,
            "engineering_verified": False,
            "hil_verified": False,
            "erase_program_verify_success_claimed": False,
            "production_write_authorized": False,
        },
    }
    return deltas, proposed_files, summary

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delta", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--patched-dir", type=Path)
    args = parser.parse_args()

    deltas, files, summary = build()
    delta_csv = render(list(DELTA_FIELDS), deltas)
    if args.delta:
        args.delta.write_text(delta_csv, encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.patched_dir:
        args.patched_dir.mkdir(parents=True, exist_ok=True)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        by_family = {s["family"]: Path(s["path"]).name for s in manifest["sources"]}
        for family, text in files.items():
            (args.patched_dir / by_family[family]).write_text(text, encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    print("OPENOCD_CONSOLIDATED_BACKEND_PROMOTION_V614_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

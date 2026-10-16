#!/usr/bin/env python3
"""Prove PIC32MX L1 applicability through the canonical Registry, OFFLINE ONLY.

A simulated admitted-identity catalog is built from source-replayed manufacturer
order codes, NOT the PLASMA Production Manifest. This verifies that exactly
893 PIC32MX rows with pinned OpenOCD driver DEVIDs would qualify for L1
subject to separate actual canonical identity/Production admission.
No real Catalog rows, Job routes, flash operation or execution authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from microchip_pic32mx_devid_route_review_v1 import build as replay_pic32mx_devid
from plasma_web.catalog_promotion_framework import (
    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
    EVIDENCE_BACKEND_CANDIDATE_ROUTE,
    CatalogPromotionFramework,
)
from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogRecord
from plasma_web.programming_qualification import ProgrammingQualificationRegistry
from plasma_web.route_evidence_admission import AdmittedRouteCandidateRegistry, RouteEvidence


def require(valid: bool, reason: str) -> None:
    if not valid:
        raise ValueError("PIC32MX L1 dry run: " + reason)


def run(ledger: dict, driver_source: bytes, *, prior_review: dict | None = None) -> dict:
    # Verify *every* input source and DEVID mapping against the frozen upstream
    # source rather than trusting Research's prior result or editable verdicts.
    review = replay_pic32mx_devid(ledger, driver_source)
    if prior_review is not None:
        require(prior_review == review, "upstream DEVID review ledger tampered")
    catalog_rows: list[DeviceCatalogRecord] = []
    evidence: list[RouteEvidence] = []
    counts = Counter()
    seen: set[str] = set()
    for item in review["rows"]:
        icpn = item["exact_icpn"]
        key = icpn.casefold()
        require(key not in seen, "duplicate exact manufacturer order code")
        seen.add(key)
        base = item["base_device"]
        refs = item["original_mcp_response_sha256_refs"]
        require(len(refs) > 0, f"missing source original response for {icpn}")
        original_ref = (
            f"Microchip MCP exact partNumber={icpn} basePartNumber={base} "
            f"original_response_sha256={refs[0]}; "
            f"original_replay_source_report_sha256={ledger['source_report_sha256']}"
        )
        catalog_rows.append(DeviceCatalogRecord(
            vendor="Microchip", family="PIC32MX", subfamily="PIC32MX",
            plasma_series="PIC32MX", identifier=icpn,
            identifier_kind="manufacturer_part_number", cpu_architectures=(),
            target_config="", openocd_distribution="",
            mapping_status="no_mapping", validation_status="no_evidence",
            catalog_origin="UNPUBLISHED_SIMULATED_IDENTITIES",
            base_device=base, source_type="original_microchip_mcp_replay",
            source_reference=original_ref,
            source_authority="Microchip Technology official (original archive)",
            verification_status="verified_original_manufacturer_replay_simulation",
            production_admitted=True,  # in-memory fixture ONLY, NEVER product
        ))
        disposition = item["route_evidence_review"]
        counts[disposition] += 1
        if disposition == "DIRECT_DRIVER_DEVID_ROUTE_EVIDENCE":
            devid = item["flash_driver_devid"]
            require(bool(devid), f"direct evidence missing exact device ID: {icpn}")
            evidence.append(RouteEvidence(
                manufacturer="Microchip", exact_icpn=icpn, base_device=base,
                identity_source="https://api.microchip.com/mcp/resources",
                identity_sha256=refs[0],
                base_device_source=original_ref,
                provider_id="openocd-upstream-research",
                provider_version="0.12.0",
                provider_source_commit=item["openocd_source_commit"],
                route_kind="DRIVER",
                route_source_path=item["flash_driver_source"],
                route_source_blob=item["flash_driver_git_blob_sha1"],
                applicability_source=(
                    f"OpenOCD pic32mx_devs[] named PIC32MX DEVID entry {base}={devid}; "
                    f"Git blob {item['flash_driver_git_blob_sha1']}"
                ),
                applicability="VERIFIED_BASE_DEVICE",
            ))
        else:
            require(disposition == "DRIVER_DEVID_NOT_LISTED_REVIEW_REQUIRED"
                    and item["flash_driver_devid"] is None,
                    "unexpected/unsafe research disposition")
    require(len(catalog_rows) == 1241 and len(evidence) == 893
            and len(seen) == 1241
            and dict(counts) == {
                "DIRECT_DRIVER_DEVID_ROUTE_EVIDENCE": 893,
                "DRIVER_DEVID_NOT_LISTED_REVIEW_REQUIRED": 348,
            }, "source-backed Exact ICPN admission simulation cardinality drift")
    # This is an explicit in-memory fixture; no Production Manifest, CSV,
    # Product API or production service is touched or modified.
    catalog = DeviceCatalog(
        catalog_rows,
        catalog_id="microchip-pic32mx-l1-dry-run-only",
        catalog_version="unpublished-simulation",
        status="production",  # enforce normal source-reference guards
    )
    candidates = AdmittedRouteCandidateRegistry(catalog, tuple(evidence))
    qualification = ProgrammingQualificationRegistry(
        catalog, (), candidate_registries=(candidates,),
    )
    framework = CatalogPromotionFramework(catalog, qualification)
    report = framework.report
    require(report["catalog_level_counts"] == {
        "0": 348, "1": 893, "2": 0, "3": 0,
    }, "canonical Registry projected unexpected levels")
    require(report["selector_visible_exact_icpns"] == 893
            and report["job_selectable_exact_icpns"] == 0
            and report["execution_authorized_by_framework"] is False,
            "canonical Registry leaked Job/Execution entitlement")
    require(report["promotion_evidence_counts"] == {
        EVIDENCE_BACKEND_CANDIDATE_ROUTE: 893,
        "IDENTITY_ONLY": 348,
    }, "promotion evidence status drift")
    for row in catalog_rows:
        projected = qualification.describe("Microchip", row.identifier)
        assert row.base_device
        admitted = candidates.lookup(row) is not None
        require(projected["catalog_level"] == (1 if admitted else 0)
                and projected["job_selectable"] is False
                and projected["execution_authorized"] is False
                and projected["physical_programming_qualified"] is False,
                f"projected level/permission mismatch for {row.identifier}")
        if admitted:
            require(projected["state"] == "CANDIDATE"
                    and projected["selector_visible"] is True,
                    f"L1 missing programming-route candidate: {row.identifier}")
            observed = framework.observe(row)
            require(observed["promotion_blocker"] ==
                    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
                    f"unexpected L2 eligibility for {row.identifier}")
        else:
            require(projected["state"] == "UNKNOWN"
                    and projected["selector_visible"] is False,
                    f"unsupported route inferred for {row.identifier}")
    return {
        "schema_version": 1,
        "scope": "UNPUBLISHED_IN_MEMORY_CANONICAL_PIC32MX_L1_DRY_RUN_ONLY",
        "source_replay_sha256": ledger["source_report_sha256"],
        "source_pinned_openocd_commit": review["provider_source_commit"],
        "simulated_identified_exact_icpns": 1241,
        "simulated_l1_only": 893,
        "simulated_l0_only": 348,
        "simulated_l2_only": 0,
        "simulated_l3_only": 0,
        "simulated_job_selectable": 0,
        "simulated_execution_authorized": False,
        "actual_production_identity_admission": 0,
        "actual_production_route_admission": 0,
        "production_write_authorized": False,
        "openocd_supported_claimed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--driver-source", required=True, type=Path)
    parser.add_argument("--prior-review", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require("production" not in {part.lower() for part in args.output.resolve().parts},
            "cannot publish simulator results to Production")
    ledger = json.loads(args.ledger.read_bytes())
    prior = (json.loads(args.prior_review.read_bytes())
             if args.prior_review is not None else None)
    result = run(ledger, args.driver_source.read_bytes(), prior_review=prior)
    encoded = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    if args.verify:
        require(args.output.read_bytes() == encoded, "non-deterministic dry run")
    else:
        require(not args.output.exists(), "refuse overwrite")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

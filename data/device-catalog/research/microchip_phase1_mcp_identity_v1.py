#!/usr/bin/env python3
"""ADR-0002 Phase 1: source-locked Microchip exact ICPN->basePartNumber replay.

Read archived original manufacturer MCP response bytes ONLY. Enforces the
existing independent 20/60 pagination reconciliation. Not an OpenOCD,
Programming Profile, IC Selector, Production or hardware integration tool.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import microchip_mcp_paged_probe_v2 as paged
import microchip_mcp_probe_v1 as probe
from microchip_phase1_information_v1 import DEFAULT_PATH, check

QUERY = "ATSAMD21G18A"
EXPECTED_EXACT = frozenset(("ATSAMD21G18A-MU", "ATSAMD21G18A-MF"))


def require(value, message):
    if not value:
        raise ValueError(message)


def replay_identity(original_root, dataset):
    """Exact manufacturer row evidence; does NOT promote any identity to ADMITTED."""
    check(dataset)
    required = frozenset(x["icpn"] for x in dataset["records"])
    require(required == EXPECTED_EXACT and len(dataset["records"]) == 2,
            "unexpected or unreviewed exact pilot cohort")
    directory = Path(original_root)
    verification = paged.replay(directory, QUERY)
    require(verification["exact_prefix_ordering_count"] >= 2
            and verification["independent_page_size_identity_and_lifecycle_match"],
            "manufacturer independent pagination not reconciled")
    known = frozenset(verification["exact_query_ordering_parts"])
    require(required <= known, "the exact manufacturer ordering rows are missing")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    attestations = defaultdict(list)
    for event in manifest["responses"]:
        request = event["request"]
        if request["method"] != "tools/call":
            continue
        args = request["params"]["arguments"]
        if args["limit"] != paged.PRIMARY_LIMIT:
            # Reconcile with the independent 60-row walk through paged.replay(),
            # extract identity only once from the full primary walk.
            continue
        raw = (directory / event["file"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == event["sha256"],
                "original MCP source response byte SHA-256 mismatch")
        data = probe.product_data(probe.decode(raw, request["id"]))
        _, rows = paged.validate_page(
            data, args["offset"], args["limit"], query=QUERY
        )
        for row in rows:
            icpn = row.get("partNumber")
            if icpn not in required:
                continue
            require(probe.exact_ordering_prefix(icpn, QUERY),
                    "product name is not an exact ordering-prefix response")
            base = row.get("basePartNumber")
            require(isinstance(base, str) and base.strip() == base and base,
                    "exact ICPN basePartNumber absent or malformed")
            attestations[icpn].append({
                "icpn": icpn,
                "manufacturer_base_part_number": base,
                "raw_lifecycle_status_not_admission": row["lifecycleStatus"],
                "manufacturer_product_url": row.get("productUrl"),
                "query": QUERY,
                "request_limit": args["limit"],
                "request_offset": args["offset"],
                "response_file": event["file"],
                "response_sha256": event["sha256"],
                "retrieved_at_utc": event.get("retrieved_at_utc"),
                "source_endpoint": probe.ENDPOINT,
                "identity_provenance_state": "EXACT_MANUFACTURER_MCP_RESPONSE_REPLAYED",
                "identity_admission_state": "NOT_ADMITTED",
            })
    require(set(attestations) == required
            and all(len(rows) == 1 for rows in attestations.values()),
            "exact manufacturer identity rows ambiguous or missing")
    records = [attestations[name][0] for name in sorted(required)]
    return {
        "schema_version": 1,
        "policy": "ADR-0002 Phase 1",
        "manufacturer": "Microchip",
        "query": QUERY,
        "original_mcp_pagination_replayed": True,
        "matched_exact_manufacturer_icpns": len(records),
        "source_exact_prefix_candidates": verification["exact_prefix_ordering_count"],
        "source_fuzzy_foreign_results_excluded": verification["fuzzy_foreign_ordering_count"],
        "exact_manufacturer_identity_evidence": records,
        "all_records_internally_admitted": False,
        "manufacturer_global_inventory_complete": False,
        "programming_or_software_supported_claimed": False,
        "physical_hil_claimed": False,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original-root", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    dataset = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    result = replay_identity(args.original_root, dataset)
    if args.report is not None:
        out = args.report.resolve()
        require("production" not in {x.lower() for x in out.parts},
                "forbidden Production output")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                       encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

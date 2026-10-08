#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import review_openocd_bounded_evidence_v619 as v619

HERE = Path(__file__).resolve().parent
POLICY = HERE / "openocd-bounded-identifier-bridge-v6.19.json"

EXPECTED_EXACT_SET_SHA256 = "20b3910840a802a8855ad9022aa6bc67a35e8b169bd71726189eb803ded8636f"
EXPECTED_REVIEW_CSV_SHA256 = "e3a74067f6e1ec8ec784116dc71c5d33d8fec5ff06974291185a904adf0f5c3a"
EXPECTED_BINDING_SHA256 = "c986e9dbd6e365b3ed6a7054f62e01ae2cd0e18e15cb3841321d43d20fc94892"


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    rows, _, summary = v619.build()

    req(summary["reviewed_exact_count"] == 17, "v6.19 reviewed count drift")
    req(summary["reviewed_exact_set_sha256"] == EXPECTED_EXACT_SET_SHA256,
        "v6.19 exact-set digest drift")
    req(summary["review_csv_sha256"] == EXPECTED_REVIEW_CSV_SHA256,
        "v6.19 review CSV digest drift")
    req(summary["bridge_binding_sha256"] == EXPECTED_BINDING_SHA256,
        "v6.19 bridge binding digest drift")

    live = summary["bridges"]
    req(policy["scope"]["exact_icpn_count"] == 17, "policy exact count drift")
    req(policy["scope"]["family_counts"] == {"STM32F3":4,"STM32G0":12,"STM32L1":1},
        "policy family partition drift")
    req(policy["scope"]["exact_icpns"] == sorted(live), "policy exact scope drift")
    req(policy["bridges"] == live, "policy bridge mapping drift")

    evidence = policy["evidence"]
    req(evidence["source_review_exact_set_sha256"] == EXPECTED_EXACT_SET_SHA256,
        "policy source exact-set digest drift")
    req(evidence["source_review_csv_sha256"] == EXPECTED_REVIEW_CSV_SHA256,
        "policy source review CSV digest drift")
    req(evidence["source_bridge_binding_sha256"] == EXPECTED_BINDING_SHA256,
        "policy source binding digest drift")
    req(evidence["route_inventory_git_blob_sha"] == v619.EXPECTED_ROUTE_INVENTORY_GIT_BLOB_SHA,
        "policy route inventory digest drift")

    gov = policy["governance"]
    req(gov["generic_one_char_generalization_authorized"] is False,
        "generic one-char policy accidentally authorized")
    req(gov["exact_set_bridge_only"] is True, "bounded bridge scope opened")
    for key in (
        "production_mapping_write_authorized",
        "programming_profile_binding_claimed",
        "programming_verified_claimed",
        "engineering_verified_claimed",
        "hil_verified_claimed",
    ):
        req(gov[key] is False, f"v6.19 overclaim: {key}")

    cov = policy["coverage_projection_if_later_promoted"]
    req(cov["potential_active_openocd_route_exact_count"] == 3975,
        "coverage numerator drift")
    req(cov["remaining_gap"] == 575, "remaining gap drift")
    req(cov["potential_coverage_percent"] == 87.3626, "coverage percent drift")

    req(len(rows) == 17, "live evidence row count drift")
    print("OPENOCD_BOUNDED_IDENTIFIER_BRIDGE_V619_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

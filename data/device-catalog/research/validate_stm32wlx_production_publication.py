#!/usr/bin/env python3
"""Validate checked-in STM32WLX Production catalog publication bytes."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from publish_stm32wlx_catalog import (
    CANONICAL,
    EXPECTED_ACTIVE_BASES,
    EXPECTED_CANONICAL_GIT_BLOB_SHA,
    EXPECTED_CANONICAL_SHA256,
    EXPECTED_DISCOVERY_BASES,
    EXPECTED_EXACT_SET_SHA256,
    EXPECTED_EXCLUDED_NON_ACTIVE,
    EXPECTED_MAPPING_COUNTS,
    EXPECTED_POSTSTATE_EXACT,
    EXPECTED_POSTSTATE_FAMILIES,
    EXPECTED_PRESTATE_EXACT,
    EXPECTED_PRESTATE_FAMILIES,
    EXPECTED_ROWS,
    EXPECTED_ROUTE_KIND_COUNTS,
    FAMILY,
    MANUFACTURER,
    PRODUCTION_FIELDS,
    PRODUCTION_MANIFEST,
    SERIES,
    TARGET_CONFIG,
    render_publication,
)

HERE = Path(__file__).resolve().parent
PROPOSAL = HERE / "stm32wlx-production-publication-proposal.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def set_sha(values: set[str]) -> str:
    return hashlib.sha256(
        ("\n".join(sorted(values)) + "\n").encode("utf-8")
    ).hexdigest()


def main() -> int:
    canonical_bytes, manifest_bytes, proposal = render_publication()

    req(CANONICAL.read_bytes() == canonical_bytes, "checked-in STM32WLX canonical CSV differs from frozen source")
    req(PRODUCTION_MANIFEST.read_bytes() == manifest_bytes, "checked-in Production manifest differs from deterministic STM32WLX poststate")
    expected_proposal = (json.dumps(proposal, indent=2, sort_keys=True) + "\n").encode("utf-8")
    req(PROPOSAL.read_bytes() == expected_proposal, "checked-in STM32WLX publication proposal differs from deterministic renderer")

    rows = list(csv.DictReader(io.StringIO(canonical_bytes.decode("utf-8"))))
    req(tuple(rows[0].keys()) == PRODUCTION_FIELDS if rows else False, "STM32WLX canonical schema drifted")
    req(len(rows) == EXPECTED_ROWS, f"STM32WLX canonical row count drifted: {len(rows)}")

    icpns = {row["icpn"] for row in rows}
    bases = {row["base_device"] for row in rows}
    req(len(icpns) == EXPECTED_ROWS, "STM32WLX canonical ICPNs are not unique")
    req(set_sha(icpns) == EXPECTED_EXACT_SET_SHA256, "STM32WLX exact ICPN set digest drifted")
    req(len(bases) == EXPECTED_ACTIVE_BASES, "STM32WLX Active Base Device count drifted")
    req({row["family"] for row in rows} == {FAMILY}, "STM32WLX canonical file contains foreign family")
    req({row["manufacturer"] for row in rows} == {MANUFACTURER}, "STM32WLX manufacturer drifted")
    req(
        Counter(row["existing_identifier_kind"] for row in rows)
        == Counter(EXPECTED_ROUTE_KIND_COUNTS),
        "STM32WLX route assignment kind counts drifted",
    )
    req(
        Counter(row["mapping_status"] for row in rows)
        == Counter(EXPECTED_MAPPING_COUNTS),
        "STM32WLX mapping method counts drifted",
    )
    req(all(row["openocd_target_config"] == TARGET_CONFIG for row in rows), "STM32WLX target config drifted")
    req(all(row["cmsis_device_name"] == "" for row in rows), "STM32WLX commercial route unexpectedly uses CMSIS identity")
    req(sum(row["series"] == "STM32WL54" for row in rows) == 4, "STM32WL54 row count drifted")
    req(sum(row["series"] == "STM32WL55" for row in rows) == 6, "STM32WL55 row count drifted")
    req(sum(row["series"] == "STM32WL5MOC" for row in rows) == 2, "STM32WL5MOC row count drifted")
    req(sum(row["series"] == "STM32WLE4" for row in rows) == 8, "STM32WLE4 row count drifted")
    req(sum(row["series"] == "STM32WLE5" for row in rows) == 11, "STM32WLE5 row count drifted")
    by_icpn = {row["icpn"]: row for row in rows if row["series"] == "STM32WL5MOC"}
    req(set(by_icpn) == {"STM32WL5MOCH6STR", "STM32WL5MOCH6TR"}, "STM32WL5MOC exact identities drifted")
    req(by_icpn["STM32WL5MOCH6STR"]["mapping_status"] == "deterministic_ordering_pattern_via_stsafe_provisioning_bridge", "STM32WL5MOCH6STR bridge drifted")
    req(by_icpn["STM32WL5MOCH6TR"]["mapping_status"] == "deterministic_ordering_pattern", "STM32WL5MOCH6TR direct route drifted")

    manifest = json.loads(manifest_bytes)
    sources = manifest.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    family_sources = [source for source in sources if source.get("family") == FAMILY]
    req(len(family_sources) == 1, "STM32WLX Production source binding missing or duplicated")
    req(
        family_sources[0] == {
            "manufacturer": MANUFACTURER,
            "family": FAMILY,
            "path": "../research/stm32wlx-commercial-icpn.csv",
            "row_count": EXPECTED_ROWS,
            "git_blob_sha": EXPECTED_CANONICAL_GIT_BLOB_SHA,
            "sha256": EXPECTED_CANONICAL_SHA256,
        },
        "STM32WLX Production source binding drifted",
    )
    req(sum(int(source["row_count"]) for source in sources) == EXPECTED_POSTSTATE_EXACT, "Production exact ICPN count drifted")
    req(len(sources) == EXPECTED_POSTSTATE_FAMILIES, "Production family count drifted")

    req(proposal.get("transaction") == "stm32wlx-production-catalog-publication", "publication transaction drifted")
    req(proposal.get("research_series") == SERIES, "publication research series drifted")
    req(proposal.get("family") == FAMILY, "publication family drifted")
    req(proposal.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SET_SHA256, "proposal exact-set digest drifted")
    req(proposal.get("published_exact_icpns") == EXPECTED_ROWS, "proposal published ICPN count drifted")
    req(proposal.get("published_active_base_devices") == EXPECTED_ACTIVE_BASES, "proposal Active Base Device count drifted")
    req(proposal.get("discovery_base_devices") == EXPECTED_DISCOVERY_BASES, "proposal discovery boundary drifted")
    req(proposal.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED_NON_ACTIVE, "proposal lifecycle exclusion count drifted")
    req(proposal.get("route_assignment_kind_counts") == EXPECTED_ROUTE_KIND_COUNTS, "proposal route counts drifted")
    req(proposal.get("mapping_status_counts") == EXPECTED_MAPPING_COUNTS, "proposal mapping counts drifted")
    req(proposal.get("metadata_exception_count") == 0, "proposal metadata exception count drifted")
    req(proposal.get("route_bridge_count") == 1, "proposal route bridge count drifted")
    req(proposal.get("production_exact_icpns_before") == EXPECTED_PRESTATE_EXACT, "Production exact prestate drifted")
    req(proposal.get("production_exact_icpns_after") == EXPECTED_POSTSTATE_EXACT, "Production exact poststate drifted")
    req(proposal.get("production_family_count_before") == EXPECTED_PRESTATE_FAMILIES, "Production family prestate drifted")
    req(proposal.get("production_family_count_after") == EXPECTED_POSTSTATE_FAMILIES, "Production family poststate drifted")
    req(proposal.get("marketing_status_observed") == {"Active": EXPECTED_ROWS}, "observed marketing-status count drifted")

    for key in (
        "ppu_hil_required_for_catalog_admission",
        "socket_hil_required_for_catalog_admission",
        "physical_programming_success_required_for_catalog_admission",
        "physical_validation_claimed",
        "programming_algorithm_equivalence_claimed",
        "runtime_programming_support_claimed",
        "wireless_radio_operation_authorized",
        "wireless_security_operation_authorized",
        "security_mutation_support_claimed",
        "debug_attach_support_claimed",
        "catalog_membership_authorizes_target_execution",
        "remaining_wireless_families_rejected",
    ):
        req(proposal.get(key) is False, f"unsafe STM32WLX publication claim enabled: {key}")

    print(json.dumps({
        "family": FAMILY,
        "published_exact_icpns": len(rows),
        "published_active_base_devices": len(bases),
        "production_exact_icpns": EXPECTED_POSTSTATE_EXACT,
        "production_families": EXPECTED_POSTSTATE_FAMILIES,
        "wireless_radio_operation_authorized": False,
        "wireless_security_operation_authorized": False,
        "catalog_membership_authorizes_target_execution": False,
    }, indent=2, sort_keys=True))
    print("STM32WLX Production publication validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

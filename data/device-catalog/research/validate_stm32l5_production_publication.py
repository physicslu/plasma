#!/usr/bin/env python3
"""Validate checked-in STM32L5 Production catalog publication bytes."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from publish_stm32l5_catalog import (
    EXPECTED_BASES,
    EXPECTED_EXACT_SET_SHA256,
    EXPECTED_POSTSTATE_EXACT,
    EXPECTED_POSTSTATE_FAMILIES,
    EXPECTED_ROWS,
    FAMILY,
    PRODUCTION_FIELDS,
    PRODUCTION_MANIFEST,
    render_publication,
)

HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "stm32l5-commercial-icpn.csv"
PROPOSAL = HERE / "stm32l5-production-publication-proposal.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def set_sha(values: set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode("utf-8")).hexdigest()


def main() -> int:
    canonical_bytes, manifest_bytes, proposal = render_publication()
    req(CANONICAL.read_bytes() == canonical_bytes, "checked-in STM32L5 canonical CSV differs from deterministic renderer")
    req(PRODUCTION_MANIFEST.read_bytes() == manifest_bytes, "checked-in Production manifest differs from deterministic STM32L5 poststate")
    expected_proposal = (json.dumps(proposal, indent=2, sort_keys=True) + "\n").encode("utf-8")
    req(PROPOSAL.read_bytes() == expected_proposal, "checked-in STM32L5 publication proposal differs from deterministic renderer")

    rows = list(csv.DictReader(io.StringIO(canonical_bytes.decode("utf-8"))))
    req(tuple(rows[0].keys()) == PRODUCTION_FIELDS if rows else False, "STM32L5 canonical schema drifted")
    req(len(rows) == EXPECTED_ROWS, f"STM32L5 canonical row count drifted: {len(rows)}")
    icpns = {row["icpn"] for row in rows}
    bases = {row["base_device"] for row in rows}
    req(len(icpns) == EXPECTED_ROWS, "STM32L5 canonical ICPNs are not unique")
    req(set_sha(icpns) == EXPECTED_EXACT_SET_SHA256, "STM32L5 exact ICPN set digest drifted")
    req(len(bases) == EXPECTED_BASES, "STM32L5 Base Device count drifted")
    req({row["family"] for row in rows} == {FAMILY}, "STM32L5 canonical file contains foreign family")
    req({row["manufacturer"] for row in rows} == {"STMicroelectronics"}, "STM32L5 manufacturer drifted")
    req({row["mapping_status"] for row in rows} <= {"deterministic_ordering_pattern", "deterministic_cmsis_device_name"}, "STM32L5 mapping method escaped deterministic allowlist")
    req(all(row["verification_status"].startswith("verified_") for row in rows), "STM32L5 admitted identity lacks verified provenance status")
    req(all(row["openocd_target_config"] == "tcl/target/stm32l5x.cfg" for row in rows), "STM32L5 target config drifted")

    req(proposal.get("production_exact_icpns_after") == EXPECTED_POSTSTATE_EXACT, "STM32L5 Production exact ICPN poststate drifted")
    req(proposal.get("production_family_count_after") == EXPECTED_POSTSTATE_FAMILIES, "STM32L5 Production family poststate drifted")
    req(proposal.get("marketing_status_observed") == {"Active": 49}, "STM32L5 observed marketing-status counts drifted")
    for key in (
        "ppu_hil_required_for_catalog_admission",
        "socket_hil_required_for_catalog_admission",
        "physical_programming_success_required_for_catalog_admission",
        "physical_validation_claimed",
        "runtime_programming_support_claimed",
        "security_mutation_support_claimed",
        "debug_attach_support_claimed",
        "catalog_membership_authorizes_target_execution",
    ):
        req(proposal.get(key) is False, f"unsafe STM32L5 publication claim enabled: {key}")

    print(json.dumps({
        "family": FAMILY,
        "published_exact_icpns": len(rows),
        "published_base_devices": len(bases),
        "production_exact_icpns": EXPECTED_POSTSTATE_EXACT,
        "production_families": EXPECTED_POSTSTATE_FAMILIES,
        "physical_validation_claimed": False,
        "runtime_programming_support_claimed": False,
    }, indent=2, sort_keys=True))
    print("STM32L5 Production publication validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

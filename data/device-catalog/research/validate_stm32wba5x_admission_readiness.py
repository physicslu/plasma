#!/usr/bin/env python3
"""Validate STM32WBA5X catalog admission readiness."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from stm32wba5x_admission_readiness import (
    EXPECTED_EXACT_COUNT,
    EXPECTED_EXACT_SHA256,
    EXPECTED_MAPPING_COUNTS,
    EXPECTED_PRODUCTION_COUNT,
    EXPECTED_PRODUCTION_FAMILIES,
    EXPECTED_ROUTE_KIND_COUNTS,
    FAMILY,
    PRODUCTION,
    PRODUCTION_FIELDS,
    build_readiness,
    build_rows,
    csv_text,
)

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "stm32wba5x-commercial-icpn.csv"
READINESS_PATH = HERE / "stm32wba5x-admission-readiness.json"
AUTHORITY_PATH = HERE / "stm32wba5x-metadata-authority.json"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def main() -> int:
    rows = build_rows()
    expected_csv = csv_text(rows)
    expected_readiness = build_readiness(rows, expected_csv)

    req(CSV_PATH.read_text(encoding="utf-8") == expected_csv, "checked-in canonical CSV differs from deterministic renderer")
    checked_readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    req(checked_readiness == expected_readiness, "checked-in readiness differs from deterministic renderer")

    parsed = list(csv.DictReader(io.StringIO(expected_csv)))
    req(len(parsed) == EXPECTED_EXACT_COUNT == 40, "canonical row count drifted")
    req(tuple(parsed[0].keys()) == PRODUCTION_FIELDS if parsed else False, "canonical schema drifted")
    icpns = [row["icpn"] for row in parsed]
    req(icpns == sorted(set(icpns)), "canonical exact ICPNs are not sorted unique")
    digest = hashlib.sha256(("\n".join(icpns) + "\n").encode("utf-8")).hexdigest()
    req(digest == EXPECTED_EXACT_SHA256, "canonical exact-set digest drifted")
    req(Counter(row["existing_identifier_kind"] for row in parsed) == Counter(EXPECTED_ROUTE_KIND_COUNTS), "route-kind counts drifted")
    req(Counter(row["mapping_status"] for row in parsed) == Counter(EXPECTED_MAPPING_COUNTS), "mapping counts drifted")
    req(all(row["cmsis_device_name"] == "" for row in parsed), "CMSIS bridge unexpectedly used")
    req(all(row["openocd_target_config"] == "tcl/target/stm32wba5x.cfg" for row in parsed), "target config drifted")
    req(all(row["verification_status"] == "verified_st_datasheet_ordering_information_plus_retained_exact_identity" for row in parsed), "metadata verification status drifted")

    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    req(authority.get("authority_id") == "stm32wba5x-ordering-information-v1", "metadata authority id drifted")
    docs = authority.get("documents")
    req(isinstance(docs, list) and {(d.get("document_id"),d.get("revision")) for d in docs} == {
        ("DS14688","Rev 2"),("DS14127","Rev 10"),("DS14801","Rev 4")
    }, "metadata authority documents drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority claim escaped")

    req(checked_readiness.get("catalog_admission_ready") is True, "catalog admission readiness not opened")
    req(checked_readiness.get("next_gate") == "stm32wba5x-production-publication-gate", "publication gate drifted")
    req(checked_readiness.get("identity_ready_count") == 40, "identity-ready count drifted")
    req(checked_readiness.get("lifecycle_ready_count") == 40, "lifecycle-ready count drifted")
    req(checked_readiness.get("metadata_ready_count") == 40, "metadata-ready count drifted")
    req(checked_readiness.get("route_ready_count") == 40, "route-ready count drifted")
    req(checked_readiness.get("manual_review_count") == 0, "manual review opened")
    req(checked_readiness.get("metadata_exception_count") == 0, "metadata exception opened")
    req(checked_readiness.get("route_bridge_count") == 0, "route bridge unexpectedly opened")
    req(checked_readiness.get("route_assignment_kind_counts") == {"ordering_pattern":40}, "readiness route counts drifted")
    req(checked_readiness.get("mapping_status_counts") == {"deterministic_ordering_pattern":40}, "readiness mapping counts drifted")
    req(checked_readiness.get("canonical_candidate_sha256") == "653dca4184eab05c3a0c8e6714e73adacf3d6927310855faf064b7d8d0b322d6", "canonical CSV SHA256 drifted")
    req(checked_readiness.get("canonical_candidate_git_blob_sha") == "21cd808371f4d6f05a813e35b06cb1227f96195a", "canonical CSV Git blob drifted")
    req(all(value is False for value in (checked_readiness.get("claims") or {}).values()), "readiness claim escaped fail-closed state")

    production = json.loads(PRODUCTION.read_text(encoding="utf-8"))
    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(source.get("row_count",0)) for source in sources if isinstance(source,dict)) == EXPECTED_PRODUCTION_COUNT, "Production exact count changed")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count changed")
    req(all(not (isinstance(source,dict) and source.get("family") == FAMILY) for source in sources), "STM32WBA5X leaked into Production")

    print("STM32WBA5X admission readiness validation: PASS")
    print("exact=40 metadata=40 route=40 direct=40 bridge=0 manual=0")
    print("Production=2604/21 next=stm32wba5x-production-publication-gate")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

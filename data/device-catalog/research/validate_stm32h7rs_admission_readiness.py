#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from stm32h7rs_admission_readiness import (
    EXPECTED_EXACT_COUNT,
    EXPECTED_EXACT_SHA256,
    EXPECTED_PRODUCTION_COUNT,
    EXPECTED_ROUTE_KIND_COUNTS,
    FAMILY,
    NEXT_GATE,
    TARGET_CONFIG,
    build_readiness,
    build_rows,
    csv_text,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASELINE = HERE / "stm32h7rs-admission-readiness.json"
CSV_PATH = HERE / "stm32h7rs-commercial-icpn.csv"
AUTHORITY = HERE / "stm32h7rs-metadata-authority.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def main() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    replay = build_readiness()
    req(baseline == replay, "readiness baseline differs from deterministic replay")

    rows = build_rows()
    req(len(rows) == EXPECTED_EXACT_COUNT, "canonical candidate row count drifted")
    req(len({r["icpn"] for r in rows}) == EXPECTED_EXACT_COUNT, "candidate ICPNs are not unique")
    req(all(r["family"] == FAMILY for r in rows), "candidate family drifted")
    req(all(r["openocd_target_config"] == TARGET_CONFIG for r in rows), "candidate target config drifted")
    req(all(r["verification_status"] == "verified_st_datasheet_ordering_information_plus_retained_exact_identity" for r in rows), "candidate verification status drifted")
    req(all(r["source_authority"].startswith("https://www.st.com/") for r in rows), "non-ST metadata authority retained")

    expected_csv = csv_text(rows)
    actual_csv = CSV_PATH.read_text(encoding="utf-8")
    req(actual_csv == expected_csv, "canonical candidate CSV differs from deterministic replay")
    req(hashlib.sha256(actual_csv.encode()).hexdigest() == baseline["canonical_candidate_csv_sha256"], "candidate CSV digest drifted")

    route_kinds: dict[str, int] = {}
    for row in rows:
        route_kinds[row["existing_identifier_kind"]] = route_kinds.get(row["existing_identifier_kind"], 0) + 1
    req(route_kinds == EXPECTED_ROUTE_KIND_COUNTS, "route assignment kind counts drifted")
    req(sum(1 for r in rows if r["existing_identifier_kind"] == "cmsis_device_name" and r["option_suffix"] in {"H", "HTR"}) == 5, "Hexadeca-SPI CMSIS route bridge count drifted")

    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    docs = authority.get("documents")
    req(isinstance(docs, list) and len(docs) == 2, "metadata authority documents drifted")
    req({d["document_id"] for d in docs} == {"DS14359", "DS14360"}, "metadata authority document ids drifted")
    req({d["revision"] for d in docs} == {"Rev 7", "Rev 5"}, "metadata authority revisions drifted")
    req(authority["ordering_semantics"]["flash_size"] == {"8": "64 KiB"}, "flash authority drifted")
    req(authority["ordering_semantics"]["temperature_grade"] == {"6": "-40..85 C"}, "temperature authority drifted")
    req(authority["ordering_semantics"]["functional_option"] == {"H": "Hexadeca SPI support"}, "functional option authority drifted")
    req(authority["ordering_semantics"]["packing"] == {"TR": "tape and reel"}, "packing authority drifted")

    req(baseline["frozen_exact_icpn_count"] == EXPECTED_EXACT_COUNT, "baseline exact count drifted")
    req(baseline["frozen_exact_icpn_set_sha256"] == EXPECTED_EXACT_SHA256, "baseline exact digest drifted")
    req(baseline["identity_ready_count"] == EXPECTED_EXACT_COUNT, "identity readiness drifted")
    req(baseline["lifecycle_ready_count"] == EXPECTED_EXACT_COUNT, "lifecycle readiness drifted")
    req(baseline["metadata_ready_count"] == EXPECTED_EXACT_COUNT, "metadata readiness drifted")
    req(baseline["route_ready_count"] == EXPECTED_EXACT_COUNT, "route readiness drifted")
    req(baseline["manual_review_count"] == 0, "manual review opened")
    req(baseline["catalog_admission_ready"] is True, "Catalog admission readiness closed")
    req(baseline["next_gate"] == NEXT_GATE, "next gate drifted")

    claims = baseline.get("claims")
    req(isinstance(claims, dict), "claims missing")
    req(all(v is False for v in claims.values()), "fail-closed claim escaped")
    req(claims["hil_required_for_catalog_admission"] is False, "HIL became Catalog prerequisite")

    production = json.loads(PRODUCTION.read_text(encoding="utf-8"))
    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(x["row_count"]) for x in sources) == EXPECTED_PRODUCTION_COUNT, "Production count changed")
    req(all(x.get("family") != FAMILY for x in sources), "STM32H7RS leaked into Production")

    print(
        "PASS: STM32H7RS admission readiness: "
        f"{EXPECTED_EXACT_COUNT}/{EXPECTED_EXACT_COUNT} ready, "
        "31 ordering + 5 CMSIS routes, Production unchanged at 2282"
    )

if __name__ == "__main__":
    main()

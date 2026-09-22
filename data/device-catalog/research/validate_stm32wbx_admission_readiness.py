#!/usr/bin/env python3
"""Fail-closed validation for retained STM32WBX Catalog admission readiness."""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from stm32wbx_admission_readiness import (
    AUTHORITY,
    CSV_FIELDS,
    FAMILY,
    NEXT_GATE,
    PRODUCTION,
    TARGET_CONFIG,
    build_readiness,
    build_rows,
    csv_text,
)

HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "stm32wbx-commercial-icpn.csv"
READINESS = HERE / "stm32wbx-admission-readiness.json"

EXPECTED_EXACT_COUNT = 50
EXPECTED_EXACT_SHA = "faaa262a535e5397894d2ecfdd4589a044371fdeb6926ffc3dfaab63f219fe96"
EXPECTED_CANONICAL_SHA = "0a97caf4afc336a762d9f504b860cafeffdf0ff8a6f603665b564f10b42bd664"
EXPECTED_CANONICAL_BLOB = "caff19debecf190fc02c2a8af4b3f301e7ae4d67"
EXPECTED_EXCLUDED = ["STM32WB5MMGH6"]
EXPECTED_ROUTE_KINDS = {"ordering_pattern": 41, "cmsis_device_name": 9}
EXPECTED_MAPPING = {
    "deterministic_ordering_pattern": 41,
    "deterministic_cmsis_commercial_bridge": 9,
}
EXPECTED_DOCS = {
    ("DS11929", "Rev 17"),
    ("DS13047", "Rev 9"),
    ("DS13258", "Rev 10"),
    ("DS13259", "Rev 7"),
    ("DS13252", "Rev 8"),
    ("DS14096", "Rev 8"),
}
EXPECTED_CMSIS_PATTERNS = {
    "STM32WB15CCUxE",
    "STM32WB30CEUxA",
    "STM32WB35CCUxA",
    "STM32WB35CEUxA",
}
EXPECTED_CMSIS_ICPNS = {
    "STM32WB15CCU6E",
    "STM32WB15CCU7E",
    "STM32WB30CEU5A",
    "STM32WB30CEU5ATR",
    "STM32WB35CCU6A",
    "STM32WB35CCU6ATR",
    "STM32WB35CCU7A",
    "STM32WB35CEU6A",
    "STM32WB35CEU7A",
}

def req(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value

def read_csv_text(value: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(value)))
    req(tuple(rows[0].keys()) == CSV_FIELDS if rows else False, "canonical CSV schema drifted")
    return rows

def validate(canonical_text: str, readiness: dict[str, Any], authority: dict[str, Any], production: dict[str, Any]) -> None:
    rebuilt_rows = build_rows()
    rebuilt_csv = csv_text(rebuilt_rows)
    req(canonical_text == rebuilt_csv, "retained canonical CSV is not deterministic replay")
    rebuilt_readiness = build_readiness(rebuilt_rows, rebuilt_csv)
    req(readiness == rebuilt_readiness, "retained readiness JSON is not deterministic replay")

    rows = read_csv_text(canonical_text)
    req(len(rows) == EXPECTED_EXACT_COUNT, "canonical row count drifted")
    req(len({row["icpn"] for row in rows}) == EXPECTED_EXACT_COUNT, "duplicate canonical ICPN")
    req({row["family"] for row in rows} == {FAMILY}, "canonical family drifted")
    req({row["openocd_target_config"] for row in rows} == {TARGET_CONFIG}, "target config drifted")
    req(Counter(row["existing_identifier_kind"] for row in rows) == Counter(EXPECTED_ROUTE_KINDS), "route-kind distribution drifted")
    req(Counter(row["mapping_status"] for row in rows) == Counter(EXPECTED_MAPPING), "mapping-status distribution drifted")
    req(all(row["verification_status"] == "verified_st_datasheet_ordering_information_plus_retained_exact_identity" for row in rows), "metadata verification status drifted")
    req(all(row["source_type"] == "official_st_datasheet_ordering_information_plus_retained_exact_identity" for row in rows), "metadata source type drifted")
    req(all(row["source_reference"] and row["source_authority"] for row in rows), "metadata provenance missing")

    cmsis = [row for row in rows if row["existing_identifier_kind"] == "cmsis_device_name"]
    req(len(cmsis) == 9, "CMSIS bridge count drifted")
    req({row["icpn"] for row in cmsis} == EXPECTED_CMSIS_ICPNS, "CMSIS bridge exact identity set drifted")
    req({row["existing_identifier"] for row in cmsis} == EXPECTED_CMSIS_PATTERNS, "CMSIS bridge pattern set drifted")
    req(all(row["cmsis_device_name"] == row["existing_identifier"] for row in cmsis), "CMSIS bridge provenance drifted")
    direct = [row for row in rows if row["existing_identifier_kind"] == "ordering_pattern"]
    req(len(direct) == 41 and all(not row["cmsis_device_name"] for row in direct), "direct route surface drifted")

    req(readiness.get("readiness_id") == "stm32wbx-bounded-exact-icpn-admission-readiness-v1", "readiness id drifted")
    req(readiness.get("status") == "catalog_admission_ready", "readiness status drifted")
    req(readiness.get("catalog_admission_ready") is True, "Catalog admission readiness closed")
    req(readiness.get("frozen_exact_icpn_count") == EXPECTED_EXACT_COUNT, "frozen exact count drifted")
    req(readiness.get("frozen_exact_icpn_set_sha256") == EXPECTED_EXACT_SHA, "exact-set digest drifted")
    req(readiness.get("excluded_non_active_part_number_count") == 1, "excluded lifecycle count drifted")
    req(readiness.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED, "excluded lifecycle identity drifted")
    req(readiness.get("identity_ready_count") == 50, "identity readiness drifted")
    req(readiness.get("lifecycle_ready_count") == 50, "lifecycle readiness drifted")
    req(readiness.get("metadata_ready_count") == 50, "metadata readiness drifted")
    req(readiness.get("route_ready_count") == 50, "route readiness drifted")
    req(readiness.get("manual_review_count") == 0, "manual review opened")
    req(readiness.get("metadata_exception_count") == 0, "metadata exception opened")
    req(readiness.get("route_bridge_count") == 9, "route bridge count drifted")
    req(readiness.get("route_assignment_kind_counts") == EXPECTED_ROUTE_KINDS, "readiness route-kind counts drifted")
    req(readiness.get("mapping_status_counts") == EXPECTED_MAPPING, "readiness mapping-status counts drifted")
    req(readiness.get("target_config") == TARGET_CONFIG, "readiness target config drifted")
    req(readiness.get("canonical_candidate_sha256") == EXPECTED_CANONICAL_SHA, "canonical SHA-256 drifted")
    req(readiness.get("canonical_candidate_git_blob_sha") == EXPECTED_CANONICAL_BLOB, "canonical Git blob drifted")
    req(readiness.get("next_gate") == NEXT_GATE, "next gate drifted")
    claims = readiness.get("claims")
    req(isinstance(claims, dict) and claims, "readiness claims missing")
    req(all(value is False for value in claims.values()), "readiness fail-closed claim escaped")
    req(claims.get("cmsis_bridge_authorizes_production_route") is False, "CMSIS bridge authorized Production route")
    req(claims.get("stm32wba6x_rejected") is False, "WBA6X was incorrectly rejected")

    docs = authority.get("documents")
    req(isinstance(docs, list) and len(docs) == 6, "metadata authority document count drifted")
    req({(doc.get("document_id"), doc.get("revision")) for doc in docs if isinstance(doc, dict)} == EXPECTED_DOCS, "metadata authority revisions drifted")
    req(authority.get("authority_id") == "stm32wbx-ordering-information-v1", "metadata authority id drifted")
    req(all(value is False for value in (authority.get("claims") or {}).values()), "metadata authority fail-closed claim escaped")
    route_semantics = authority.get("route_semantics") or {}
    req(route_semantics.get("target_config") == TARGET_CONFIG, "authority target config drifted")
    req("does not authorize Production publication or target execution" in str(route_semantics.get("cmsis_bridge")), "CMSIS governance wording drifted")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(source.get("row_count", 0)) for source in sources if isinstance(source, dict)) == 2554, "Production exact count drifted")
    req(len(sources) == 20, "Production family count drifted")
    req(all(not (isinstance(source, dict) and source.get("family") == FAMILY) for source in sources), "STM32WBX leaked into Production")

def expect_reject(name: str, mutate) -> None:
    canonical = CANONICAL.read_text(encoding="utf-8")
    readiness = load_json(READINESS)
    authority = load_json(AUTHORITY)
    production = load_json(PRODUCTION)
    canonical, readiness, authority, production = mutate(canonical, readiness, authority, production)
    try:
        validate(canonical, readiness, authority, production)
    except (AssertionError, RuntimeError):
        return
    raise AssertionError(f"negative control accepted: {name}")

def main() -> int:
    canonical = CANONICAL.read_text(encoding="utf-8")
    readiness = load_json(READINESS)
    authority = load_json(AUTHORITY)
    production = load_json(PRODUCTION)
    validate(canonical, readiness, authority, production)

    def identity(c,r,a,p): return c,r,a,p
    controls = [
        ("drop canonical row", lambda c,r,a,p: ("\n".join(c.splitlines()[:-1])+"\n",r,a,p)),
        ("authorize production", lambda c,r,a,p: (c,{**r,"claims":{**r["claims"],"production_write_authorized":True}},a,p)),
        ("authorize CMSIS route", lambda c,r,a,p: (c,{**r,"claims":{**r["claims"],"cmsis_bridge_authorizes_production_route":True}},a,p)),
        ("close admission readiness", lambda c,r,a,p: (c,{**r,"catalog_admission_ready":False},a,p)),
        ("route count mutation", lambda c,r,a,p: (c,{**r,"route_bridge_count":8},a,p)),
        ("metadata exception", lambda c,r,a,p: (c,{**r,"metadata_exception_count":1},a,p)),
        ("skip publication gate", lambda c,r,a,p: (c,{**r,"next_gate":"stm32wbx-runtime-programming-gate"},a,p)),
        ("canonical digest mutation", lambda c,r,a,p: (c,{**r,"canonical_candidate_sha256":"0"*64},a,p)),
        ("wrong authority revision", lambda c,r,a,p: (c,r,{**a,"documents":[{**a["documents"][0],"revision":"Rev 16"},*a["documents"][1:]]},p)),
        ("authority claim escape", lambda c,r,a,p: (c,r,{**a,"claims":{**a["claims"],"production_publication_authorized":True}},p)),
        ("Production count mutation", lambda c,r,a,p: (c,r,a,{**p,"sources":[{**p["sources"][0],"row_count":int(p["sources"][0]["row_count"])+1},*p["sources"][1:]]})),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print("STM32WBX admission readiness validation: PASS")
    print("50/50 identity+lifecycle+metadata+route ready")
    print("routes=41 ordering_pattern + 9 CMSIS bridge; ambiguous=0 unmapped=0")
    print(f"negative_controls={len(controls)} rejected")
    print("Production remains 2554 / 20")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

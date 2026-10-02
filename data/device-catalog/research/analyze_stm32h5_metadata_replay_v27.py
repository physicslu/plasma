#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXACT_PATH = HERE / "st-stm32h5-active-exact-mpn-v1.2.txt"
AUTH_PATH = HERE / "stm32h5-ordering-authority-v2.7.json"

EXPECTED_EXACT = 190
EXPECTED_DIRECT = 187
EXPECTED_EXCEPTIONS = 3
EXPECTED_SUBFAMILY_COUNTS = {
    "503": 14,
    "523": 39,
    "533": 14,
    "543": 4,
    "553": 2,
    "562": 22,
    "563": 37,
    "573": 23,
    "5E4": 13,
    "5E5": 9,
    "5F4": 9,
    "5F5": 4,
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_authority() -> dict:
    value = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    req(value.get("schema_version") == 1, "authority schema drift")
    req(value.get("authority_id") == "stm32h5-ordering-authority-v2.7", "authority id drift")
    req(set(value.get("subfamilies", {})) == set(EXPECTED_SUBFAMILY_COUNTS), "subfamily authority surface drift")
    req(len(value.get("bounded_exact_exceptions", {})) == EXPECTED_EXCEPTIONS, "exception set drift")
    req(value["claims"]["production_write_authorized"] is False, "authority file cannot authorize Production")
    return value


def load_exact() -> list[str]:
    rows = [x.strip() for x in EXACT_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(rows) == EXPECTED_EXACT and len(set(rows)) == EXPECTED_EXACT, "H5 exact ledger drift")
    return rows


def resolve_subfamily(icpn: str, authorities: dict) -> str:
    matches = [s for s in authorities if icpn.startswith("STM32H" + s)]
    req(len(matches) == 1, f"{icpn}: subfamily authority resolution failed")
    return matches[0]


def parse_shape(icpn: str, subfamily: str) -> dict:
    tail = icpn[len("STM32H" + subfamily):]
    packing = ""
    if tail.endswith("TR"):
        packing = "TR"
        tail = tail[:-2]
    dedicated = ""
    if tail.endswith("Q"):
        dedicated = "Q"
        tail = tail[:-1]
    req(len(tail) == 4, f"{icpn}: unexpected ordering-code length")
    pin_code, flash_code, package_code, temp_code = tail
    return {
        "pin_code": pin_code,
        "flash_code": flash_code,
        "package_code": package_code,
        "temperature_code": temp_code,
        "dedicated_code": dedicated,
        "packing_code": packing,
    }


def decode_one(icpn: str, auth: dict) -> dict:
    authorities = auth["subfamilies"]
    exceptions = auth["bounded_exact_exceptions"]
    subfamily = resolve_subfamily(icpn, authorities)
    rule = authorities[subfamily]
    codes = parse_shape(icpn, subfamily)

    req(codes["pin_code"] in rule["pin_count"], f"{icpn}: unknown pin code")
    req(codes["flash_code"] in rule["flash_kib"], f"{icpn}: unknown flash code")
    req(codes["temperature_code"] in rule["temperature_c"], f"{icpn}: unknown temperature code")

    exception = exceptions.get(icpn)
    package_code = codes["package_code"]
    if package_code in rule["package"]:
        package_value = rule["package"][package_code]
        metadata_basis = "ordering_information"
    else:
        req(exception is not None, f"{icpn}: package code absent from Ordering Information and no exact exception")
        req(exception["field"] == "package" and exception["code"] == package_code,
            f"{icpn}: exact exception does not authorize package code")
        package_value = exception["value"]
        metadata_basis = "ordering_information_plus_exact_st_quality_exception"

    q = codes["dedicated_code"] == "Q"
    policy = rule["q_policy"]
    if policy == "forbidden":
        req(not q, f"{icpn}: Q forbidden by authority")
    elif policy == "temperature_3_requires_q_temperature_6_7_forbid_q":
        if codes["temperature_code"] == "3":
            req(q, f"{icpn}: temperature 3 requires Q/SMPS")
        else:
            req(not q, f"{icpn}: temperatures 6/7 require LDO and forbid Q")
    elif policy == "temperature_7_requires_q_temperature_6_forbids_q":
        if codes["temperature_code"] == "7":
            req(q, f"{icpn}: temperature 7 requires Q/SMPS")
        else:
            req(not q, f"{icpn}: temperature 6 requires LDO and forbids Q")
    else:
        raise ValueError(f"{icpn}: unknown q_policy {policy}")

    if subfamily in {"543", "553"} and codes["temperature_code"] == "3":
        req(codes["package_code"] == "Z", f"{icpn}: temperature 3 requires LQFP-EP package Z")

    return {
        "icpn": icpn,
        "subfamily": subfamily,
        "pin_count": rule["pin_count"][codes["pin_code"]],
        "flash_kib": rule["flash_kib"][codes["flash_code"]],
        "package": package_value,
        "temperature": rule["temperature_c"][codes["temperature_code"]],
        "dedicated_pinout": "SMPS" if q else "LDO/default",
        "packing": "tape_and_reel" if codes["packing_code"] == "TR" else "tray_or_unspecified",
        "authority_document": rule["document"],
        "authority_revision": rule["revision"],
        "metadata_basis": metadata_basis,
        "exception_source_url": exception["source_url"] if exception else None,
    }


def analyze() -> dict:
    auth = load_authority()
    exact = load_exact()
    decoded = [decode_one(icpn, auth) for icpn in exact]

    sub_counts = dict(sorted(Counter(row["subfamily"] for row in decoded).items()))
    basis_counts = dict(sorted(Counter(row["metadata_basis"] for row in decoded).items()))
    docs = sorted({f'{row["authority_document"]} Rev {row["authority_revision"]}' for row in decoded})

    req(sub_counts == EXPECTED_SUBFAMILY_COUNTS, "decoded subfamily distribution drift")
    req(basis_counts == {
        "ordering_information": EXPECTED_DIRECT,
        "ordering_information_plus_exact_st_quality_exception": EXPECTED_EXCEPTIONS,
    }, "metadata basis partition drift")

    return {
        "audit_id": "stm32h5-metadata-authority-replay-v2.7",
        "input_active_exact_count": len(exact),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "direct_ordering_information_exact_count": EXPECTED_DIRECT,
        "bounded_exact_exception_count": EXPECTED_EXCEPTIONS,
        "subfamily_counts": sub_counts,
        "authority_documents": docs,
        "exception_exact_identities": sorted(auth["bounded_exact_exceptions"]),
        "layer2_backend_state": {
            "mapping_status": "no_mapping",
            "affected_exact_count": len(exact),
            "backend_route_synthesized": False,
        },
        "claims": {
            "layer1_identity_locked": True,
            "manufacturer_active_lifecycle_locked": True,
            "metadata_authority_replay_complete": True,
            "layer1_admission_proposal_ready": True,
            "catalog_production_write_authorized": False,
            "programming_profile_applicability_expanded": False,
            "engineering_verified": False,
            "operational_field_evidence": False,
        },
        "next_gate": (
            "Prepare a reviewable 190-row STM32H5 Layer-1 Catalog admission proposal. "
            "Keep all rows backend no_mapping unless a separate pinned backend qualification changes that state. "
            "Production publication requires explicit owner approval."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

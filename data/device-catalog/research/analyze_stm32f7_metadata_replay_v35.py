#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GAP = HERE / "stm32f7-active-exact-gap-v3.4.txt"
AUTHORITY = HERE / "stm32f7-ordering-authority-v3.5.json"

EXPECTED_GAP = 154
EXPECTED_GAP_SHA256 = "ec93408ecec154bf40a6fcd4d5ddb063e5e36cb023bc19bbed13b306a3b4a931"
EXPECTED_OVERRIDE_IDS = {
    "STM32F750V8T6",
    "STM32F750V8T7",
    "STM32F750Z8T6",
}
EXPECTED_SERIES_COUNTS = {
    "STM32F722": 18,
    "STM32F723": 12,
    "STM32F730": 5,
    "STM32F732": 4,
    "STM32F733": 4,
    "STM32F745": 14,
    "STM32F746": 22,
    "STM32F750": 3,
    "STM32F756": 8,
    "STM32F765": 27,
    "STM32F767": 19,
    "STM32F769": 5,
    "STM32F777": 11,
    "STM32F779": 2,
}
EXPECTED_PACKAGE_COUNTS = {
    "LQFP": 93,
    "TFBGA": 34,
    "UFBGA": 20,
    "WLCSP": 7,
}
EXPECTED_FLASH_COUNTS = {
    "64 KiB": 8,
    "256 KiB": 8,
    "512 KiB": 44,
    "1024 KiB": 54,
    "2048 KiB": 40,
}
EXPECTED_TEMP_COUNTS = {
    "-40 to 85 C": 118,
    "-40 to 105 C": 36,
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_gap() -> list[str]:
    rows = [x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "F7 gap ledger must remain sorted")
    req(len(rows) == EXPECTED_GAP and len(set(rows)) == EXPECTED_GAP,
        "F7 gap ledger count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_GAP_SHA256, "F7 gap exact-set digest drift")
    return rows


def load_authority() -> dict[str, Any]:
    value = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(value.get("schema_version") == 1, "authority schema drift")
    req(value.get("authority_id") == "stm32f7-ordering-authority-v3.5", "authority id drift")
    gov = value.get("governance") or {}
    req(gov.get("production_write_authorized") is False,
        "research authority cannot authorize Production")
    req(gov.get("backend_scope_evaluated") is False,
        "Layer-1 replay must not claim backend evaluation")
    req(gov.get("programming_profile_scope_expanded") is False,
        "programming profile scope overclaim")
    return value


def parse_codes(icpn: str) -> dict[str, str]:
    req(icpn.startswith("STM32F7"), f"{icpn}: non-F7 identity")
    core = icpn
    packing = ""
    if core.endswith("TR"):
        packing = "TR"
        core = core[:-2]
    series = core[:9]
    tail = core[9:]
    req(len(tail) == 4, f"{icpn}: unexpected ordering-code length")
    pin_code, flash_code, package_code, temperature_code = tail
    return {
        "series": series,
        "pin_code": pin_code,
        "flash_code": flash_code,
        "package_code": package_code,
        "temperature_code": temperature_code,
        "packing_code": packing,
    }


def decode_one(icpn: str, authority: dict[str, Any]) -> dict[str, Any]:
    override = authority["bounded_exact_overrides"].get(icpn)
    if override is not None:
        req(icpn in EXPECTED_OVERRIDE_IDS, f"{icpn}: unexpected exact override")
        codes = parse_codes(icpn)
        req(override["base_device"] == codes["series"] + codes["pin_code"] + codes["flash_code"],
            f"{icpn}: override base-device mismatch")
        req(override["option_suffix"] == codes["packing_code"],
            f"{icpn}: override packing mismatch")
        return {
            "icpn": icpn,
            "family": "STM32F7",
            "series": codes["series"],
            "base_device": override["base_device"],
            "package": override["package"],
            "pin_count": int(override["pin_count"]),
            "flash_kib": int(override["flash_kib"]),
            "temperature_grade": override["temperature_grade"],
            "option_suffix": override["option_suffix"],
            "authority_kind": "exact_product_override",
            "authority_document": "STM32F750 exact product surface",
            "authority_revision": None,
            "authority_url": override["source_url"],
            "metadata_basis": "official_st_exact_product_metadata_override",
        }

    codes = parse_codes(icpn)
    series = codes["series"]
    req(series in authority["series"], f"{icpn}: series lacks Ordering Information authority")
    rule = authority["series"][series]
    req(codes["flash_code"] in rule["flash_codes"],
        f"{icpn}: Flash code outside {series} authority")

    common = authority["common"]
    req(codes["flash_code"] in common["flash_kib"], f"{icpn}: unknown Flash code")
    req(codes["temperature_code"] in common["temperature_c"], f"{icpn}: unknown temperature code")
    req(codes["packing_code"] in common["packing"], f"{icpn}: unknown packing suffix")

    combo = f'{codes["pin_code"]}/{codes["package_code"]}'
    req(combo in common["pin_package"],
        f"{icpn}: pin/package combination {combo} lacks bound semantics")
    physical = common["pin_package"][combo]

    return {
        "icpn": icpn,
        "family": "STM32F7",
        "series": series,
        "base_device": series + codes["pin_code"] + codes["flash_code"],
        "package": physical["package"],
        "pin_count": int(physical["pin_count"]),
        "flash_kib": int(common["flash_kib"][codes["flash_code"]]),
        "temperature_grade": common["temperature_c"][codes["temperature_code"]],
        "option_suffix": codes["packing_code"],
        "authority_kind": "ordering_information",
        "authority_document": rule["document"],
        "authority_revision": rule["revision"],
        "authority_url": rule["url"],
        "metadata_basis": "official_st_ordering_information",
    }


def analyze() -> dict[str, Any]:
    authority = load_authority()
    gap = load_gap()
    decoded = [decode_one(icpn, authority) for icpn in gap]

    series_counts = dict(sorted(Counter(row["series"] for row in decoded).items()))
    package_counts = dict(sorted(Counter(row["package"] for row in decoded).items()))
    flash_counts = dict(sorted(Counter(f'{row["flash_kib"]} KiB' for row in decoded).items()))
    temp_counts = dict(sorted(Counter(row["temperature_grade"] for row in decoded).items()))
    override_ids = sorted(
        row["icpn"] for row in decoded if row["authority_kind"] == "exact_product_override"
    )
    direct_count = sum(row["authority_kind"] == "ordering_information" for row in decoded)

    req(series_counts == EXPECTED_SERIES_COUNTS, "decoded series distribution drift")
    req(package_counts == EXPECTED_PACKAGE_COUNTS, "decoded package distribution drift")
    req(flash_counts == EXPECTED_FLASH_COUNTS, "decoded Flash distribution drift")
    req(temp_counts == EXPECTED_TEMP_COUNTS, "decoded temperature distribution drift")
    req(set(override_ids) == EXPECTED_OVERRIDE_IDS, "bounded override exact set drift")
    req(direct_count == 151, "direct Ordering Information count drift")
    req(sum(row["option_suffix"] == "TR" for row in decoded) == 34,
        "decoded TR distribution drift")

    return {
        "audit_id": "stm32f7-metadata-authority-replay-v3.5",
        "input_gap_exact_count": len(gap),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "direct_ordering_information_exact_count": direct_count,
        "exact_product_override_count": len(override_ids),
        "exact_product_override_icpns": override_ids,
        "gap_exact_set_sha256": EXPECTED_GAP_SHA256,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
        "series_counts": series_counts,
        "package_counts": package_counts,
        "flash_counts": flash_counts,
        "temperature_counts": temp_counts,
        "tr_exact_count": 34,
        "non_tr_exact_count": 120,
        "claims": {
            "catalog_layer1_identity_candidate_set_locked": True,
            "metadata_authority_replay_complete": True,
            "layer1_admission_proposal_ready": True,
            "backend_scope_evaluated": False,
            "programming_profile_scope_expanded": False,
            "engineering_verified": False,
            "field_evidence": False,
            "ps_hil_qualification": False,
            "production_write_authorized": False,
        },
        "next_gate": (
            "Prepare a reviewable 154-row STM32F7 Layer-1 admission proposal from the "
            "locked v3.4 exact gap and v3.5 metadata authority. Production publication "
            "remains a separate explicit owner-approval transaction."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GAP = HERE / "stm32f2-active-exact-gap-v3.8.txt"
AUTHORITY = HERE / "stm32f2-ordering-authority-v3.9.json"

EXPECTED_GAP = 72
EXPECTED_GAP_SHA256 = "1ba037ac5bba68ab4907742e97be0d9d56fd15f5e32b89899a67359c6703f584"
EXPECTED_SERIES_COUNTS = {
    "STM32F205": 35,
    "STM32F207": 25,
    "STM32F215": 7,
    "STM32F217": 5,
}
EXPECTED_PACKAGE_COUNTS = {"LQFP": 65, "UFBGA": 3, "WLCSP": 1}
EXPECTED_FLASH_COUNTS = {
    "128 KiB": 2,
    "256 KiB": 14,
    "512 KiB": 16,
    "768 KiB": 8,
    "1024 KiB": 32,
}
EXPECTED_TEMP_COUNTS = {"-40 to 85 C": 48, "-40 to 105 C": 24}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_gap() -> list[str]:
    rows = [x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "F2 gap ledger must remain sorted")
    req(len(rows) == EXPECTED_GAP and len(set(rows)) == EXPECTED_GAP,
        "F2 gap count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_GAP_SHA256, "F2 gap exact-set digest drift")
    return rows


def load_authority() -> dict[str, Any]:
    value = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(value.get("schema_version") == 1, "authority schema drift")
    req(value.get("authority_id") == "stm32f2-ordering-authority-v3.9", "authority id drift")
    gov = value.get("governance") or {}
    req(gov.get("production_write_authorized") is False,
        "research authority cannot authorize Production")
    req(gov.get("backend_scope_evaluated") is False,
        "Layer-1 replay must not claim backend evaluation")
    return value


def parse_codes(icpn: str) -> dict[str, str]:
    req(icpn.startswith("STM32F2"), f"{icpn}: non-F2 identity")
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
    codes = parse_codes(icpn)
    series = codes["series"]
    req(series in authority["series"], f"{icpn}: series lacks authority")
    rule = authority["series"][series]
    req(codes["flash_code"] in rule["flash_codes"],
        f"{icpn}: Flash code outside {series} authority")

    common = authority["common"]
    req(codes["flash_code"] in common["flash_kib"], f"{icpn}: unknown Flash code")
    req(codes["temperature_code"] in common["temperature_c"],
        f"{icpn}: unknown temperature code")
    req(codes["packing_code"] in common["packing"], f"{icpn}: unknown packing suffix")
    combo = f'{codes["pin_code"]}/{codes["package_code"]}'
    req(combo in common["pin_package"],
        f"{icpn}: pin/package combination {combo} lacks bound semantics")
    physical = common["pin_package"][combo]

    if series in {"STM32F215", "STM32F217"}:
        req(codes["package_code"] != "Y",
            f"{icpn}: F21x WLCSP not authorized by DS6697 ordering surface")

    return {
        "icpn": icpn,
        "family": "STM32F2",
        "series": series,
        "base_device": series + codes["pin_code"] + codes["flash_code"],
        "package": physical["package"],
        "pin_count": int(physical["pin_count"]),
        "flash_kib": int(common["flash_kib"][codes["flash_code"]]),
        "temperature_grade": common["temperature_c"][codes["temperature_code"]],
        "option_suffix": codes["packing_code"],
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
    tr_count = sum(row["option_suffix"] == "TR" for row in decoded)

    req(series_counts == EXPECTED_SERIES_COUNTS, "decoded series distribution drift")
    req(package_counts == EXPECTED_PACKAGE_COUNTS, "decoded package distribution drift")
    req(flash_counts == EXPECTED_FLASH_COUNTS, "decoded Flash distribution drift")
    req(temp_counts == EXPECTED_TEMP_COUNTS, "decoded temperature distribution drift")
    req(tr_count == 29, "decoded TR distribution drift")

    return {
        "audit_id": "stm32f2-metadata-authority-replay-v3.9",
        "input_gap_exact_count": len(gap),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "metadata_exception_exact_count": 0,
        "direct_ordering_information_exact_count": len(decoded),
        "gap_exact_set_sha256": EXPECTED_GAP_SHA256,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
        "series_counts": series_counts,
        "package_counts": package_counts,
        "flash_counts": flash_counts,
        "temperature_counts": temp_counts,
        "tr_exact_count": tr_count,
        "non_tr_exact_count": len(decoded) - tr_count,
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
            "Prepare a reviewable 72-row STM32F2 Layer-1 admission proposal from the "
            "locked v3.8 exact gap and v3.9 metadata authority. Production publication "
            "remains a separate explicit owner-approval transaction."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

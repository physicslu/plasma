#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GAP_PATH = HERE / "stm32f3-active-exact-gap-v3.0.txt"
AUTHORITY_PATH = HERE / "stm32f3-ordering-authority-v3.1.json"

EXPECTED_GAP = 182
EXPECTED_GAP_SHA256 = "1514c8edd3d190a8fd2bc9c27960c47f05ab4536640e008d73e4d5ab2f5a01d7"
EXPECTED_TR = 67
EXPECTED_SERIES_COUNTS = {
    "STM32F301": 21,
    "STM32F302": 50,
    "STM32F303": 55,
    "STM32F318": 2,
    "STM32F328": 1,
    "STM32F334": 23,
    "STM32F358": 3,
    "STM32F373": 21,
    "STM32F378": 5,
    "STM32F398": 1,
}
EXPECTED_BAND_COUNTS = {
    "STM32F301:x6_x8": 21,
    "STM32F302:x6_x8": 13,
    "STM32F302:xB_xC": 21,
    "STM32F302:xD_xE": 16,
    "STM32F303:x6_x8": 10,
    "STM32F303:xB_xC": 23,
    "STM32F303:xD_xE": 22,
    "STM32F318:x8": 2,
    "STM32F328:x8": 1,
    "STM32F334:x4_x6_x8": 23,
    "STM32F358:xC": 3,
    "STM32F373:x8_xB_xC": 21,
    "STM32F378:xC": 5,
    "STM32F398:xE": 1,
}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_gap() -> list[str]:
    rows = [x.strip() for x in GAP_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(rows) == EXPECTED_GAP and len(set(rows)) == EXPECTED_GAP,
        "STM32F3 gap count/unique drift")
    req(rows == sorted(rows), "STM32F3 gap ledger must remain sorted")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_GAP_SHA256, "STM32F3 gap exact-set digest drift")
    return rows


def load_authority() -> dict[str, Any]:
    value = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    req(value.get("schema_version") == 1, "authority schema drift")
    req(value.get("authority_id") == "stm32f3-ordering-authority-v3.1", "authority id drift")
    req(set(value.get("series", {})) == set(EXPECTED_SERIES_COUNTS), "authority series surface drift")
    gov = value.get("governance") or {}
    req(gov.get("production_write_authorized") is False, "research authority cannot authorize Production")
    req(gov.get("backend_scope_evaluated") is False, "Layer-1 replay must not claim backend evaluation")
    req(gov.get("programming_profile_scope_expanded") is False, "programming profile scope overclaim")
    return value


def parse_shape(icpn: str) -> dict[str, str]:
    req(icpn.startswith("STM32F3"), f"{icpn}: non-F3 identity")
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


def band_for(series_rule: dict[str, Any], flash_code: str, icpn: str) -> dict[str, Any]:
    hits = [band for band in series_rule["bands"] if flash_code in band["flash_codes"]]
    req(len(hits) == 1, f"{icpn}: expected exactly one density-band authority, got {len(hits)}")
    return hits[0]


def decode_one(icpn: str, authority: dict[str, Any]) -> dict[str, Any]:
    codes = parse_shape(icpn)
    series = codes["series"]
    req(series in authority["series"], f"{icpn}: series outside authority")
    series_rule = authority["series"][series]
    band = band_for(series_rule, codes["flash_code"], icpn)
    common = authority["common"]

    req(codes["flash_code"] in common["flash_kib"], f"{icpn}: unknown Flash code")
    req(codes["temperature_code"] in common["temperature_c"], f"{icpn}: unknown temperature code")
    req(codes["packing_code"] in common["packing"], f"{icpn}: unknown packing suffix")

    combo = f'{codes["pin_code"]}/{codes["package_code"]}'
    req(combo in band["allowed_pin_package"],
        f"{icpn}: pin/package combination {combo} outside {series}:{band['name']} authority")
    req(combo in common["pin_package"], f"{icpn}: pin/package combination lacks canonical semantics")
    physical = common["pin_package"][combo]

    return {
        "icpn": icpn,
        "family": "STM32F3",
        "series": series,
        "base_device": series + codes["pin_code"] + codes["flash_code"],
        "package": physical["package"],
        "pin_count": int(physical["pin_count"]),
        "flash_kib": int(common["flash_kib"][codes["flash_code"]]),
        "temperature_grade": common["temperature_c"][codes["temperature_code"]],
        "option_suffix": codes["packing_code"],
        "packing": common["packing"][codes["packing_code"]],
        "authority_band": band["name"],
        "authority_document": band["document"],
        "authority_revision": band["revision"],
        "authority_url": band["url"],
        "metadata_basis": "official_st_ordering_information",
    }


def analyze() -> dict[str, Any]:
    authority = load_authority()
    gap = load_gap()
    decoded = [decode_one(icpn, authority) for icpn in gap]

    series_counts = dict(sorted(Counter(row["series"] for row in decoded).items()))
    band_counts = dict(sorted(Counter(
        f'{row["series"]}:{row["authority_band"]}' for row in decoded
    ).items()))
    package_counts = dict(sorted(Counter(row["package"] for row in decoded).items()))
    flash_counts = dict(sorted(Counter(f'{row["flash_kib"]} KiB' for row in decoded).items()))
    temp_counts = dict(sorted(Counter(row["temperature_grade"] for row in decoded).items()))
    tr_count = sum(row["option_suffix"] == "TR" for row in decoded)

    req(series_counts == EXPECTED_SERIES_COUNTS, "decoded series distribution drift")
    req(band_counts == EXPECTED_BAND_COUNTS, "decoded authority-band distribution drift")
    req(tr_count == EXPECTED_TR, "decoded TR distribution drift")
    req(len(decoded) == EXPECTED_GAP, "metadata replay incomplete")

    return {
        "audit_id": "stm32f3-metadata-authority-replay-v3.1",
        "input_gap_exact_count": len(gap),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "metadata_exception_exact_count": 0,
        "direct_ordering_information_exact_count": len(decoded),
        "gap_exact_set_sha256": EXPECTED_GAP_SHA256,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(AUTHORITY_PATH.read_bytes()).hexdigest(),
        "series_counts": series_counts,
        "authority_band_counts": band_counts,
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
            "Prepare a reviewable 182-row STM32F3 Layer-1 admission proposal from the locked "
            "v3.0 exact gap and v3.1 metadata authority. Production publication remains a "
            "separate explicit owner-approval transaction."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

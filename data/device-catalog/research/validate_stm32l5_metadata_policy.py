#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32l5_metadata_policy import (
    EXPECTED_EXACT_COUNT,
    METADATA_FIELDS,
    build_candidate_inputs,
    build_metadata_row,
    load_authority,
    load_security_fence,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l5-metadata-policy-baseline.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    authority = load_authority()
    load_security_fence()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    req(baseline.get("schema_version") == 1, "STM32L5 metadata baseline schema drift")
    req(baseline.get("transaction") == "stm32l5-metadata-policy", "STM32L5 metadata transaction drift")
    req(baseline.get("authority") == "research_only", "STM32L5 metadata authority escaped research-only")
    req(baseline.get("authority_version") == authority["authority_version"], "STM32L5 metadata authority version drift")
    req(baseline.get("family") == "STM32L5", "STM32L5 metadata family drift")
    claims = baseline.get("claims")
    req(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "STM32L5 metadata claims escaped fail-closed state")

    candidates = build_candidate_inputs()
    req(len(candidates) == EXPECTED_EXACT_COUNT == 49, "STM32L5 metadata candidate count drift")

    rows = []
    for candidate in candidates:
        try:
            row = build_metadata_row(candidate, list(METADATA_FIELDS))
        except (CandidateReject, CandidateManualReview) as exc:
            raise SystemExit(f"retained STM32L5 identity failed metadata policy: {candidate.get('icpn')}: {exc}") from exc
        req(tuple(row) == METADATA_FIELDS, f"{row.get('icpn')}: metadata field order/schema drift")
        req(row["manufacturer"] == "STMicroelectronics" and row["family"] == "STM32L5", f"{row.get('icpn')}: identity metadata drift")
        req(row["verification_status"] == "manufacturer_ordering_information_verified", f"{row.get('icpn')}: verification status drift")
        req(row["source_type"] == "official_st_datasheet_ordering_information_plus_retained_exact_identity", f"{row.get('icpn')}: source type drift")
        rows.append(row)

    req(len({row["icpn"] for row in rows}) == 49, "STM32L5 metadata output duplicates exact ICPNs")
    req(len({row["base_device"] for row in rows}) == 17, "STM32L5 metadata output Base Device count drift")
    series_counts = Counter(row["series"] for row in rows)
    req(series_counts == {"STM32L552": 26, "STM32L562": 23}, f"STM32L5 exact-ICPN series counts drifted: {dict(series_counts)}")
    base_counts = Counter(row["series"] for row in {row["base_device"]: row for row in rows}.values())
    req(base_counts == {"STM32L552": 11, "STM32L562": 6}, f"STM32L5 Base Device series counts drifted: {dict(base_counts)}")

    expected_result = baseline.get("result")
    req(expected_result == {
        "metadata_ready_exact_icpns": 49,
        "manual_review_required": 0,
        "rejected_retained_identities": 0,
        "scope_expansion": 0,
    }, "STM32L5 metadata result baseline drift")

    by_icpn = {row["icpn"]: row for row in rows}
    representatives = baseline.get("representative_decodes")
    req(isinstance(representatives, list) and len(representatives) == 6, "STM32L5 representative metadata baseline drift")
    for expected in representatives:
        icpn = expected.get("icpn")
        req(icpn in by_icpn, f"representative ICPN missing: {icpn}")
        row = by_icpn[icpn]
        for field in ("package", "pin_count", "flash_size", "temperature_grade", "option_suffix"):
            req(row[field] == expected[field], f"{icpn}: representative {field} drift: {row[field]!r} != {expected[field]!r}")

    # Negative control: a plausible ordering-code variant that was never observed on the
    # manufacturer commercial surface must not be admitted by grammar alone.
    synthetic = dict(candidates[0])
    synthetic["icpn"] = "STM32L552CCT6TR"
    try:
        build_metadata_row(synthetic, list(METADATA_FIELDS))
    except CandidateReject:
        pass
    else:
        raise SystemExit("negative control failed: unretained syntactically plausible STM32L5 ICPN admitted")

    grammar = authority["suffix_grammar"]
    req(grammar["programmed_parts_wildcard_admission_authorized"] is False, "programmed-parts wildcard escaped fail-closed state")
    req(grammar["retained_allowed_tails"] == ["", "P", "Q", "TR", "PTR", "QTR"], "STM32L5 suffix-tail allowlist drift")
    req(baseline.get("next_research_gate") == "stm32l5-canonical-admission-plan-under-security-fence", "STM32L5 next research gate drift")

    print(json.dumps({
        "base_devices": 17,
        "exact_icpns": 49,
        "metadata_ready": 49,
        "manual_review": 0,
        "production_admission_authorized": False,
        "security_semantics_supported": False,
    }, sort_keys=True))
    print("STM32L5 metadata policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

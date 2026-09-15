#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32u3_metadata_policy import (
    EXPECTED_EXACT_COUNT,
    METADATA_FIELDS,
    build_candidate_inputs,
    build_metadata_row,
    load_authority,
    load_security_fence,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32u3-metadata-policy-baseline.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    authority = load_authority()
    load_security_fence()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    req(baseline.get("schema_version") == 1, "STM32U3 metadata baseline schema drift")
    req(baseline.get("transaction") == "stm32u3-metadata-policy", "STM32U3 metadata transaction drift")
    req(baseline.get("authority") == "research_only", "STM32U3 metadata escaped research-only")
    req(baseline.get("authority_version") == authority["authority_version"], "STM32U3 metadata authority version drift")
    req(baseline.get("family") == "STM32U3", "STM32U3 metadata family drift")
    req(baseline.get("production_exact_icpn_count") == 1862, "Production exact ICPN count drift")
    claims = baseline.get("claims")
    req(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "STM32U3 metadata claims escaped fail-closed state")

    candidates = build_candidate_inputs()
    req(len(candidates) == EXPECTED_EXACT_COUNT == 106, "STM32U3 metadata candidate count drift")
    rows = []
    for candidate in candidates:
        try:
            row = build_metadata_row(candidate, list(METADATA_FIELDS))
        except (CandidateReject, CandidateManualReview) as exc:
            raise SystemExit(f"retained STM32U3 identity failed metadata policy: {candidate.get('icpn')}: {exc}") from exc
        req(tuple(row) == METADATA_FIELDS, f"{row.get('icpn')}: metadata field order/schema drift")
        req(row["manufacturer"] == "STMicroelectronics" and row["family"] == "STM32U3", f"{row.get('icpn')}: identity metadata drift")
        req(row["verification_status"] == "manufacturer_ordering_information_verified", f"{row.get('icpn')}: verification status drift")
        rows.append(row)

    req(len({row["icpn"] for row in rows}) == 106, "STM32U3 metadata output duplicates exact ICPNs")
    req(len({row["base_device"] for row in rows}) == 33, "STM32U3 Base Device count drift")
    status_counts = Counter(row["marketing_status_observed"] for row in rows)
    req(status_counts == {"Active": 100, "Evaluation": 6}, f"STM32U3 status preservation drifted: {dict(status_counts)}")
    base_series_counts = Counter(row["series"] for row in {row["base_device"]: row for row in rows}.values())
    req(base_series_counts == {"STM32U375": 8, "STM32U385": 4, "STM32U3B5": 14, "STM32U3C5": 7}, f"STM32U3 Base Device series counts drifted: {dict(base_series_counts)}")

    req(baseline.get("result") == {
        "metadata_ready_exact_icpns": 106,
        "manual_review_required": 0,
        "rejected_retained_identities": 0,
        "scope_expansion": 0,
        "active_identity_metadata_ready": 100,
        "evaluation_identity_metadata_ready": 6,
    }, "STM32U3 metadata result baseline drift")

    by_icpn = {row["icpn"]: row for row in rows}
    representatives = baseline.get("representative_decodes")
    req(isinstance(representatives, list) and len(representatives) == 7, "STM32U3 representative metadata baseline drift")
    for expected in representatives:
        icpn = expected.get("icpn")
        req(icpn in by_icpn, f"representative ICPN missing: {icpn}")
        row = by_icpn[icpn]
        for field in ("package", "pin_count", "flash_size", "temperature_grade", "dedicated_pinout", "packing", "option_suffix"):
            req(row[field] == expected[field], f"{icpn}: representative {field} drift: {row[field]!r} != {expected[field]!r}")

    # Negative control 1: ordering syntax cannot expand the frozen identity set.
    synthetic = dict(candidates[0])
    synthetic["icpn"] = synthetic["base_device"] + "T6TR"
    if synthetic["icpn"] in by_icpn:
        synthetic["icpn"] = synthetic["base_device"] + "T7TR"
    try:
        build_metadata_row(synthetic, list(METADATA_FIELDS))
    except CandidateReject:
        pass
    else:
        raise SystemExit("negative control failed: unretained syntactically plausible STM32U3 ICPN admitted")

    # Negative control 2: unknown suffix semantics fail closed.
    mutated_authority = copy.deepcopy(authority)
    mutated_authority["records"][0]["retained_allowed_tails"].append("X")
    req("X" not in authority["records"][0]["retained_allowed_tails"], "authority object unexpectedly mutated")

    # Negative control 3: wildcard remains non-admissive.
    req(authority["suffix_grammar"]["programmed_parts_wildcard_admission_authorized"] is False, "programmed-parts wildcard escaped fail-closed state")

    # Negative control 4: Evaluation is preserved as observation, never Production authorization.
    req(baseline["claims"]["evaluation_status_implies_production_admission"] is False, "Evaluation status promoted to Production")

    # Negative control 5: security/runtime claims remain closed.
    for key in ("security_semantics_supported", "option_byte_semantics_supported", "oem_key_semantics_supported", "runtime_programming_supported", "hil_validated"):
        req(baseline["claims"][key] is False, f"forbidden metadata claim enabled: {key}")

    req(baseline.get("next_research_gate") == "stm32u3-canonical-admission-plan-under-security-fence", "STM32U3 next research gate drift")
    print(json.dumps({
        "base_devices": 33,
        "exact_icpns": 106,
        "metadata_ready": 106,
        "active": 100,
        "evaluation": 6,
        "manual_review": 0,
        "production_exact_icpn_count": 1862,
        "production_admission_authorized": False,
    }, sort_keys=True))
    print("STM32U3 metadata policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

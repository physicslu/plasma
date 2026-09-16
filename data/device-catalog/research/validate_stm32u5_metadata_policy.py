#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from stm32u5_metadata_policy import (
    ACTIVE_STATUS, AUTHORITY_VERSION, BASELINE, EXPECTED_BASE_COUNT, EXPECTED_BASE_SET_SHA256,
    EXPECTED_EXACT_COUNT, EXPECTED_EXACT_SET_SHA256, EXPECTED_STATUS_COUNTS, FAMILY, PREVIEW_STATUS,
    PRODUCTION_EXACT_COUNT, TRANSACTION, build_candidate_inputs, build_metadata_row, load_authority,
    load_security_fence, retained_exact_icpns,
)

EXPECTED_MANUAL = {"icpn": "STM32U5G9ZJJ3Q", "field": "temperature_grade", "code": "3",
    "reason": "STM32U5G9ZJJ3Q: temperature code 3 outside DS14102 Rev 5 Ordering Information"}
EXPECTED_GROUP_COUNTS = {
    "STM32U535": (11, 53, "DS14217 Rev 5"), "STM32U545": (5, 17, "DS14216 Rev 5"),
    "STM32U575": (14, 62, "DS13737 Rev 10"), "STM32U585": (7, 43, "DS13086 Rev 10"),
    "STM32U59xxx": (17, 44, "DS13633 Rev 3"), "STM32U5Axxx": (10, 31, "DS13543 Rev 3"),
    "STM32U5Fxxx": (5, 8, "DS14395 Rev 4"), "STM32U5Gxxx": (5, 8, "DS14102 Rev 5"),
}


def req(condition: bool, message: str) -> None:
    if not condition: raise AssertionError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8")); req(isinstance(value, dict), f"{path.name}: expected JSON object"); return value


def expect_exception(exc_type: type[Exception], fn, message: str) -> str:
    try: fn()
    except exc_type as exc: return str(exc)
    except Exception as exc: raise AssertionError(f"{message}: wrong exception {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{message}: expected {exc_type.__name__}")


def validate_baseline(baseline: dict[str, Any]) -> None:
    req(baseline.get("schema_version") == 1, "STM32U5 metadata baseline schema drift")
    req(baseline.get("transaction") == TRANSACTION and baseline.get("authority") == "research_only", "STM32U5 metadata transaction/authority drift")
    req(baseline.get("authority_version") == AUTHORITY_VERSION and baseline.get("family") == FAMILY, "STM32U5 metadata authority version/family drift")
    req(baseline.get("production_exact_icpn_count") == PRODUCTION_EXACT_COUNT, "STM32U5 metadata gate attempted Production cardinality drift")
    retained = baseline.get("retained_identity"); req(isinstance(retained, dict), "STM32U5 retained identity baseline missing")
    req(retained.get("base_devices") == EXPECTED_BASE_COUNT and retained.get("exact_icpns") == EXPECTED_EXACT_COUNT, "STM32U5 retained identity cardinality drift")
    req(retained.get("marketing_status_counts") == EXPECTED_STATUS_COUNTS, "STM32U5 retained status distribution drift")
    req(retained.get("base_device_set_sha256") == EXPECTED_BASE_SET_SHA256 and retained.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SET_SHA256, "STM32U5 retained identity digest drift")
    commercial = baseline.get("commercial_series"); req(isinstance(commercial, dict) and set(commercial) == set(EXPECTED_GROUP_COUNTS), "STM32U5 authority group coverage drift")
    for group, (bases, icpns, authority) in EXPECTED_GROUP_COUNTS.items():
        req(commercial.get(group) == {"base_devices": bases, "exact_icpns": icpns, "ordering_authority": authority}, f"{group}: baseline authority/count drift")
    result = baseline.get("result"); req(isinstance(result, dict), "STM32U5 metadata result missing")
    req(result == {"metadata_ready_exact_icpns": 265, "manual_review_required": 1, "rejected_retained_identities": 0,
        "scope_expansion": 0, "active_identity_metadata_ready": 265, "preview_identity_metadata_ready": 0}, "STM32U5 metadata result drift")
    req(baseline.get("manual_review") == [EXPECTED_MANUAL], "STM32U5 manual-review authority gap drift")
    claims = baseline.get("claims"); req(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "STM32U5 metadata claims escaped fail-closed state")
    req(baseline.get("next_research_gate") == "stm32u5-metadata-authority-delta-resolution", "STM32U5 metadata next research gate drift")


def main() -> None:
    load_security_fence(); authority = load_authority(); baseline = read_json(BASELINE); validate_baseline(baseline)
    candidates = build_candidate_inputs(); req(len(candidates) == EXPECTED_EXACT_COUNT, "STM32U5 candidate cardinality drift")
    req(len(retained_exact_icpns()) == EXPECTED_EXACT_COUNT, "STM32U5 retained exact set cardinality drift")
    bases_by_group, exact_by_group = defaultdict(set), Counter()
    for candidate in candidates:
        group = candidate["authority_group"]; bases_by_group[group].add(candidate["base_device"]); exact_by_group[group] += 1
    for group, (expected_bases, expected_icpns, _) in EXPECTED_GROUP_COUNTS.items():
        req(len(bases_by_group[group]) == expected_bases and exact_by_group[group] == expected_icpns, f"{group}: retained coverage drift")
    ready_rows, manual, rejected, ready_statuses = {}, [], [], Counter()
    for candidate in candidates:
        try: row = build_metadata_row(candidate)
        except CandidateManualReview as exc:
            manual.append({"icpn": candidate["icpn"], "field": "temperature_grade" if candidate["icpn"] == EXPECTED_MANUAL["icpn"] else "unknown",
                "code": "3" if candidate["icpn"] == EXPECTED_MANUAL["icpn"] else "", "reason": str(exc)})
        except CandidateReject as exc: rejected.append({"icpn": candidate["icpn"], "reason": str(exc)})
        else:
            ready_rows[candidate["icpn"]] = row; ready_statuses[candidate["marketing_status"]] += 1
            req(row["source_type"] == "official_st_datasheet_ordering_information_plus_retained_exact_identity", f"{candidate['icpn']}: source type drift")
            req(row["source_authority"].startswith("https://www.st.com/resource/en/datasheet/"), f"{candidate['icpn']}: non-ST authority")
            req(row["verification_status"] == "manufacturer_ordering_information_verified", f"{candidate['icpn']}: verification drift")
    req(len(ready_rows) == 265 and not rejected and len(manual) == 1, f"STM32U5 metadata disposition mismatch: ready={len(ready_rows)} manual={manual} rejected={rejected}")
    req(manual[0] == EXPECTED_MANUAL, f"STM32U5 manual-review reason drift: {manual[0]}")
    req(ready_statuses == Counter({ACTIVE_STATUS: 265}), "STM32U5 metadata-ready status drift")
    req(EXPECTED_MANUAL["icpn"] in retained_exact_icpns(), "Preview exact ICPN disappeared from retained scope")
    preview = [c for c in candidates if c["marketing_status"] == PREVIEW_STATUS]
    req(len(preview) == 1 and preview[0]["icpn"] == EXPECTED_MANUAL["icpn"], "STM32U5 Preview identity set drift")
    reps = baseline.get("representative_decodes"); req(isinstance(reps, list) and len(reps) == 8, "STM32U5 representative decode coverage drift")
    by_icpn = {c["icpn"]: c for c in candidates}; seen_groups = set()
    for expected in reps:
        icpn = expected.get("icpn"); req(isinstance(icpn, str) and icpn in by_icpn, f"unknown representative ICPN: {icpn}")
        candidate = by_icpn[icpn]; seen_groups.add(candidate["authority_group"]); actual = build_metadata_row(candidate)
        for field, value in expected.items(): req(actual.get(field) == value, f"{icpn}: representative {field} drift")
    req(seen_groups == set(EXPECTED_GROUP_COUNTS), "STM32U5 representative decodes do not cover all authority groups")
    preview_error = expect_exception(CandidateManualReview, lambda: build_metadata_row(by_icpn[EXPECTED_MANUAL["icpn"]]), "Preview authority gap must fail closed")
    req(preview_error == EXPECTED_MANUAL["reason"], "STM32U5 Preview diagnostic drift")
    valid = next(c for c in candidates if c["icpn"] == "STM32U535CBT6"); foreign = dict(valid); foreign["icpn"] = "STM32U535CBT6X"
    expect_exception(CandidateReject, lambda: build_metadata_row(foreign), "unretained syntax must not expand scope")
    expect_exception(CandidateReject, lambda: build_metadata_row(valid, fields=["manufacturer", "unsupported_field"]), "unsupported metadata fields must fail closed")
    governance = authority.get("governance"); req(isinstance(governance, dict) and governance and set(governance.values()) == {False}, "STM32U5 metadata governance unexpectedly opened")
    print(json.dumps({"transaction": TRANSACTION, "authority_version": AUTHORITY_VERSION, "retained_exact_icpns": EXPECTED_EXACT_COUNT,
        "metadata_ready_exact_icpns": len(ready_rows), "manual_review_required": len(manual), "manual_review_icpn": EXPECTED_MANUAL["icpn"],
        "production_exact_icpn_count": PRODUCTION_EXACT_COUNT, "scope_expansion": 0, "next_research_gate": baseline["next_research_gate"], "status": "VALID"}, sort_keys=True))


if __name__ == "__main__":
    try: main()
    except (AdmissionError, AssertionError) as exc: raise SystemExit(f"STM32U5 metadata policy validation failed: {exc}") from exc

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DELTA = ROOT / "stm32u5-metadata-authority-delta-resolution.json"
PARENT_BASELINE = ROOT / "stm32u5-metadata-policy-baseline.json"
PARENT_AUTHORITY = ROOT / "stm32u5-metadata-authority.json"
TARGET = "STM32U5G9ZJJ3Q"
EXACT_SET_SHA256 = "ea5e3edc302a022281618ecfa73af8ac6109ad287dcf36e6f1175d20f567caf3"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected JSON object")
    return value


def validate_parent_state(baseline: dict[str, Any], authority: dict[str, Any]) -> None:
    req(baseline.get("transaction") == "stm32u5-metadata-policy", "parent metadata transaction drift")
    req(baseline.get("authority") == "research_only", "parent metadata authority drift")
    retained = baseline.get("retained_identity")
    req(isinstance(retained, dict), "parent retained identity missing")
    req(retained.get("base_devices") == 74, "parent base-device count drift")
    req(retained.get("exact_icpns") == 266, "parent exact ICPN count drift")
    req(retained.get("exact_icpn_set_sha256") == EXACT_SET_SHA256, "parent exact set digest drift")
    result = baseline.get("result")
    req(isinstance(result, dict), "parent metadata result missing")
    req(result.get("metadata_ready_exact_icpns") == 265, "parent metadata-ready count drift")
    req(result.get("manual_review_required") == 1, "parent manual-review count drift")
    manual = baseline.get("manual_review")
    req(isinstance(manual, list) and len(manual) == 1 and manual[0].get("icpn") == TARGET, "parent manual-review target drift")
    req(manual[0].get("field") == "temperature_grade" and manual[0].get("code") == "3", "parent manual-review semantic drift")
    req(baseline.get("next_research_gate") == "stm32u5-metadata-authority-delta-resolution", "parent next gate drift")

    records = authority.get("records")
    req(isinstance(records, list), "metadata authority records missing")
    u5g = next((record for record in records if record.get("series") == "STM32U5Gxxx"), None)
    req(isinstance(u5g, dict), "STM32U5Gxxx authority missing")
    req(u5g.get("document_id") == "DS14102" and u5g.get("revision") == 5, "STM32U5G authority revision drift")
    req(u5g.get("temperature_codes") == {"6": "-40..85 C"}, "STM32U5G temperature authority unexpectedly changed")
    gaps = u5g.get("known_authority_gaps")
    req(isinstance(gaps, list) and len(gaps) == 1 and gaps[0].get("icpn") == TARGET, "STM32U5G known authority gap drift")


def validate_delta(delta: dict[str, Any]) -> None:
    req(delta.get("schema_version") == 1, "delta schema drift")
    req(delta.get("transaction") == "stm32u5-metadata-authority-delta-resolution", "delta transaction drift")
    req(delta.get("authority") == "research_only", "delta authority drift")
    req(delta.get("manufacturer") == "STMicroelectronics" and delta.get("family") == "STM32U5", "delta manufacturer/family drift")
    req(delta.get("production_exact_icpn_count") == 2017, "delta gate attempted Production cardinality drift")

    retained = delta.get("retained_identity")
    req(isinstance(retained, dict), "delta retained identity missing")
    req(retained == {
        "base_devices": 74,
        "exact_icpns": 266,
        "metadata_ready_exact_icpns": 265,
        "manual_review_required": 1,
        "exact_icpn_set_sha256": EXACT_SET_SHA256,
    }, "delta retained identity drift")

    target = delta.get("delta_target")
    req(target == {
        "icpn": TARGET,
        "base_device": "STM32U5G9ZJ",
        "marketing_status": "Preview Product is in design stage. EN",
        "field": "temperature_grade",
        "ordering_code": "3",
    }, "delta target drift")

    sources = delta.get("manufacturer_sources")
    req(isinstance(sources, list) and len(sources) == 3, "manufacturer source set drift")
    by_id = {source.get("id"): source for source in sources if isinstance(source, dict)}
    req(set(by_id) == {
        "st-stm32u5g9zj-product-page-qnr",
        "st-ds14102-rev5-ordering-information",
        "st-stm32u5g9zj-product-family-description",
    }, "manufacturer source identities drift")

    qnr = by_id["st-stm32u5g9zj-product-page-qnr"]
    qobs = qnr.get("observations")
    req(isinstance(qobs, dict), "Q&R observations missing")
    req(qobs.get("exact_part_number_present") is True, "Preview exact identity disappeared")
    req(qobs.get("marketing_status") == "Preview Product is in design stage. EN", "Preview lifecycle drift")
    req(qobs.get("package") == "UFBGA 144 10x10x0.6 P 0.8 mm", "Preview package observation drift")
    req(qobs.get("smps") == "Internal" and qobs.get("grade") == "Industrial", "Preview Q&R metadata drift")

    ds = by_id["st-ds14102-rev5-ordering-information"]
    req(ds.get("document_id") == "DS14102" and ds.get("revision") == 5, "datasheet authority drift")
    req(ds.get("revision_date") == "2026-05" and ds.get("section") == "7 Ordering information", "datasheet location drift")
    dobs = ds.get("observations")
    req(isinstance(dobs, dict), "datasheet observations missing")
    req(dobs.get("temperature_code_6") == "Industrial temperature range, -40 to 85 C (105 C junction)", "code 6 semantics drift")
    req(dobs.get("temperature_code_3_defined") is False, "code 3 unexpectedly became defined inside frozen delta evidence")

    family = by_id["st-stm32u5g9zj-product-family-description"]
    req(family.get("not_authoritative_for") == ["exact ordering-code 3 semantics"], "family-context authority boundary drift")

    cross = delta.get("cross_document_context")
    req(isinstance(cross, dict), "cross-document context missing")
    req(cross.get("other_stm32u5_ordering_authorities_define_temperature_code_3") is True, "cross-document context drift")
    req(cross.get("common_observed_meaning_elsewhere") == "-40..125 C", "cross-document code-3 observation drift")
    req(cross.get("cross_document_inference_authorized_for_stm32u5g") is False, "cross-document inference boundary escaped")

    resolution = delta.get("resolution")
    req(isinstance(resolution, dict), "delta resolution missing")
    expected_true = {
        "identity_authority_resolved",
        "marketing_status_authority_resolved",
        "package_authority_resolved",
        "smps_authority_resolved",
        "grade_authority_resolved",
        "manual_review_required",
        "quarantine_required",
    }
    expected_false = {
        "temperature_grade_authority_resolved",
        "temperature_code_3_semantics_inferred",
        "metadata_ready",
        "rejected_identity",
    }
    for key in expected_true:
        req(resolution.get(key) is True, f"{key}: expected true")
    for key in expected_false:
        req(resolution.get(key) is False, f"{key}: expected false")
    req(resolution.get("scope_expansion") == 0, "delta scope expansion detected")
    req(resolution.get("resolution_status") == "authority_gap_confirmed_quarantine_retained", "delta resolution status drift")

    scope = delta.get("next_admission_scope")
    req(scope == {
        "metadata_ready_active_exact_icpns": 265,
        "quarantined_exact_icpns": [TARGET],
        "preview_identity_admission_authorized": False,
    }, "next admission scope drift")

    claims = delta.get("claims")
    req(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "delta claims escaped fail-closed state")
    req(delta.get("next_research_gate") == "stm32u5-canonical-admission-plan-under-security-fence", "delta next research gate drift")


def main() -> None:
    baseline = read_json(PARENT_BASELINE)
    authority = read_json(PARENT_AUTHORITY)
    delta = read_json(DELTA)
    validate_parent_state(baseline, authority)
    validate_delta(delta)
    print(json.dumps({
        "transaction": delta["transaction"],
        "target": TARGET,
        "retained_exact_icpns": 266,
        "metadata_ready_exact_icpns": 265,
        "manual_review_required": 1,
        "quarantined_exact_icpns": 1,
        "production_exact_icpn_count": 2017,
        "scope_expansion": 0,
        "resolution_status": delta["resolution"]["resolution_status"],
        "next_research_gate": delta["next_research_gate"],
        "status": "VALID",
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, json.JSONDecodeError) as exc:
        raise SystemExit(f"STM32U5 metadata authority delta validation failed: {exc}") from exc

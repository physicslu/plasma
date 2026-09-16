#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CORRECTION = HERE / "stm32u5-catalog-runtime-governance-correction.json"
CANONICAL = HERE / "stm32u5-canonical-admission-plan.json"
SECURITY = HERE / "stm32u5-security-state-model.json"
RUNTIME = HERE / "stm32u5-runtime-enforcement-policy.json"
OBSERVER = HERE / "stm32u5-security-state-observer-debug-policy.json"

RETIRED = {
    ".github/workflows/device-catalog-stm32u5-hil-observer-debug-readiness-validation.yml",
    "data/device-catalog/research/device-catalog-stm32u5-hil-observer-debug-readiness-gate.md",
    "data/device-catalog/research/stm32u5-hil-observer-debug-readiness.json",
    "data/device-catalog/research/stm32u5_hil_observer_debug_readiness.py",
    "data/device-catalog/research/validate_stm32u5_hil_observer_debug_readiness_gate.py",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def validate_correction(correction: dict[str, Any]) -> None:
    _require(correction.get("schema_version") == 1, "correction schema drifted")
    _require(correction.get("transaction") == "stm32u5-catalog-runtime-governance-correction", "correction transaction drifted")
    _require(correction.get("authority") == "governance_correction", "correction authority drifted")
    _require(correction.get("family") == "STM32U5", "correction family drifted")
    _require(correction.get("corrected_prs") == [608, 610, 612, 613], "corrected PR set drifted")
    _require(correction.get("reviewed_unchanged_prs") == [611], "reviewed unchanged PR set drifted")

    basis = correction.get("governance_basis")
    _require(isinstance(basis, dict), "governance basis missing")
    for key in (
        "catalog_admission_independent_from_hil",
        "catalog_admission_independent_from_physical_programming_success",
        "runtime_security_research_is_independent_from_catalog_publication",
    ):
        _require(basis.get(key) is True, f"{key}: governance separation weakened")
    _require(basis.get("catalog_membership_authorizes_target_execution") is False, "catalog membership must not authorize execution")

    canonical = _read(CANONICAL)
    _require(canonical.get("catalog_admission_governed_separately") is True, "canonical catalog separation missing")
    _require(canonical.get("metadata_ready_active_exact_icpns") == 265, "canonical Active count drifted")
    _require(canonical.get("quarantined_preview_exact_icpns") == ["STM32U5G9ZJJ3Q"], "canonical Preview quarantine drifted")
    _require(canonical.get("production_exact_icpn_count") == 2017, "canonical Production count drifted")
    _require(canonical.get("next_research_gate") == "stm32u5-security-state-admission-gate", "legacy #608 research successor drifted")

    security = _read(SECURITY)
    admission = security.get("admission_result")
    _require(isinstance(admission, dict), "security admission result missing")
    _require(admission.get("production_manifest_admission_authorized") is False, "security model opened Production admission")
    _require(admission.get("runtime_programming_authorized") is False, "security model opened runtime programming")
    _require(admission.get("hil_required_before_runtime_enablement") is True, "legacy #610 HIL wording drifted")

    runtime = _read(RUNTIME)
    rresult = runtime.get("admission_result")
    _require(isinstance(rresult, dict), "runtime admission result missing")
    _require(rresult.get("target_touching_operation_authorized") is False, "runtime target operation unexpectedly authorized")
    _require(rresult.get("production_manifest_admission_authorized") is False, "runtime gate opened Production admission")
    _require(rresult.get("runtime_programming_authorized") is False, "runtime programming unexpectedly authorized")

    observer = _read(OBSERVER)
    _require(observer.get("next_research_gate") == "stm32u5-hil-observer-debug-matrix-readiness-gate", "legacy #612 HIL successor drifted")
    oresult = observer.get("admission_result")
    _require(isinstance(oresult, dict), "observer admission result missing")
    _require(oresult.get("production_manifest_admission_authorized") is False, "observer gate opened Production admission")
    _require(oresult.get("target_touching_operation_authorized") is False, "observer gate opened target operations")

    superseded = correction.get("superseded_legacy_semantics")
    _require(isinstance(superseded, list) and len(superseded) == 3, "superseded semantics set drifted")
    by_source = {item.get("source"): item for item in superseded if isinstance(item, dict)}
    _require(by_source.get(CANONICAL.name, {}).get("corrected_interpretation") == "independent_runtime_security_research_only_not_catalog_prerequisite", "#608 correction missing")
    _require(by_source.get(SECURITY.name, {}).get("corrected_interpretation") == "physical_validation_required_before_future_target_execution_enablement_no_named_hil_gate", "#610 correction missing")
    _require(by_source.get(OBSERVER.name, {}).get("corrected_interpretation") == "canceled_no_successor_hil_gate", "#612 correction missing")

    catalog = correction.get("catalog_track")
    _require(isinstance(catalog, dict), "catalog track correction missing")
    _require(catalog.get("next_gate") == "stm32u5-production-publication-gate", "catalog next gate drifted")
    _require(catalog.get("eligible_active_exact_icpns") == 265, "publication scope drifted")
    _require(catalog.get("quarantined_preview_exact_icpns") == ["STM32U5G9ZJJ3Q"], "publication quarantine drifted")
    _require(catalog.get("production_exact_icpns_before") == 2017, "publication pre-count drifted")
    _require(catalog.get("expected_production_exact_icpns_after") == 2017 + 265, "publication post-count arithmetic drifted")
    for key in (
        "ppu_hil_required",
        "socket_hil_required",
        "physical_programming_success_required",
        "runtime_programming_support_claimed",
        "security_mutation_support_claimed",
        "debug_attach_support_claimed",
    ):
        _require(catalog.get(key) is False, f"{key}: catalog/runtime separation regressed")

    runtime_track = correction.get("runtime_security_track")
    _require(isinstance(runtime_track, dict), "runtime/security track correction missing")
    _require(runtime_track.get("independent_from_catalog_publication") is True, "runtime/security track became catalog prerequisite")
    _require(runtime_track.get("named_hil_gate_required") is False, "named HIL gate unexpectedly required")
    _require(runtime_track.get("physical_validation_required_before_future_target_execution_enablement") is True, "physical runtime validation boundary missing")
    _require(runtime_track.get("current_target_execution_authorized") is False, "target execution unexpectedly authorized")
    _require(runtime_track.get("next_software_gate") is None, "observer track must not chain to another software HIL gate")

    retired = set(correction.get("retired_hil_gate_artifacts") or [])
    _require(retired == RETIRED, "retired HIL artifact set drifted")
    for relative in sorted(RETIRED):
        _require(not (ROOT / relative).exists(), f"retired HIL gate artifact still present: {relative}")

    _require(correction.get("next_action") == "stm32u5-production-publication-gate", "next action drifted")


def negative_controls(correction: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    hil_required = copy.deepcopy(correction)
    hil_required["catalog_track"]["ppu_hil_required"] = True
    cases.append(("PPU HIL made catalog prerequisite", hil_required))

    physical_required = copy.deepcopy(correction)
    physical_required["catalog_track"]["physical_programming_success_required"] = True
    cases.append(("physical programming made catalog prerequisite", physical_required))

    execute = copy.deepcopy(correction)
    execute["governance_basis"]["catalog_membership_authorizes_target_execution"] = True
    cases.append(("catalog membership authorizes execution", execute))

    preview = copy.deepcopy(correction)
    preview["catalog_track"]["quarantined_preview_exact_icpns"] = []
    cases.append(("Preview quarantine removed", preview))

    hil_gate = copy.deepcopy(correction)
    hil_gate["runtime_security_track"]["named_hil_gate_required"] = True
    cases.append(("named HIL gate reintroduced", hil_gate))

    chained = copy.deepcopy(correction)
    chained["runtime_security_track"]["next_software_gate"] = "stm32u5-hil-observer-debug-matrix-readiness-gate"
    cases.append(("canceled HIL successor reintroduced", chained))

    return cases


def main() -> int:
    correction = _read(CORRECTION)
    validate_correction(correction)

    rejected = 0
    for name, mutated in negative_controls(correction):
        try:
            validate_correction(mutated)
        except AdmissionError:
            rejected += 1
            continue
        raise AdmissionError(f"negative control unexpectedly passed: {name}")

    _require(rejected == 6, "negative-control rejection count drifted")
    print(json.dumps({
        "transaction": correction["transaction"],
        "corrected_prs": correction["corrected_prs"],
        "reviewed_unchanged_prs": correction["reviewed_unchanged_prs"],
        "catalog_next_gate": correction["catalog_track"]["next_gate"],
        "eligible_active_exact_icpns": correction["catalog_track"]["eligible_active_exact_icpns"],
        "quarantined_preview_exact_icpns": correction["catalog_track"]["quarantined_preview_exact_icpns"],
        "expected_production_exact_icpns_after": correction["catalog_track"]["expected_production_exact_icpns_after"],
        "named_hil_gate_required": correction["runtime_security_track"]["named_hil_gate_required"],
        "retired_hil_gate_artifacts": len(RETIRED),
        "negative_controls_rejected": rejected,
    }, sort_keys=True))
    print("STM32U5 catalog/runtime governance correction: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

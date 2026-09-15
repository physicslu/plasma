#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECISION = HERE / "stm32-trustzone-cohort-succession-after-l5-blocker.json"
GATE1 = HERE / "stm32-trustzone-cohort-gate1-qualification.json"
L5_BLOCKER = HERE / "stm32l5-hil-fixture-acquisition-provenance.json"
TRANSACTION = "stm32-trustzone-cohort-succession-after-l5-blocker"
EXPECTED_RANKING = ["STM32L5", "STM32U3", "STM32U5"]
EXPECTED_U3_SUBFAMILIES = {
    "STM32U335", "STM32U345", "STM32U356", "STM32U366",
    "STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def validate(decision: dict, gate1: dict, blocker: dict) -> None:
    _require(decision.get("schema_version") == 1, "schema version drifted")
    _require(decision.get("transaction") == TRANSACTION, "transaction drifted")
    _require(decision.get("authority") == "research_only", "authority escaped research_only")
    _require(decision.get("source_gate1") == GATE1.name, "Gate1 binding drifted")
    _require(decision.get("source_l5_blocker") == L5_BLOCKER.name, "L5 blocker binding drifted")
    _require(decision.get("exact_icpn_count") == 1862, "Production exact ICPN count drifted")

    _require(gate1.get("authority") == "research_only", "upstream Gate1 authority drifted")
    candidates = gate1.get("candidates")
    _require(isinstance(candidates, list) and len(candidates) == 3, "TrustZone Gate1 candidate set drifted")
    ordered = sorted(candidates, key=lambda row: row["rank"])
    _require([row["plasma_series"] for row in ordered] == EXPECTED_RANKING, "original TrustZone ranking drifted")
    _require(gate1.get("selected_for_next_research") == "STM32L5", "original Gate1 selection drifted")

    _require(blocker.get("authority") == "research_only", "L5 blocker authority drifted")
    _require(blocker.get("family") == "STM32L5", "L5 blocker family drifted")
    blocker_info = blocker.get("blocker")
    _require(isinstance(blocker_info, dict), "L5 blocker record missing")
    _require(blocker_info.get("type") == "external_hardware_acquisition_required", "L5 blocker type drifted")
    _require(blocker.get("next_action") == "external_stm32l5_fixture_acquisition_and_provenance_submission", "L5 external next action drifted")
    _require(blocker.get("next_research_gate") is None, "L5 software-only chain no longer stops at blocker")
    result = blocker.get("admission_result")
    _require(isinstance(result, dict), "L5 admission result missing")
    _require(result.get("verified_physical_acquisition_present") is False, "L5 physical acquisition unexpectedly present")
    _require(result.get("hil_execution_ready") is False, "L5 HIL unexpectedly ready")
    _require(blocker.get("exact_icpn_count") == 1862, "L5 blocker ICPN count drifted")

    ranking = decision.get("original_ranking")
    _require(isinstance(ranking, list) and len(ranking) == 3, "decision ranking missing")
    _require([row.get("plasma_series") for row in ranking] == EXPECTED_RANKING, "decision ranking order drifted")
    for expected, actual in zip(ordered, ranking):
        for key in ("rank", "plasma_series", "subfamily_count", "row_count", "ordering_pattern_rows"):
            _require(actual.get(key) == expected.get(key), f"ranking field drifted: {actual.get('plasma_series')}/{key}")
        _require(actual.get("target_config") == expected.get("target_config"), f"target config drifted: {actual.get('plasma_series')}")

    pause = decision.get("l5_pause")
    _require(isinstance(pause, dict), "L5 pause record missing")
    _require(pause.get("series") == "STM32L5", "L5 pause series drifted")
    _require(pause.get("blocker_type") == "external_hardware_acquisition_required", "L5 pause blocker drifted")
    _require(pause.get("verified_physical_fixtures") == 0, "unsupported L5 fixture count")
    _require(pause.get("hil_execution_ready") is False, "L5 HIL ready claim forbidden")
    _require(pause.get("next_action") == blocker.get("next_action"), "L5 next-action continuity drifted")
    _require(pause.get("permanent_family_rejection") is False, "L5 must be paused, not permanently rejected")

    policy = decision.get("succession_policy")
    _require(isinstance(policy, dict), "succession policy missing")
    for key in ("preserve_original_ranking", "skip_only_candidates_with_explicit_external_blocker", "do_not_reclassify_blocked_candidate_as_failed", "do_not_infer_production_or_runtime_support_from_selection"):
        _require(policy.get(key) is True, f"succession invariant missing: {key}")
    _require(policy.get("selected_series") == "STM32U3", "next software-only candidate must be STM32U3")
    _require(policy.get("selected_rank") == 2, "STM32U3 rank must remain 2")

    selected = decision.get("selected_candidate")
    _require(isinstance(selected, dict), "selected candidate missing")
    _require(selected.get("plasma_series") == "STM32U3", "selected candidate drifted")
    _require(set(selected.get("subfamilies", [])) == EXPECTED_U3_SUBFAMILIES, "STM32U3 subfamily set drifted")
    _require(selected.get("subfamily_count") == 8, "STM32U3 subfamily count drifted")
    _require(selected.get("row_count") == 171, "STM32U3 row count drifted")
    _require(selected.get("cmsis_device_name_rows") == 96, "STM32U3 CMSIS row count drifted")
    _require(selected.get("ordering_pattern_rows") == 75, "STM32U3 ordering row count drifted")
    _require(selected.get("target_config") == "tcl/target/stm32u3x.cfg", "STM32U3 target config drifted")
    _require(selected.get("structural_gate_pass") is True, "STM32U3 structural gate must pass")
    _require(selected.get("complete_mapping_metadata") is True, "STM32U3 mapping metadata must be complete")
    _require(selected.get("cohort") == "trustzone_requires_security_scope", "STM32U3 cohort drifted")

    claims = decision.get("claims")
    _require(isinstance(claims, dict), "claims missing")
    for key, value in claims.items():
        _require(value is False, f"selection may not assert capability: {key}")
    _require(decision.get("next_research_gate") == "stm32u3-security-scope-foundation", "next research gate drifted")


def negative_controls(decision: dict) -> list[tuple[str, dict]]:
    cases: list[tuple[str, dict]] = []
    u5 = copy.deepcopy(decision)
    u5["succession_policy"]["selected_series"] = "STM32U5"
    cases.append(("skip rank-2 U3", u5))

    production = copy.deepcopy(decision)
    production["claims"]["production_admission"] = True
    cases.append(("Production admission inferred from succession", production))

    runtime = copy.deepcopy(decision)
    runtime["claims"]["runtime_programming_supported"] = True
    cases.append(("runtime programming inferred from succession", runtime))

    reject_l5 = copy.deepcopy(decision)
    reject_l5["l5_pause"]["permanent_family_rejection"] = True
    cases.append(("L5 external blocker converted to permanent rejection", reject_l5))

    count = copy.deepcopy(decision)
    count["exact_icpn_count"] = 1911
    cases.append(("Production ICPN count drift", count))
    return cases


def main() -> int:
    decision = _read(DECISION)
    gate1 = _read(GATE1)
    blocker = _read(L5_BLOCKER)
    validate(decision, gate1, blocker)
    rejected = 0
    for name, mutated in negative_controls(decision):
        try:
            validate(mutated, gate1, blocker)
        except ValueError:
            rejected += 1
        else:
            raise SystemExit(f"FAIL: negative control admitted: {name}")
    _require(rejected == 5, "negative-control rejection count drifted")
    print("STM32 TrustZone cohort succession after L5 blocker: PASS")
    print("selected_series=STM32U3")
    print("negative_controls_rejected=5")
    print("exact_icpn_count=1862")
    print("next_research_gate=stm32u3-security-scope-foundation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

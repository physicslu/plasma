#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32L4 Phase L4.2 evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stm32l4_phase_l4_1_foundation import validate_production_prestate
from stm32l4_phase_l4_2_discovery import (
    AUTHORITY_SURFACE,
    COMMERCIAL_IDENTITY_AUTHORITY,
    EXPECTED_L4_1_BASELINE_SHA256,
    EXPECTED_L4_1_REPRESENTATIVES,
    FAMILY,
    PARSER_PROFILE,
    PHASE,
    deterministic_targets,
    read_catalog,
    target_manifest,
    validate_l4_1_boundary,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l4-phase-l4.2-discovery-baseline.json"
DISCOVERY = HERE / "stm32l4-phase-l4.2-discovery-manifest.json"
EVIDENCE = HERE / "evidence/stm32l4-l4.2-official-st-discovery-live-2026-09-13"

EXPECTED_BASE_DEVICE_COUNT = 138
EXPECTED_ACTIVE_EXACT_COUNT = 446
EXPECTED_EXCLUDED_EXACT_COUNT = 5
EXPECTED_RETENTION_RUN_ID = 34741498287
EXPECTED_RETENTION_EXEC_SHA = "5a066ac1d9d2c92961bf2c09553b3658b89e8e6f"
EXPECTED_INITIAL_RUN_ID = 34713341677
EXPECTED_INITIAL_EXEC_SHA = "8d45ed34bd1029055ba9a6fd035f23ea4f4ebb6f"
EXPECTED_INITIAL_ARTIFACT_ID = 10304163363
EXPECTED_INITIAL_ARTIFACT_SHA256 = "e04253546cfba83209bf0b55f8fe46de4b5e14110bbc1bb5b95aefcb46d984a4"
EXPECTED_OPENOCD_SHA = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_PRODUCTION_PRESTATE_SHA = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"
EXPECTED_LIVE_SUMMARY_SHA = "0c9279000bf69384ed167049c711bfe7b6fe4e1274288cc1bbd6b21e6bafc784"
EXPECTED_TARGETS_SHA = "568726e2b285831b1d17d49bf1da78ae7fde12ff720d24190c5fb5dcd2cd44d9"
EXPECTED_PROVENANCE_SHA = "774f7391a45d4106d0fcbb019d4aa7ac31a3c72691586c55b489f3d63f234587"
EXPECTED_LEAF_DIGESTS_SHA = "4231e22e22b646dc8aa2c859740ea778e84aca8f6b516fc3b5e93ac7dec7b47d"
EXPECTED_RETAINED_MANIFEST_SHA = "b2809115666d6ed3afd1af50c62fcb7d95bcbdbfdb472080fa51cfa4b0f0b56e"
EXPECTED_BASE_SET_SHA = "d014a837f40cd2c4bebaa39ef92261cd3eb4a4f30f26aed1225f32d77c2c781d"
EXPECTED_ACTIVE_SET_SHA = "cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45"
EXPECTED_EXCLUDED_SET_SHA = "72b21e849db53a724f7162394e1bfa3c5d7ff9f68726b6088e8cadae502e5e23"

RETRY_BASE_DEVICES = (
    "STM32L412CB", "STM32L412RB", "STM32L412T8", "STM32L451VC", "STM32L471QG",
    "STM32L471VG", "STM32L475RE", "STM32L496QG", "STM32L496VE", "STM32L4P5ZE",
    "STM32L4Q5CG", "STM32L4Q5RG", "STM32L4R9VG", "STM32L4S5ZI", "STM32L4S9ZI",
)
EXPECTED_EXCLUDED_PART_NUMBERS = (
    "STM32L452CET6P",
    "STM32L462CET6P",
    "STM32L462CEU3",
    "STM32L462CEU6F",
    "STM32L476VGY6PTR",
)


class Error(RuntimeError):
    pass


def req(state: bool, message: str) -> None:
    if not state:
        raise Error(message)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(payload, dict), f"{path.name}: expected JSON object")
    return payload


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_sha(values: list[str] | tuple[str, ...] | set[str]) -> str:
    body = "".join(value + "\n" for value in sorted(values)).encode()
    return hashlib.sha256(body).hexdigest()


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    validate_l4_1_boundary()
    production = validate_production_prestate()
    sources = production.get("sources")
    req(isinstance(sources, list), "immutable Production prestate sources missing")
    counts = {
        item.get("family"): item.get("row_count")
        for item in sources if isinstance(item, dict)
    }
    req(sum(v for v in counts.values() if isinstance(v, int)) == 1272, "immutable Production count drift")
    req(counts.get("STM32L4", 0) == 0, "immutable Production prestate unexpectedly contains STM32L4")

    baseline = read_json(BASELINE)
    summary = read_json(EVIDENCE / "live-summary.json")
    targets = read_json(EVIDENCE / "targets.json")
    provenance = read_json(EVIDENCE / "provenance.json")
    leaf_map = read_json(EVIDENCE / "leaf-digests.json")
    retained = read_json(EVIDENCE / "retained-manifest.json")

    req(sha256(EVIDENCE / "live-summary.json") == EXPECTED_LIVE_SUMMARY_SHA, "live summary hard-lock drift")
    req(sha256(EVIDENCE / "targets.json") == EXPECTED_TARGETS_SHA, "targets hard-lock drift")
    req(sha256(EVIDENCE / "provenance.json") == EXPECTED_PROVENANCE_SHA, "provenance hard-lock drift")
    req(sha256(EVIDENCE / "leaf-digests.json") == EXPECTED_LEAF_DIGESTS_SHA, "leaf digest-map hard-lock drift")
    req(sha256(EVIDENCE / "retained-manifest.json") == EXPECTED_RETAINED_MANIFEST_SHA, "retained manifest hard-lock drift")
    req(sha256(DISCOVERY) == EXPECTED_TARGETS_SHA, "root deterministic manifest hard-lock drift")

    req(baseline.get("schema_version") == 2, "baseline schema drift")
    req(provenance.get("schema_version") == 2, "provenance schema drift")
    req(retained.get("schema_version") == 2, "retained manifest schema drift")
    for payload, label in ((baseline, "baseline"), (summary, "summary"), (targets, "targets"), (retained, "retained manifest")):
        req(payload.get("phase") == PHASE and payload.get("family") == FAMILY, f"{label} identity drift")
    req(all_false(baseline.get("claims")), "baseline claims escaped fail-closed state")
    req(all_false(summary.get("claims")), "summary claims escaped fail-closed state")
    req(all_false(targets.get("claims")), "target claims escaped fail-closed state")
    req(all_false(retained.get("claims")), "retained manifest claims escaped fail-closed state")
    req(summary.get("commercial_identity_authority") == COMMERCIAL_IDENTITY_AUTHORITY, "summary authority drift")

    source_bindings = baseline.get("source_bindings")
    req(isinstance(source_bindings, dict), "baseline source bindings missing")
    req(source_bindings.get("l4_1_foundation_sha256") == EXPECTED_L4_1_BASELINE_SHA256, "L4.1 binding drift")
    req(source_bindings.get("openocd_catalog_sha256") == EXPECTED_OPENOCD_SHA, "OpenOCD binding drift")
    req(source_bindings.get("production_prestate_sha256") == EXPECTED_PRODUCTION_PRESTATE_SHA, "Production prestate binding drift")
    req(source_bindings.get("production_prestate_exact_icpn_count") == 1272, "Production count binding drift")
    req(source_bindings.get("stm32l4_production_prestate_exact_icpn_count") == 0, "STM32L4 Production prestate binding drift")

    retained_binding = baseline.get("retained_evidence")
    req(isinstance(retained_binding, dict), "baseline retained-evidence binding missing")
    req(retained_binding.get("workflow_run_id") == EXPECTED_RETENTION_RUN_ID, "retention workflow run binding drift")
    req(retained_binding.get("workflow_run_attempt") == 1, "retention workflow attempt drift")
    req(retained_binding.get("executed_git_sha") == EXPECTED_RETENTION_EXEC_SHA, "retention execution SHA drift")
    req(retained_binding.get("acquisition_run_count") == 2, "acquisition run-count binding drift")
    req(retained_binding.get("live_summary_sha256") == EXPECTED_LIVE_SUMMARY_SHA, "baseline live-summary binding drift")
    req(retained_binding.get("targets_sha256") == EXPECTED_TARGETS_SHA, "baseline targets binding drift")
    req(retained_binding.get("provenance_sha256") == EXPECTED_PROVENANCE_SHA, "baseline provenance binding drift")
    req(retained_binding.get("leaf_digests_sha256") == EXPECTED_LEAF_DIGESTS_SHA, "baseline leaf-map binding drift")
    req(retained_binding.get("retained_manifest_sha256") == EXPECTED_RETAINED_MANIFEST_SHA, "baseline retained-manifest binding drift")

    req(provenance.get("workflow_role") == "targeted_timeout_recovery_and_retention", "provenance workflow role drift")
    req(provenance.get("workflow_run_id") == EXPECTED_RETENTION_RUN_ID, "provenance retention run drift")
    req(provenance.get("workflow_run_attempt") == 1, "provenance retention attempt drift")
    req(provenance.get("executed_git_sha") == EXPECTED_RETENTION_EXEC_SHA, "provenance retention execution SHA drift")
    req(provenance.get("source_repository") == "physicslu/plasma", "provenance repository drift")
    req(provenance.get("source_branch") == "agent/device-catalog-stm32l4-phase-l42-discovery", "provenance branch drift")
    req(provenance.get("canonical_admission_authorized") is False, "provenance admitted canonical data")
    req(provenance.get("production_write_authorized") is False, "provenance authorized Production")
    req(provenance.get("runtime_programming_support_claimed") is False, "provenance claimed runtime support")

    browser = provenance.get("browser")
    req(isinstance(browser, dict), "aggregate browser provenance missing")
    req(browser.get("headless") is False, "retained acquisition must remain headed")
    req(browser.get("evidence_profile") == PARSER_PROFILE, "aggregate evidence profile drift")
    req(browser.get("reuse_browser") is True and browser.get("per_device_global_deadline") is True, "aggregate bounded-browser policy drift")
    req(browser.get("acquisition_run_count") == 2, "aggregate browser run count drift")
    req(browser.get("initial_per_device_timeout_seconds") == 75.0, "initial timeout profile drift")
    req(browser.get("recovery_per_device_timeout_seconds") == 180.0, "recovery timeout profile drift")
    req(summary.get("browser") == browser, "summary/provenance browser profile drift")

    expected_manifest = target_manifest(deterministic_targets(read_catalog()))
    req(canonical_json_bytes(expected_manifest) == DISCOVERY.read_bytes(), "deterministic root discovery manifest drift")
    req(DISCOVERY.read_bytes() == (EVIDENCE / "targets.json").read_bytes(), "root/evidence target manifests differ")
    target_rows = targets.get("targets")
    req(isinstance(target_rows, list) and len(target_rows) == EXPECTED_BASE_DEVICE_COUNT, "target row count drift")
    deterministic_bases = [str(row.get("base_device")) for row in target_rows if isinstance(row, dict)]
    req(len(deterministic_bases) == EXPECTED_BASE_DEVICE_COUNT and len(set(deterministic_bases)) == EXPECTED_BASE_DEVICE_COUNT, "deterministic Base Device set drift")
    retry_set = set(RETRY_BASE_DEVICES)
    req(retry_set.issubset(set(deterministic_bases)), "retry set escaped deterministic boundary")
    initial_set = set(deterministic_bases) - retry_set
    req(len(initial_set) == 123 and len(retry_set) == 15 and not initial_set & retry_set, "123+15 contribution partition drift")
    req(initial_set | retry_set == set(deterministic_bases), "contribution partition does not cover all 138 Base Devices")

    runs = provenance.get("acquisition_runs")
    req(isinstance(runs, list) and len(runs) == 2, "two-run acquisition provenance missing")
    initial, recovery = runs
    req(isinstance(initial, dict) and isinstance(recovery, dict), "malformed acquisition-run provenance")
    req(initial.get("role") == "initial_partial_acquisition", "initial acquisition role drift")
    req(initial.get("workflow_run_id") == EXPECTED_INITIAL_RUN_ID and initial.get("workflow_run_attempt") == 1, "initial workflow identity drift")
    req(initial.get("executed_git_sha") == EXPECTED_INITIAL_EXEC_SHA, "initial execution SHA drift")
    req(initial.get("artifact_id") == EXPECTED_INITIAL_ARTIFACT_ID, "initial artifact ID drift")
    req(initial.get("artifact_sha256") == EXPECTED_INITIAL_ARTIFACT_SHA256, "initial artifact digest drift")
    req(initial.get("per_device_timeout_seconds") == 75.0, "initial per-device timeout drift")
    req(initial.get("reuse_browser") is True and initial.get("per_device_global_deadline") is True, "initial bounded-browser policy drift")
    req(initial.get("successful_target_count") == initial.get("contributed_base_device_count") == 123, "initial contribution count drift")
    req(initial.get("timeout_target_count") == 15, "initial timeout count drift")
    req(tuple(initial.get("timeout_base_devices", ())) == RETRY_BASE_DEVICES, "initial timeout whitelist drift")
    req(initial.get("contributed_base_device_set_sha256") == set_sha(initial_set), "initial contribution set digest drift")
    ib = initial.get("browser")
    req(isinstance(ib, dict) and ib.get("headless") is False and ib.get("evidence_profile") == PARSER_PROFILE, "initial browser evidence profile drift")
    req(ib.get("per_device_timeout_seconds") == 75.0 and ib.get("reuse_browser") is True and ib.get("per_device_global_deadline") is True, "initial browser bounded policy drift")

    req(recovery.get("role") == "targeted_timeout_recovery", "recovery role drift")
    req(recovery.get("workflow_run_id") == EXPECTED_RETENTION_RUN_ID and recovery.get("workflow_run_attempt") == 1, "recovery workflow identity drift")
    req(recovery.get("executed_git_sha") == EXPECTED_RETENTION_EXEC_SHA, "recovery execution SHA drift")
    req(recovery.get("per_device_timeout_seconds") == 180.0, "recovery per-device timeout drift")
    req(recovery.get("reuse_browser") is True and recovery.get("per_device_global_deadline") is True, "recovery bounded-browser policy drift")
    req(recovery.get("successful_target_count") == recovery.get("contributed_base_device_count") == 15, "recovery contribution count drift")
    req(tuple(recovery.get("contributed_base_devices", ())) == RETRY_BASE_DEVICES, "recovery whitelist drift")
    req(recovery.get("contributed_base_device_set_sha256") == set_sha(retry_set), "recovery contribution set digest drift")
    rb = recovery.get("browser")
    req(isinstance(rb, dict) and rb.get("headless") is False and rb.get("evidence_profile") == PARSER_PROFILE, "recovery browser evidence profile drift")
    req(rb.get("per_device_timeout_seconds") == 180.0, "recovery browser timeout drift")

    aggregate = baseline.get("aggregate")
    req(isinstance(aggregate, dict), "baseline aggregate missing")
    req(summary.get("base_device_count") == summary.get("attempted") == EXPECTED_BASE_DEVICE_COUNT, "summary target count drift")
    req(summary.get("commercial_identity_verified_targets") == EXPECTED_BASE_DEVICE_COUNT, "verified identity count drift")
    req(summary.get("dispositioned_targets") == EXPECTED_BASE_DEVICE_COUNT, "disposition count drift")
    req(summary.get("active_candidate_targets") == EXPECTED_BASE_DEVICE_COUNT, "Active Base Device count drift")
    req(summary.get("lifecycle_excluded_targets") == 0, "unexpected lifecycle-only Base Device")
    req(summary.get("active_exact_icpn_candidates") == EXPECTED_ACTIVE_EXACT_COUNT, "Active exact ICPN count hard-lock drift")
    req(summary.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED_EXACT_COUNT, "excluded exact Part Number count hard-lock drift")
    req(summary.get("source_unavailable_exclusions") == 0, "source-unavailable target drift")
    req(summary.get("identity_manual_intervention_required") == 0, "manual review drift")
    req(summary.get("acquisition_failure") == 0, "acquisition failure drift")
    req(summary.get("representative_continuity_clean") is True, "representative continuity drift")
    req(summary.get("commercial_identity_clean") is True, "commercial identity clean state drift")
    req(summary.get("bounded_discovery_clean") is True, "bounded discovery clean state drift")
    for key in (
        "base_device_count", "active_candidate_targets", "lifecycle_excluded_targets",
        "active_exact_icpn_candidates", "excluded_non_active_part_numbers",
        "source_unavailable_exclusions", "identity_manual_intervention_required",
        "acquisition_failure", "representative_continuity_clean", "routing_followup_required",
        "bounded_discovery_clean",
    ):
        req(aggregate.get(key) == summary.get(key), f"aggregate {key} drift")
    routing = summary.get("openocd_routing")
    req(isinstance(routing, dict) and routing.get("gates_commercial_identity") is False, "OpenOCD routing became identity authority")
    req(routing.get("unique") == 138 and routing.get("ambiguous") == 0 and routing.get("unmapped") == 0, "routing diagnostic set drift")
    req(summary.get("routing_followup_required") == 0, "unexpected routing follow-up")
    req(aggregate.get("openocd_unique_targets") == routing.get("unique"), "routing unique aggregate drift")

    result_rows = summary.get("results")
    digests = leaf_map.get("sha256_by_file")
    req(isinstance(result_rows, list) and len(result_rows) == EXPECTED_BASE_DEVICE_COUNT, "result row count drift")
    req(leaf_map.get("leaf_count") == EXPECTED_BASE_DEVICE_COUNT and isinstance(digests, dict) and len(digests) == EXPECTED_BASE_DEVICE_COUNT, "leaf digest count drift")

    active: list[str] = []
    excluded: list[str] = []
    bases: list[str] = []
    seen_active: set[str] = set()
    seen_excluded: set[str] = set()
    rep_status: dict[str, str] = {}
    for target, result in zip(target_rows, result_rows):
        req(isinstance(target, dict) and isinstance(result, dict), "invalid target/result row")
        base = target.get("base_device")
        req(isinstance(base, str) and result.get("base_device") == base, "target/result order drift")
        req(result.get("subfamily") == target.get("subfamily"), f"{base}: subfamily drift")
        req(result.get("source_url") == target.get("source_url"), f"{base}: source URL drift")
        req(str(result.get("source_url", "")).startswith("https://www.st.com/en/microcontrollers-microprocessors/"), f"{base}: non-ST source")
        req(result.get("acquisition_status") == "success", f"{base}: acquisition status drift")
        disposition = result.get("disposition")
        identity = result.get("commercial_identity_status")
        req((identity, disposition) in {
            ("verified_active", "active_candidates"),
            ("verified_non_active_only", "lifecycle_excluded"),
        }, f"{base}: invalid identity/lifecycle disposition")
        req(result.get("manual_intervention_required") is False, f"{base}: manual review drift")
        route = result.get("openocd_routing")
        req(isinstance(route, dict) and route.get("gates_commercial_identity") is False, f"{base}: routing escaped diagnostic role")

        evidence = result.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("base_device") == base, f"{base}: evidence Base Device drift")
        req(evidence.get("evidence_surface") == AUTHORITY_SURFACE, f"{base}: evidence authority surface drift")
        req(evidence.get("parser_profile") == PARSER_PROFILE, f"{base}: parser profile drift")
        exact = evidence.get("exact_icpns")
        non_active = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and isinstance(non_active, list), f"{base}: malformed exact lifecycle sets")
        req(bool(exact) or bool(non_active), f"{base}: no exact lifecycle disposition")
        if identity == "verified_active":
            req(bool(exact), f"{base}: Active target has no exact ICPN")
        else:
            req(not exact and bool(non_active), f"{base}: lifecycle-only target has Active exact ICPN")
        for value in exact:
            req(isinstance(value, str) and value.startswith(base), f"{base}: invalid Active exact ICPN")
            req(value not in seen_active and value not in seen_excluded, f"{value}: duplicate/cross-set exact ICPN")
            seen_active.add(value)
            active.append(value)
        for item in non_active:
            req(isinstance(item, dict), f"{base}: invalid lifecycle exclusion row")
            value = item.get("icpn")
            status = item.get("marketing_status")
            req(isinstance(value, str) and value.startswith(base), f"{base}: invalid excluded exact ICPN")
            req(isinstance(status, str) and bool(status.strip()), f"{base}: missing lifecycle status")
            req(value not in seen_active and value not in seen_excluded, f"{value}: duplicate/cross-set excluded ICPN")
            seen_excluded.add(value)
            excluded.append(value)
        leaf_name = f"{base.lower()}.json"
        req(digests.get(leaf_name) == hashlib.sha256(canonical_json_bytes(result)).hexdigest(), f"{base}: reconstructed leaf digest drift")
        bases.append(base)
        if base in EXPECTED_L4_1_REPRESENTATIVES:
            rep_status[base] = str(identity)

    req(set(rep_status) == EXPECTED_L4_1_REPRESENTATIVES, "L4.1 representative set lost")
    req(set(rep_status.values()) == {"verified_active"}, "L4.1 representative lifecycle continuity regressed")
    req(len(active) == EXPECTED_ACTIVE_EXACT_COUNT, "Active exact ICPN count drift")
    req(len(excluded) == EXPECTED_EXCLUDED_EXACT_COUNT, "excluded non-Active count drift")
    req(not set(active) & set(excluded), "Active/excluded exact Part Number sets overlap")
    req(tuple(sorted(excluded)) == tuple(sorted(EXPECTED_EXCLUDED_PART_NUMBERS)), "excluded exact Part Number set hard-lock drift")

    set_digests = baseline.get("set_digests")
    req(isinstance(set_digests, dict), "baseline set digests missing")
    req(set_sha(bases) == EXPECTED_BASE_SET_SHA, "Base Device set hard-lock drift")
    req(set_sha(active) == EXPECTED_ACTIVE_SET_SHA, "Active exact ICPN set hard-lock drift")
    req(set_sha(excluded) == EXPECTED_EXCLUDED_SET_SHA, "excluded exact Part Number set hard-lock drift")
    req(set_digests.get("base_device_set_sha256") == EXPECTED_BASE_SET_SHA, "baseline Base Device set digest drift")
    req(set_digests.get("active_exact_icpn_set_sha256") == EXPECTED_ACTIVE_SET_SHA, "baseline Active exact set digest drift")
    req(set_digests.get("excluded_non_active_set_sha256") == EXPECTED_EXCLUDED_SET_SHA, "baseline excluded set digest drift")
    req(baseline.get("excluded_non_active_exact_part_numbers") == sorted(excluded), "baseline excluded exact Part Number list drift")

    req(retained.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT, "retained manifest Base Device count drift")
    req(retained.get("acquisition_run_count") == 2, "retained manifest acquisition run count drift")
    req(retained.get("active_exact_icpn_candidates") == EXPECTED_ACTIVE_EXACT_COUNT, "retained manifest Active exact count drift")
    req(retained.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED_EXACT_COUNT, "retained manifest excluded exact count drift")
    req(retained.get("live_summary_sha256") == EXPECTED_LIVE_SUMMARY_SHA, "retained live summary SHA drift")
    req(retained.get("targets_sha256") == EXPECTED_TARGETS_SHA, "retained targets SHA drift")
    req(retained.get("provenance_sha256") == EXPECTED_PROVENANCE_SHA, "retained provenance SHA drift")
    req(retained.get("leaf_digests_sha256") == EXPECTED_LEAF_DIGESTS_SHA, "retained leaf-map SHA drift")

    print("STM32L4 L4.2 retained evidence validation: PASS")
    print(json.dumps({
        "base_devices": len(bases),
        "active_candidate_targets": summary.get("active_candidate_targets"),
        "active_exact_icpn_candidates": len(active),
        "excluded_non_active_part_numbers": len(excluded),
        "routing_followup_required": summary.get("routing_followup_required"),
        "acquisition_runs": len(runs),
        "production_write_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

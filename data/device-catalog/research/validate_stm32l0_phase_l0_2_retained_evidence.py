#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32L0 Phase L0.2 evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from device_catalog_evidence_framework import read_json, sha256, validate_core_provenance, validate_manifest
from stm32l0_phase_l0_1_foundation import validate_production_prestate, validate_retained_identity
from stm32l0_phase_l0_2_discovery import (
    AUTHORITY_SURFACE,
    COMMERCIAL_IDENTITY_AUTHORITY,
    EXPECTED_L0_1_BASELINE_SHA256,
    EXPECTED_L0_1_REPRESENTATIVES,
    FAMILY,
    PARSER_PROFILE,
    PHASE,
    TARGET_CONFIG,
    validate_l0_1_boundary,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l0-phase-l0.2-discovery-baseline.json"
DISCOVERY = HERE / "stm32l0-phase-l0.2-discovery-manifest.json"
EVIDENCE = HERE / "evidence/stm32l0-l0.2-official-st-discovery-live-2026-09-12"
EXPECTED_BASELINE_BLOB = "671064b89fd171eb1ff39d9ef22e361c74bbf2bd"
EXPECTED_EVIDENCE_ID = "stm32l0-l0.2-official-st-discovery-2026-09-12-retained-20260912T110725Z-996489c8"
EXPECTED_RUN_ID = 34686132303
EXPECTED_ARTIFACT_ID = 10296507776
EXPECTED_ARTIFACT_SHA = "5732782fce1911debe7360c07ccbae5ba03fd86cc097a975bc271fe9c6b334bd"
EXPECTED_PR_HEAD = "996489c8fe5e871310dd42c0d06c7b0302ca0750"
EXPECTED_EXEC_SHA = "4423e029cea8ac541d25c87ea8612fae2a3e68ee"
EXPECTED_SUMMARY_SHA = "c664e6458d00f169b2653021284acb56664b607c245e97f51bf13f4a232d51de"
EXPECTED_TARGETS_SHA = "72350a146038c09b43516715f52cddf06ee5d05f1a4ab737a994744d43e166ed"
EXPECTED_ACQ_PROV_SHA = "2e7379f865b0f5e23101517f58d7a53ec5076820a0240369d99cb34b1f08862c"
EXPECTED_LEAF_SHA = "79b562f6eb87081544cd409c399d68f3afa06f644501a243d272be37004c4502"
EXPECTED_RETENTION_PROV_SHA = "23bd258b75f687b01e43beb249f759b4d71a704ba56480ce170c054017cb635f"
EXPECTED_MANIFEST_SHA = "66e4c248398e8986878538c3dde7cc3811df0f3f1a0fbbbd2b1f46c77a20e97a"
EXPECTED_BASE_SET_SHA = "1c9dc41c8f8dc44a132e8303e0c88b2168dc3bbf745a6250aa7f382e57d5f8af"
EXPECTED_ACTIVE_SET_SHA = "8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b"
EXPECTED_EXCLUDED_SET_SHA = "86be718862ed2641a3e857d0d7016aca459852d7dc3f210123893b28f66a6960"
EXPECTED_FILES = {
    "README.md",
    "acquisition-provenance.json",
    "leaf-digests.json",
    "live-summary.json",
    "provenance.json",
    "targets.json",
}
EXPECTED_EXCLUDED = [
    "STM32L011K4T7",
    "STM32L011K4U7",
    "STM32L021F4U7TR",
    "STM32L021G4U7",
    "STM32L021K4T7",
    "STM32L031F4P7",
    "STM32L071RZT7",
    "STM32L071VBT7",
    "STM32L071VZT7",
    "STM32L073V8T7",
]


class Error(RuntimeError):
    pass


def req(state: bool, message: str) -> None:
    if not state:
        raise Error(message)


def git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def set_sha(values: list[str]) -> str:
    body = "".join(value + "\n" for value in sorted(values)).encode()
    return hashlib.sha256(body).hexdigest()


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def main() -> int:
    req(git_blob(BASELINE) == EXPECTED_BASELINE_BLOB, "L0.2 baseline byte drift")
    baseline = read_json(BASELINE)
    req(baseline.get("phase") == PHASE and baseline.get("family") == FAMILY, "baseline identity drift")
    req(baseline.get("evidence_id") == EXPECTED_EVIDENCE_ID, "baseline evidence ID drift")
    req(all_false(baseline.get("claims")), "baseline claims escaped fail-closed state")
    req(baseline.get("commercial_identity_authority") == COMMERCIAL_IDENTITY_AUTHORITY, "authority drift")

    validate_l0_1_boundary()
    production = validate_production_prestate()
    counts = {item["family"]: item["row_count"] for item in production["sources"]}
    req(sum(counts.values()) == 912, "immutable Production prestate count drift")
    req(counts.get("STM32L0", 0) == 0, "immutable Production prestate unexpectedly contains STM32L0")

    manifest = validate_manifest(EVIDENCE, expected_files=EXPECTED_FILES)
    req(manifest.get("evidence_id") == EXPECTED_EVIDENCE_ID, "manifest evidence ID drift")
    req(sha256(EVIDENCE / "manifest.json") == EXPECTED_MANIFEST_SHA, "manifest digest drift")
    req(sha256(EVIDENCE / "live-summary.json") == EXPECTED_SUMMARY_SHA, "live summary digest drift")
    req(sha256(EVIDENCE / "targets.json") == EXPECTED_TARGETS_SHA, "targets digest drift")
    req(sha256(EVIDENCE / "acquisition-provenance.json") == EXPECTED_ACQ_PROV_SHA, "acquisition provenance digest drift")
    req(sha256(EVIDENCE / "leaf-digests.json") == EXPECTED_LEAF_SHA, "leaf digest-map drift")
    req(sha256(EVIDENCE / "provenance.json") == EXPECTED_RETENTION_PROV_SHA, "retention provenance digest drift")
    req(sha256(DISCOVERY) == EXPECTED_TARGETS_SHA, "root discovery manifest drift")
    req(DISCOVERY.read_bytes() == (EVIDENCE / "targets.json").read_bytes(), "root/evidence targets differ")

    provenance = read_json(EVIDENCE / "provenance.json")
    core = validate_core_provenance(
        provenance,
        evidence_id=EXPECTED_EVIDENCE_ID,
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )
    req(core["evaluator_result"] == "clean", "retained evaluator not clean")
    req(core["target_count"] == 99 and core["acquisition_success"] == 99 and core["acquisition_failure"] == 0, "retained acquisition accounting drift")
    req(core["exact_icpn_candidate_count"] == 360, "retained candidate count drift")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "workflow run drift")
    req(provenance.get("artifact_id") == EXPECTED_ARTIFACT_ID, "artifact ID drift")
    req(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_SHA, "artifact digest drift")
    req(provenance.get("pr_head_sha") == EXPECTED_PR_HEAD, "PR head binding drift")
    req(provenance.get("executed_git_sha") == EXPECTED_EXEC_SHA, "executed SHA drift")
    req(provenance.get("headed") is True, "retained acquisition must remain headed")
    req(provenance.get("evidence_profile") == PARSER_PROFILE, "evidence profile drift")
    req(provenance.get("commercial_identity_authority") == COMMERCIAL_IDENTITY_AUTHORITY, "retained authority drift")
    req(provenance.get("l0_1_foundation_sha256") == EXPECTED_L0_1_BASELINE_SHA256, "L0.1 binding drift")
    req(provenance.get("canonical_dataset_admission") is False, "retained evidence cannot admit canonical data")
    req(provenance.get("production_write_authorized") is False, "retained evidence cannot authorize Production")
    req(provenance.get("runtime_programming_support_claimed") is False, "retained evidence cannot claim runtime support")

    acq = read_json(EVIDENCE / "acquisition-provenance.json")
    req(acq.get("workflow_run_id") == EXPECTED_RUN_ID and acq.get("workflow_run_attempt") == 1, "original run provenance drift")
    req(acq.get("executed_git_sha") == EXPECTED_EXEC_SHA, "original executed SHA drift")
    req(acq.get("live_summary_validation") == "success", "original live validation drift")
    req(acq.get("bounded_discovery_clean") is True, "original discovery was not clean")
    req(acq.get("target_count") == 99 and acq.get("active_exact_icpn_candidates") == 360, "original aggregate drift")

    summary = read_json(EVIDENCE / "live-summary.json")
    targets = read_json(EVIDENCE / "targets.json")
    leaf_map = read_json(EVIDENCE / "leaf-digests.json")
    req(summary.get("phase") == PHASE and summary.get("family") == FAMILY, "summary identity drift")
    req(summary.get("commercial_identity_authority") == COMMERCIAL_IDENTITY_AUTHORITY, "summary authority drift")
    req(summary.get("evidence_surface") == AUTHORITY_SURFACE, "summary evidence surface drift")
    req(all_false(summary.get("claims")), "summary claims escaped fail-closed state")
    req(all_false(targets.get("claims")), "target manifest claims escaped fail-closed state")
    req(summary.get("base_device_count") == summary.get("attempted") == 99, "summary target count drift")
    req(summary.get("commercial_identity_verified_targets") == 99, "verified identity count drift")
    req(summary.get("active_candidate_targets") == 99, "Active Base Device count drift")
    req(summary.get("lifecycle_excluded_targets") == 0, "lifecycle-only target drift")
    req(summary.get("source_unavailable_exclusions") == 0, "source-unavailable drift")
    req(summary.get("identity_manual_intervention_required") == 0, "manual review drift")
    req(summary.get("acquisition_failure") == 0, "acquisition failure drift")
    req(summary.get("dispositioned_targets") == 99, "disposition count drift")
    req(summary.get("active_exact_icpn_candidates") == 360, "Active exact ICPN aggregate drift")
    req(summary.get("excluded_non_active_part_numbers") == 10, "non-Active exclusion aggregate drift")
    req(summary.get("representative_continuity_clean") is True, "representative continuity drift")
    req(summary.get("bounded_discovery_clean") is True and summary.get("commercial_identity_clean") is True, "discovery clean state drift")
    req(summary.get("routing_followup_required") == 0, "routing follow-up drift")
    req(summary.get("openocd_routing") == {
        "ambiguous": 0,
        "gates_commercial_identity": False,
        "not_applicable": 0,
        "unique": 99,
        "unmapped": 0,
    }, "routing aggregate drift")
    req(summary.get("browser") == {
        "browser_version": "151.0.7922.34",
        "evidence_profile": PARSER_PROFILE,
        "headless": False,
        "playwright_version": "1.62.0",
    }, "browser profile drift")

    source_targets = targets.get("targets")
    results = summary.get("results")
    leaves = leaf_map.get("leaves")
    req(isinstance(source_targets, list) and len(source_targets) == 99, "target list drift")
    req(isinstance(results, list) and len(results) == 99, "result list drift")
    req(isinstance(leaves, list) and leaf_map.get("leaf_count") == len(leaves) == 99, "leaf digest count drift")
    req(leaf_map.get("artifact_id") == EXPECTED_ARTIFACT_ID and leaf_map.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_SHA, "leaf-map artifact binding drift")
    leaf_by_base = {item.get("base_device"): item for item in leaves if isinstance(item, dict)}
    req(len(leaf_by_base) == 99, "leaf digest Base Device uniqueness drift")

    active: list[str] = []
    excluded: list[str] = []
    bases: list[str] = []
    exact_by_base: dict[str, list[str]] = {}
    for target, result in zip(source_targets, results):
        req(isinstance(target, dict) and isinstance(result, dict), "invalid target/result row")
        base = target.get("base_device")
        req(isinstance(base, str) and result.get("base_device") == base, "target/result order drift")
        req(result.get("subfamily") == target.get("subfamily"), f"{base}: subfamily drift")
        req(result.get("source_url") == target.get("source_url"), f"{base}: source URL drift")
        req(str(result.get("source_url", "")).startswith("https://www.st.com/"), f"{base}: non-ST source")
        req(result.get("acquisition_status") == "success", f"{base}: acquisition status drift")
        req(result.get("commercial_identity_status") == "verified_active", f"{base}: identity status drift")
        req(result.get("disposition") == "active_candidates", f"{base}: disposition drift")
        req(result.get("manual_intervention_required") is False, f"{base}: manual review drift")
        req(result.get("openocd_routing") == {"status": "unique", "gates_commercial_identity": False}, f"{base}: routing drift")
        observations = result.get("routing_observations")
        req(isinstance(observations, list) and observations, f"{base}: missing routing observations")
        req(all(isinstance(obs, dict) and obs.get("status") == "unique" and obs.get("target_config") == TARGET_CONFIG for obs in observations), f"{base}: routing target-config drift")

        evidence = result.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("base_device") == base, f"{base}: evidence Base Device drift")
        req(evidence.get("evidence_surface") == AUTHORITY_SURFACE, f"{base}: evidence surface drift")
        req(evidence.get("parser_profile") == PARSER_PROFILE, f"{base}: parser profile drift")
        exact = evidence.get("exact_icpns")
        non_active = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and exact, f"{base}: missing Active exact ICPNs")
        req(len(exact) == len(set(exact)) and all(isinstance(value, str) and value.startswith(base) for value in exact), f"{base}: invalid exact ICPNs")
        req(isinstance(non_active, list), f"{base}: non-Active list missing")
        canonical = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
        leaf = leaf_by_base.get(base)
        req(isinstance(leaf, dict), f"{base}: leaf digest missing")
        req(leaf.get("path") == f"evidence/{base}.json", f"{base}: leaf path drift")
        req(hashlib.sha256(canonical).hexdigest() == leaf.get("sha256"), f"{base}: reconstructed leaf digest drift")

        bases.append(base)
        active.extend(exact)
        exact_by_base[base] = exact
        for row in non_active:
            req(isinstance(row, dict), f"{base}: invalid non-Active record")
            icpn = row.get("icpn")
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: invalid non-Active ICPN")
            excluded.append(icpn)

    req(len(bases) == len(set(bases)) == 99, "Base Device count/uniqueness drift")
    req(len(active) == len(set(active)) == 360, "Active exact ICPN count/uniqueness drift")
    req(len(excluded) == len(set(excluded)) == 10, "excluded exact ICPN count/uniqueness drift")
    req(set(active).isdisjoint(excluded), "Active/non-Active exact ICPN overlap")
    req(set_sha(bases) == EXPECTED_BASE_SET_SHA, "Base Device set digest drift")
    req(set_sha(active) == EXPECTED_ACTIVE_SET_SHA, "Active exact ICPN set digest drift")
    req(set_sha(excluded) == EXPECTED_EXCLUDED_SET_SHA, "excluded exact ICPN set digest drift")
    req(sorted(excluded) == EXPECTED_EXCLUDED, "excluded exact Part Number set drift")
    req(baseline.get("excluded_non_active_exact_part_numbers") == EXPECTED_EXCLUDED, "baseline excluded set drift")

    representatives = validate_retained_identity()
    req(set(representatives) == EXPECTED_L0_1_REPRESENTATIVES, "L0.1 representative set drift")
    for base, old_result in representatives.items():
        old_exact = old_result["evidence"]["exact_icpns"]
        req(exact_by_base.get(base) == old_exact, f"{base}: L0.1/L0.2 representative exact-set drift")

    print("STM32L0 L0.2 retained evidence: VALID")
    print("Base Devices: 99")
    print("Active exact ICPNs: 360")
    print("Excluded non-Active exact Part Numbers: 10")
    print("Production writes authorized: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

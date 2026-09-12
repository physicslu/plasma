#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32C0 Phase C0.2 evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32c0-phase-c0.2-discovery-baseline.json"
DISCOVERY = HERE / "stm32c0-phase-c0.2-discovery-manifest.json"
C0_1 = HERE / "stm32c0-phase-c0.1-foundation-baseline.json"
PRODUCTION = HERE / "stm32c0-phase-c0.2-production-manifest-prestate.json"
EVIDENCE = HERE / "evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11"
LEAVES = EVIDENCE / "evidence"

EXPECTED_BASELINE_BLOB = "c59818e625ed1f8a0bf99bb80528c374665cbbd5"
EXPECTED_DISCOVERY_BLOB = "1af985c886de3f2355cdde2876f4b51282461cf9"
EXPECTED_C0_1_BLOB = "59eaaa5b367ba889fe547e89b36e4ce58736e794"
EXPECTED_SUMMARY_BLOB = "030703dfaa45405d1541de41a250a712ca0ab834"
EXPECTED_PROVENANCE_BLOB = "fd005b19ebd6d5f117afe2518ccbeb1f1a7c9c92"
EXPECTED_PRODUCTION_BLOB = "89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc"
EXPECTED_C0_1_SHA256 = "c89e8c528f80f9b199a2b153d3d40aa4af090e50c492a7c88bfa7876ce406515"
EXPECTED_PRODUCTION_SHA256 = "903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0"
EXPECTED_RUN_ID = 34573244983
EXPECTED_EXEC_SHA = "64fa5800a5f495da3818a44a71d5bcf8918d16e1"
EXPECTED_RETENTION_SHA = "5d8ffd2b10411773d1300b7351e1f8d3be9e20b8"
EXPECTED_ARTIFACT_ID = 5650035967
EXPECTED_ARTIFACT_DIGEST = "fdce5cde3894ce57f6b1b39a90a61e26f9005111555560336b51a33b11e72549"
EXPECTED_LIVE_SUMMARY_SHA256 = "bbbfb5ccd7695bff2933ed87d4a45985221d6e267e5a75792be4e5a81b943612"
EXPECTED_TARGETS = 50
EXPECTED_ACTIVE_ICPNS = 220
EXPECTED_EXCLUDED_NON_ACTIVE = 1
EXPECTED_ROUTING = Counter({"unique": 44, "unmapped": 6})
EXPECTED_TARGET_CONFIG = "tcl/target/stm32c0x.cfg"
EXPECTED_PROFILE = "stm32c0_c0_2_dual_surface_v1"


class Error(RuntimeError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise Error(message)


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def official_st_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://www.st.com/")


def main() -> int:
    baseline = read_json(BASELINE)
    discovery = read_json(DISCOVERY)
    c0_1 = read_json(C0_1)
    production = read_json(PRODUCTION)
    summary = read_json(EVIDENCE / "pilot-summary.json")
    provenance = read_json(EVIDENCE / "provenance.json")

    # Byte-level bindings for immutable transaction inputs and retained aggregate evidence.
    req(git_blob(BASELINE) == EXPECTED_BASELINE_BLOB, "C0.2 baseline byte drift")
    req(git_blob(DISCOVERY) == EXPECTED_DISCOVERY_BLOB, "C0.2 discovery manifest byte drift")
    req(git_blob(C0_1) == EXPECTED_C0_1_BLOB, "C0.1 foundation byte drift")
    req(git_blob(EVIDENCE / "pilot-summary.json") == EXPECTED_SUMMARY_BLOB, "retained summary byte drift")
    req(git_blob(EVIDENCE / "provenance.json") == EXPECTED_PROVENANCE_BLOB, "retained provenance byte drift")
    req(git_blob(PRODUCTION) == EXPECTED_PRODUCTION_BLOB, "Production manifest drift")
    req(sha256(C0_1) == EXPECTED_C0_1_SHA256, "C0.1 foundation SHA-256 drift")
    req(sha256(PRODUCTION) == EXPECTED_PRODUCTION_SHA256, "Production prestate SHA-256 drift")

    req(baseline.get("schema_version") == 1, "baseline schema drift")
    req(baseline.get("family") == "STM32C0" and baseline.get("phase") == "C0.2", "baseline identity drift")
    req(discovery.get("family") == "STM32C0" and discovery.get("phase") == "C0.2", "discovery identity drift")
    req(summary.get("family") == "STM32C0" and summary.get("phase") == "C0.2", "summary identity drift")
    req(provenance.get("family") == "STM32C0" and provenance.get("phase") == "C0.2", "provenance identity drift")

    # Authority and non-claim boundaries must remain fail-closed.
    req(all_false(baseline.get("claims")), "baseline claims must remain false")
    req(all_false(discovery.get("claims")), "discovery claims must remain false")
    req(all_false(summary.get("claims")), "summary claims must remain false")
    boundaries = baseline.get("authority_boundaries")
    req(isinstance(boundaries, dict) and set(boundaries.values()) == {False}, "authority boundaries must remain false")
    req(summary.get("commercial_identity_authority") == baseline.get("commercial_identity_authority"), "identity authority drift")
    req(summary.get("openocd_routing", {}).get("gates_commercial_identity") is False, "OpenOCD routing cannot gate identity")
    req(provenance.get("canonical_admission_authorized") is False, "retained evidence cannot authorize admission")
    req(provenance.get("production_write_authorized") is False, "retained evidence cannot authorize Production write")
    req(provenance.get("runtime_programming_support_claimed") is False, "retained evidence cannot claim runtime support")

    # Frozen source and execution bindings.
    retained = baseline.get("retained_evidence")
    req(isinstance(retained, dict), "retained_evidence missing")
    req(retained.get("workflow_run_id") == EXPECTED_RUN_ID, "workflow run binding drift")
    req(retained.get("workflow_run_attempt") == 1, "workflow run attempt drift")
    req(retained.get("executed_git_sha") == EXPECTED_EXEC_SHA, "execution SHA binding drift")
    req(retained.get("retention_commit_sha") == EXPECTED_RETENTION_SHA, "retention commit binding drift")
    req(retained.get("artifact_id") == EXPECTED_ARTIFACT_ID, "artifact ID binding drift")
    req(retained.get("artifact_digest_sha256") == EXPECTED_ARTIFACT_DIGEST, "artifact digest binding drift")
    req(retained.get("pilot_summary_git_blob_sha") == EXPECTED_SUMMARY_BLOB, "summary blob binding drift")
    req(retained.get("provenance_git_blob_sha") == EXPECTED_PROVENANCE_BLOB, "provenance blob binding drift")
    req(retained.get("live_summary_sha256") == EXPECTED_LIVE_SUMMARY_SHA256, "live summary binding drift")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "provenance workflow run drift")
    req(provenance.get("workflow_run_attempt") == 1, "provenance run attempt drift")
    req(provenance.get("executed_git_sha") == EXPECTED_EXEC_SHA, "provenance execution SHA drift")
    req(provenance.get("live_summary_sha256") == EXPECTED_LIVE_SUMMARY_SHA256, "provenance live summary digest drift")
    req(provenance.get("source_repository") == "physicslu/plasma", "provenance repository drift")
    req(provenance.get("production_manifest_sha256") == EXPECTED_PRODUCTION_SHA256, "provenance Production binding drift")
    req(provenance.get("c0_1_foundation_sha256") == EXPECTED_C0_1_SHA256, "provenance C0.1 binding drift")

    # Aggregate retained outcome. Routing is intentionally independent of identity.
    req(summary.get("base_device_count") == EXPECTED_TARGETS, "Base Device count drift")
    req(summary.get("attempted") == EXPECTED_TARGETS, "attempt count drift")
    req(summary.get("dispositioned_targets") == EXPECTED_TARGETS, "disposition count drift")
    req(summary.get("commercial_identity_verified_targets") == EXPECTED_TARGETS, "verified identity count drift")
    req(summary.get("active_candidate_targets") == EXPECTED_TARGETS, "Active target count drift")
    req(summary.get("active_exact_icpn_candidates") == EXPECTED_ACTIVE_ICPNS, "Active exact ICPN aggregate drift")
    req(summary.get("lifecycle_excluded_targets") == 0, "unexpected lifecycle-only Base Device")
    req(summary.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED_NON_ACTIVE, "non-Active exact exclusion count drift")
    req(summary.get("source_unavailable_exclusions") == 0, "source-unavailable exclusion drift")
    req(summary.get("identity_manual_intervention_required") == 0, "manual identity review drift")
    req(summary.get("acquisition_failure") == 0, "acquisition failure drift")
    req(summary.get("bounded_discovery_clean") is True, "bounded discovery must remain clean")
    req(summary.get("commercial_identity_clean") is True, "commercial identity must remain clean")
    req(summary.get("representative_continuity_clean") is True, "C0.1 representative continuity drift")
    req(summary.get("routing_followup_required") == 6, "routing follow-up count drift")
    req(summary.get("openocd_routing") == {
        "ambiguous": 0,
        "gates_commercial_identity": False,
        "not_applicable": 0,
        "unique": 44,
        "unmapped": 6,
    }, "routing aggregate drift")

    browser = summary.get("browser")
    req(browser == {
        "browser_version": "151.0.7922.34",
        "evidence_profile": EXPECTED_PROFILE,
        "headless": False,
        "playwright_version": "1.62.0",
    }, "browser/probe profile drift")

    targets = discovery.get("targets")
    results = summary.get("results")
    req(isinstance(targets, list) and len(targets) == EXPECTED_TARGETS, "discovery target list drift")
    req(isinstance(results, list) and len(results) == EXPECTED_TARGETS, "retained result list drift")
    target_bases = [target.get("base_device") for target in targets if isinstance(target, dict)]
    result_bases = [result.get("base_device") for result in results if isinstance(result, dict)]
    req(len(target_bases) == EXPECTED_TARGETS and len(set(target_bases)) == EXPECTED_TARGETS, "discovery Base Device uniqueness drift")
    req(result_bases == target_bases, "retained result order/target drift")

    leaf_paths = sorted(LEAVES.glob("*.json"))
    req(len(leaf_paths) == EXPECTED_TARGETS, "retained leaf evidence file count drift")
    req({path.stem for path in leaf_paths} == set(target_bases), "retained leaf evidence target set drift")

    active: list[str] = []
    excluded: list[str] = []
    routing = Counter()
    exact_by_base: dict[str, list[str]] = {}

    for target, result in zip(targets, results):
        req(isinstance(target, dict) and isinstance(result, dict), "invalid target/result record")
        base = target["base_device"]
        req(result.get("base_device") == base, f"{base}: result target drift")
        req(result.get("subfamily") == target.get("subfamily"), f"{base}: subfamily drift")
        req(result.get("source_url") == target.get("source_url"), f"{base}: source URL drift")
        req(official_st_url(result.get("source_url")), f"{base}: source must remain official ST")
        req(result.get("acquisition_status") == "success", f"{base}: acquisition status drift")
        req(result.get("commercial_identity_status") == "verified_active", f"{base}: commercial identity drift")
        req(result.get("disposition") == "active_candidates", f"{base}: disposition drift")
        req(result.get("manual_intervention_required") is False, f"{base}: manual review drift")

        evidence = result.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(read_json(LEAVES / f"{base}.json") == evidence, f"{base}: leaf evidence differs from frozen summary")
        req(evidence.get("base_device") == base, f"{base}: evidence target drift")
        req(evidence.get("parser_profile") == EXPECTED_PROFILE, f"{base}: parser profile drift")
        req(evidence.get("parser_version") == 2, f"{base}: parser version drift")
        req(evidence.get("acquisition_transport") == "chromium_rendered_dom", f"{base}: transport drift")
        req(official_st_url(evidence.get("source_url")) and official_st_url(evidence.get("final_url")), f"{base}: non-ST evidence URL")
        for key in ("evidence_section_sha256", "rendered_dom_sha256"):
            req(re.fullmatch(r"[0-9a-f]{64}", str(evidence.get(key, ""))) is not None, f"{base}: invalid {key}")

        exact = evidence.get("exact_icpns")
        req(isinstance(exact, list) and exact, f"{base}: missing Active exact ICPNs")
        req(all(isinstance(value, str) and value.startswith(base) for value in exact), f"{base}: foreign exact ICPN")
        req(len(exact) == len(set(exact)), f"{base}: duplicate exact ICPN")
        exact_by_base[base] = exact
        active.extend(exact)

        non_active = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(non_active, list), f"{base}: excluded part list missing")
        for record in non_active:
            req(isinstance(record, dict), f"{base}: invalid excluded part record")
            icpn = record.get("icpn")
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: invalid excluded ICPN")
            req(icpn not in exact, f"{base}: ICPN cannot be both Active and excluded")
            excluded.append(icpn)

        route = result.get("openocd_routing")
        req(isinstance(route, dict) and route.get("gates_commercial_identity") is False, f"{base}: routing boundary drift")
        status = route.get("status")
        req(status in {"unique", "unmapped"}, f"{base}: unexpected routing status {status!r}")
        routing[str(status)] += 1
        observations = result.get("routing_observations")
        req(isinstance(observations, list), f"{base}: routing observations missing")
        if status == "unique":
            req(observations, f"{base}: unique route lacks observations")
            req(all(obs.get("status") == "unique" and obs.get("target_config") == EXPECTED_TARGET_CONFIG for obs in observations if isinstance(obs, dict)), f"{base}: unique route target-config drift")

    req(len(active) == len(set(active)) == EXPECTED_ACTIVE_ICPNS, "Active exact ICPN count/uniqueness drift")
    req(len(excluded) == EXPECTED_EXCLUDED_NON_ACTIVE, "excluded non-Active exact ICPN replay drift")
    req(set(active).isdisjoint(excluded), "Active/excluded exact ICPN overlap")
    req(routing == EXPECTED_ROUTING, f"routing replay drift: {routing}")

    # C0.1 representative exact identities must remain a strict continuity subset.
    representatives = c0_1.get("evidence_foundation", {}).get("representatives")
    req(isinstance(representatives, list) and len(representatives) == 6, "C0.1 representative set drift")
    for rep in representatives:
        req(isinstance(rep, dict), "invalid C0.1 representative")
        base = rep.get("base_device")
        req(isinstance(base, str) and exact_by_base.get(base) == rep.get("exact_icpns"), f"{base}: C0.1 exact-identity continuity drift")

    req(provenance.get("target_count") == EXPECTED_TARGETS, "provenance target count drift")
    req(provenance.get("active_exact_icpn_candidates") == EXPECTED_ACTIVE_ICPNS, "provenance Active exact count drift")
    req(provenance.get("bounded_discovery_clean") is True, "provenance clean-state drift")
    req(provenance.get("browser") == browser, "provenance browser binding drift")

    print("STM32C0 Phase C0.2 retained evidence validation: PASS")
    print(json.dumps({
        "base_devices": EXPECTED_TARGETS,
        "active_exact_icpns": EXPECTED_ACTIVE_ICPNS,
        "excluded_non_active_exact_icpns": EXPECTED_EXCLUDED_NON_ACTIVE,
        "openocd_unique": EXPECTED_ROUTING["unique"],
        "openocd_unmapped": EXPECTED_ROUTING["unmapped"],
        "canonical_admission_authorized": False,
        "production_write_authorized": False,
        "runtime_programming_support_claimed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
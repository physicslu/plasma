#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32G4 Phase 4.9B evidence."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32g4-phase4.9b-discovery-baseline.json"
DISCOVERY = HERE / "stm32g4-phase4.9b-discovery-manifest.json"
EVIDENCE = HERE / "evidence/stm32g4-phase4.9b-official-st-discovery-live-2026-09-10"

EXPECTED_EVIDENCE_ID = "stm32g4-phase4.9b-official-st-discovery-2026-09-10-retained-20260910T003814Z-3c74395a"
EXPECTED_BASELINE_SHA = "474dbe34de46d654262497d3a6bd306c94fb5157e5e6cffb0f4bc753b5d228e3"
EXPECTED_SUMMARY_SHA = "0310a888dadfa2cdabc8f16b59a177ecd6bb0cfc0344a73763d8a5ac264a960b"
EXPECTED_PROVENANCE_SHA = "46943309c3755c4c9f1e8e78e05372e4eef07050bd61d15c80641cd50313e931"
EXPECTED_MANIFEST_SHA = "b9df96eeac45dfe051df8ea8e5d464e41d8e4136d65df2bdd44076ba2be81cfb"
EXPECTED_README_SHA = "f06fa65c26b045252821a01057292ee20100b49e9e3d3b9c46939415ef50643a"
EXPECTED_LIVE_SHA = "4535807ed9c95bc825c7acf98d555fd599cff5dbd13e1989bc829d33dc1b51df"
EXPECTED_EXEC_SHA = "3c74395ae8771ccb8abfeb8fa7aeec671b9d6042"
EXPECTED_RUN = 34421443430
EXPECTED_ARTIFACT = 10131271123
EXPECTED_ARTIFACT_SHA = "a10b34d4ea2f28a0e2ae19e1a54d36b684ec0581de5c79fc8d21c90b97989eb1"

EXPECTED_AGG = {
    "acquisition_failure": 0,
    "acquisition_success": 8,
    "active_candidate_targets": 8,
    "active_exact_icpn_candidates": 25,
    "attempted": 11,
    "bounded_discovery_clean": True,
    "commercial_identity_clean": False,
    "commercial_identity_unresolved_targets": 3,
    "commercial_identity_verified_targets": 8,
    "dispositioned_targets": 11,
    "excluded_non_active_part_numbers": 3,
    "identity_manual_intervention_required": 0,
    "lifecycle_excluded_targets": 0,
    "openocd_routing": {
        "ambiguous": 0,
        "gates_commercial_identity": False,
        "not_applicable": 3,
        "unique": 8,
        "unmapped": 0,
    },
    "routing_followup_required": 0,
    "source_unavailable_exclusions": 3,
}

EXPECTED_BINDINGS = {
    "discovery_manifest_git_blob_sha": "58b78d75225527021b749564cb3b5bb5053f2812",
    "openocd_catalog_git_blob_sha": "0ef056e3363e20bb527590c4a4cc1cc0d7afb810",
    "production_exact_icpn_count": 610,
    "production_family_counts": {
        "STM32F0": 42,
        "STM32F1": 75,
        "STM32F2": 33,
        "STM32F3": 10,
        "STM32F4": 384,
        "STM32F7": 19,
        "STM32G0": 47,
    },
    "production_manifest_git_blob_sha": "9d859e2055132caa9a611b9f9ea877f455d65566",
    "stm32g4_production_prestate_count": 0,
}

EXPECTED_TARGETS = [
    "STM32G411C6",
    "STM32G414CB",
    "STM32G431C6",
    "STM32G441CB",
    "STM32G471CC",
    "STM32G473CB",
    "STM32G474CB",
    "STM32G483CE",
    "STM32G484CE",
    "STM32G491CC",
    "STM32G4A1CE",
]

EXPECTED_UNAVAILABLE = {"STM32G411C6", "STM32G414CB", "STM32G471CC"}
EXPECTED_ACTIVE = {
    "STM32G431C6T6",
    "STM32G431C6U6",
    "STM32G441CBT6",
    "STM32G441CBU6",
    "STM32G441CBY6TR",
    "STM32G473CBT3",
    "STM32G473CBT6",
    "STM32G473CBU6",
    "STM32G474CBT3",
    "STM32G474CBT3TR",
    "STM32G474CBT6TR",
    "STM32G474CBU6",
    "STM32G483CET3",
    "STM32G483CET6",
    "STM32G483CEU6",
    "STM32G484CET6",
    "STM32G484CEU3",
    "STM32G484CEU6",
    "STM32G491CCT3",
    "STM32G491CCT6",
    "STM32G491CCT6TR",
    "STM32G491CCU6",
    "STM32G491CCU6TR",
    "STM32G4A1CET6",
    "STM32G4A1CEU6",
}
EXPECTED_PROPOSAL = {"STM32G441CBT3", "STM32G441CBU3", "STM32G484CET3"}


class Error(RuntimeError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise Error(message)


def readj(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path}: object required")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def main() -> int:
    baseline = readj(BASELINE)
    summary = readj(EVIDENCE / "pilot-summary.json")
    provenance = readj(EVIDENCE / "provenance.json")
    manifest = readj(EVIDENCE / "manifest.json")
    discovery = readj(DISCOVERY)

    req(sha(BASELINE) == EXPECTED_BASELINE_SHA, "baseline byte drift")
    req(sha(EVIDENCE / "pilot-summary.json") == EXPECTED_SUMMARY_SHA, "summary byte drift")
    req(sha(EVIDENCE / "provenance.json") == EXPECTED_PROVENANCE_SHA, "provenance byte drift")
    req(sha(EVIDENCE / "manifest.json") == EXPECTED_MANIFEST_SHA, "manifest byte drift")
    req(sha(EVIDENCE / "README.md") == EXPECTED_README_SHA, "README byte drift")

    req(manifest.get("evidence_id") == EXPECTED_EVIDENCE_ID, "manifest evidence ID drift")
    req(provenance.get("evidence_id") == EXPECTED_EVIDENCE_ID, "provenance evidence ID drift")
    req(
        manifest.get("files")
        == {
            "README.md": EXPECTED_README_SHA,
            "pilot-summary.json": EXPECTED_SUMMARY_SHA,
            "provenance.json": EXPECTED_PROVENANCE_SHA,
        },
        "retained manifest file bindings drift",
    )

    req(baseline.get("aggregate") == EXPECTED_AGG, "baseline aggregate drift")
    req(summary.get("aggregate") == EXPECTED_AGG, "summary aggregate drift")
    req(baseline.get("source_bindings") == EXPECTED_BINDINGS, "baseline source bindings drift")
    req(provenance.get("source_bindings") == EXPECTED_BINDINGS, "provenance source bindings drift")

    execution = baseline.get("discovery_execution")
    req(
        execution
        == {
            "artifact_id": EXPECTED_ARTIFACT,
            "artifact_zip_sha256": EXPECTED_ARTIFACT_SHA,
            "executed_git_sha": EXPECTED_EXEC_SHA,
            "live_summary_sha256": EXPECTED_LIVE_SHA,
            "workflow_run_id": EXPECTED_RUN,
        },
        "execution binding drift",
    )
    req(provenance.get("workflow_run_id") == EXPECTED_RUN, "workflow run drift")
    req(provenance.get("artifact_id") == EXPECTED_ARTIFACT, "artifact ID drift")
    req(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_SHA, "artifact digest drift")
    req(provenance.get("executed_git_sha") == EXPECTED_EXEC_SHA, "execution SHA drift")
    req(provenance.get("live_artifact_summary_sha256") == EXPECTED_LIVE_SHA, "live summary digest drift")
    req(provenance.get("baseline_sha256") == EXPECTED_BASELINE_SHA, "provenance baseline digest drift")

    req(
        provenance.get("acquisition_time_utc")
        == {"first": "2026-09-10T00:29:39Z", "last": "2026-09-10T00:38:14Z"},
        "acquisition time drift",
    )
    req(provenance.get("evidence_profile") == "stm32g4_dual_surface_v1", "evidence profile drift")
    req(provenance.get("playwright_version") == "1.62.0", "Playwright version drift")
    req(provenance.get("chromium_version") == "151.0.7922.34", "Chromium version drift")
    req(provenance.get("headed") is True, "retained run must remain headed")

    req(all_false(baseline.get("claims")), "baseline claims must remain false")
    req(all_false(summary.get("claims")), "summary claims must remain false")
    req(
        isinstance(baseline.get("claims"), dict)
        and baseline["claims"].get("cmsis_alias_is_commercial_identity") is False,
        "CMSIS alias boundary violated",
    )

    targets = baseline.get("targets")
    source_targets = discovery.get("targets")
    req(isinstance(targets, list) and isinstance(source_targets, list), "target lists missing")
    req(len(targets) == len(source_targets) == 11, "target count drift")
    req([x.get("base_device") for x in targets] == EXPECTED_TARGETS, "retained target ordering drift")
    req([x.get("base_device") for x in source_targets] == EXPECTED_TARGETS, "discovery target ordering drift")

    observed_active: list[str] = []
    observed_proposals: list[str] = []
    observed_unavailable: set[str] = set()
    routing = Counter()

    for target in targets:
        req(isinstance(target, dict), "retained target must be an object")
        base = target.get("base_device")
        req(isinstance(base, str), "retained target base missing")
        req(target.get("routing_gates_commercial_identity") is False, f"{base}: routing boundary drift")

        if base in EXPECTED_UNAVAILABLE:
            req(target.get("disposition") == "source_unavailable_excluded", f"{base}: 404 disposition drift")
            req(target.get("commercial_identity_status") == "unverified", f"{base}: 404 identity status drift")
            req(target.get("source_unavailable_status") == "http_404", f"{base}: source status drift")
            req("exact_icpns" not in target, f"{base}: 404 target cannot claim exact identities")
            observed_unavailable.add(base)
            routing["not_applicable"] += 1
            continue

        req(target.get("disposition") == "active_candidates", f"{base}: expected Active disposition")
        req(target.get("commercial_identity_status") == "verified_active", f"{base}: Active identity status drift")
        exact = target.get("exact_icpns")
        excluded = target.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and exact, f"{base}: exact identities missing")
        req(isinstance(excluded, list), f"{base}: lifecycle exclusions missing")
        req(all(isinstance(x, str) and x.startswith(base) for x in exact), f"{base}: foreign Active identity")
        req(target.get("historical_openocd_routing_status") == "unique", f"{base}: routing status drift")
        req(target.get("historical_openocd_target_configs") == ["tcl/target/stm32g4x.cfg"], f"{base}: target config drift")
        routing["unique"] += 1
        observed_active.extend(exact)

        for item in excluded:
            req(isinstance(item, dict), f"{base}: exclusion must be object")
            icpn = item.get("icpn")
            status = item.get("marketing_status")
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: invalid excluded identity")
            req(isinstance(status, str) and status.startswith("Proposal"), f"{base}: unexpected non-Active state")
            observed_proposals.append(icpn)

        for key in ("evidence_section_sha256", "rendered_dom_sha256"):
            req(re.fullmatch(r"[0-9a-f]{64}", str(target.get(key, ""))) is not None, f"{base}: invalid {key}")

    req(set(observed_active) == EXPECTED_ACTIVE, "Active exact ICPN set drift")
    req(len(observed_active) == len(set(observed_active)) == 25, "Active exact ICPN count/uniqueness drift")
    req(set(observed_proposals) == EXPECTED_PROPOSAL and len(observed_proposals) == 3, "Proposal exclusion set drift")
    req(observed_unavailable == EXPECTED_UNAVAILABLE, "source-unavailable set drift")
    req(routing == Counter({"unique": 8, "not_applicable": 3}), f"routing target-count drift: {routing}")

    unavailable = baseline.get("source_unavailable")
    req(isinstance(unavailable, list) and len(unavailable) == 3, "source-unavailable projection drift")
    req({x.get("base_device") for x in unavailable} == EXPECTED_UNAVAILABLE, "source-unavailable projection set drift")
    req(all(x.get("reason") == "canonical_product_page_http_404" for x in unavailable), "404 reason drift")

    req(provenance.get("target_count") == 11, "provenance target count drift")
    req(provenance.get("exact_icpn_candidate_count") == 25, "provenance Active count drift")
    req(provenance.get("excluded_non_active_part_number_count") == 3, "provenance exclusion count drift")
    req(provenance.get("source_unavailable_exclusion_count") == 3, "provenance 404 count drift")
    req(provenance.get("bounded_discovery_clean") is True, "bounded discovery must remain clean")
    req(provenance.get("commercial_identity_clean") is False, "commercial identity clean flag drift")
    req(provenance.get("routing_gates_commercial_identity") is False, "routing cannot gate identity")
    req(provenance.get("canonical_dataset_admission") is False, "retained evidence cannot admit canonical data")
    req(provenance.get("production_admission_ready") is False, "retained evidence cannot authorize Production")

    print("STM32G4 Phase 4.9B retained evidence validation: PASS")
    print(
        json.dumps(
            {
                "active_exact_icpns": 25,
                "proposal_exclusions": sorted(EXPECTED_PROPOSAL),
                "source_unavailable_bases": sorted(EXPECTED_UNAVAILABLE),
                "routing_unique_targets": 8,
                "routing_not_applicable_targets": 3,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

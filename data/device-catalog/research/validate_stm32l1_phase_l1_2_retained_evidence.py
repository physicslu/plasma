#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32L1 Phase L1.2 evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stm32l1_phase_l1_2_discovery import (
    DEFAULT_CATALOG,
    EXPECTED_L1_1_REPRESENTATIVES,
    FAMILY,
    PHASE,
    deterministic_targets,
    read_catalog,
    target_manifest,
    validate_gate1_production_boundary,
    validate_l1_1_boundary,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32l1-phase-l1.2-discovery-baseline.json"
EVIDENCE = HERE / "evidence/stm32l1-l1.2-official-st-discovery-live-2026-09-13"
COMMERCIAL = EVIDENCE / "commercial-identity.json"
LEAF_DIGESTS = EVIDENCE / "leaf-digests.json"
PROVENANCE = EVIDENCE / "provenance.json"
RETAINED = EVIDENCE / "retained-manifest.json"

EXPECTED_BASELINE_SHA256 = "2f44e54dfac6904cc9af485e14eeb54e2d1a564f1cb633668fdf8f3a78ab4f92"
EXPECTED_COMMERCIAL_SHA256 = "b55695589ea47b84e6097725f68ac888d652ffd0865e8724066b3dda7fe81555"
EXPECTED_LEAF_DIGESTS_SHA256 = "20fc8bb2faca2171d21966ee8930e1184012530ed8f30378c575ebce887bcd17"
EXPECTED_PROVENANCE_SHA256 = "180179f59d1c377870b78b3fcbe1a91f4fdb5785f69df0fb4ebd89033f1d79de"
EXPECTED_RETAINED_SHA256 = "31562944157c9ea754f90adecf7018e7611d57a78f113d7f4e16ec4e2b6669e8"
EXPECTED_RAW_LIVE_SUMMARY_SHA256 = "74ad8d3630874f0f6ffe8454a8970508882402fc7e57a2f754944d9dffd28624"
EXPECTED_RAW_TARGETS_SHA256 = "ecedbe5da6ef960cbab049c728c027e6bc0fc55596727a514b20a8a9880a8eb8"
EXPECTED_ARTIFACT_SHA256 = "a659f1f6751cf9a249ac64e7d8d654497c40077ceac6bf6794c5f4eda21be9c0"
EXPECTED_EXEC_SHA = "d0018aa512fc94127ad4bb1aab2ee8ab2ccdfc41"
EXPECTED_RUN_ID = 34765901513
EXPECTED_ARTIFACT_ID = 10321123053
EXPECTED_L1_1_BLOB = "8da20cfc02c8106d5163338e85fb6425bc9ccdc9"
EXPECTED_PRODUCTION_BLOB = "1aa2311a25a69742c428147a402816ed5071e04e"
EXPECTED_OPENOCD_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_BASE_SET_SHA256 = "a655af5a5063748a3e493ebe40c4a98d91722a1daa672e4965bcb4a105022595"
EXPECTED_ACTIVE_SET_SHA256 = "0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12"
EXPECTED_EXCLUDED_SET_SHA256 = "c839c5063c990b62c4ea051aa15901070a6e38feb1c182f13cb2577b9ababa56"
EXPECTED_BASE_COUNT = 59
EXPECTED_SURFACE_COUNT = 78
EXPECTED_GENERATION_PAIR_COUNT = 19
EXPECTED_ACTIVE_EXACT_COUNT = 144
EXPECTED_EXCLUDED_EXACT_COUNT = 62


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


def set_sha(values: set[str]) -> str:
    body = "".join(value + "\n" for value in sorted(values)).encode()
    return hashlib.sha256(body).hexdigest()


def canonical_pretty_sha(value: object) -> str:
    body = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(body).hexdigest()


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def main() -> int:
    l1_1 = validate_l1_1_boundary()
    production = validate_gate1_production_boundary()
    req(sum(row["row_count"] for row in production["sources"]) == 1718, "Production exact ICPN count drift")
    req(len(production["sources"]) == 12, "Production family count drift")
    req(not any(row["family"] == FAMILY for row in production["sources"]), "STM32L1 escaped into Production")

    baseline = read_json(BASELINE)
    commercial = read_json(COMMERCIAL)
    leafs = read_json(LEAF_DIGESTS)
    provenance = read_json(PROVENANCE)
    retained = read_json(RETAINED)

    req(sha256(BASELINE) == EXPECTED_BASELINE_SHA256, "L1.2 baseline hard-lock drift")
    req(sha256(COMMERCIAL) == EXPECTED_COMMERCIAL_SHA256, "retained commercial identity drift")
    req(sha256(LEAF_DIGESTS) == EXPECTED_LEAF_DIGESTS_SHA256, "retained leaf digest map drift")
    req(sha256(PROVENANCE) == EXPECTED_PROVENANCE_SHA256, "retained provenance drift")
    req(sha256(RETAINED) == EXPECTED_RETAINED_SHA256, "retained manifest drift")

    for payload, label in (
        (baseline, "baseline"),
        (commercial, "commercial"),
        (leafs, "leaf digests"),
        (provenance, "provenance"),
        (retained, "retained manifest"),
    ):
        req(payload.get("phase") == PHASE and payload.get("family") == FAMILY, f"{label} identity drift")

    req(all_false(baseline.get("claims")), "baseline claims escaped fail-closed state")
    req(all_false(commercial.get("claims")), "commercial claims escaped fail-closed state")
    req(all_false(retained.get("claims")), "retained claims escaped fail-closed state")

    sb = baseline.get("source_bindings")
    req(isinstance(sb, dict), "baseline source bindings missing")
    req(sb.get("l1_1_foundation_git_blob") == EXPECTED_L1_1_BLOB, "L1.1 binding drift")
    req(sb.get("gate1_production_manifest_git_blob") == EXPECTED_PRODUCTION_BLOB, "Production binding drift")
    req(sb.get("openocd_catalog_sha256") == EXPECTED_OPENOCD_SHA256, "OpenOCD catalog binding drift")
    req(sb.get("gate1_production_exact_icpn_count") == 1718, "Production count binding drift")
    req(sb.get("gate1_production_family_count") == 12, "Production family binding drift")
    req(sb.get("gate1_stm32l1_exact_icpn_count") == 0, "STM32L1 Production prestate drift")
    req(l1_1["evidence_foundation"]["openocd_catalog_sha256"] == EXPECTED_OPENOCD_SHA256, "L1.1 OpenOCD authority drift")

    replay = target_manifest(deterministic_targets(read_catalog(DEFAULT_CATALOG)))
    req(canonical_pretty_sha(replay) == EXPECTED_RAW_TARGETS_SHA256, "deterministic L1.2 target replay drift")
    req(replay.get("base_device_count") == EXPECTED_BASE_COUNT, "deterministic Base Device count drift")
    req(replay.get("evidence_surface_count") == EXPECTED_SURFACE_COUNT, "deterministic evidence surface count drift")
    req(replay.get("generation_pair_target_count") == EXPECTED_GENERATION_PAIR_COUNT, "generation-pair count drift")
    req(all_false(replay.get("claims")), "target replay claims escaped fail-closed state")

    rb = baseline.get("retained_evidence")
    req(isinstance(rb, dict), "baseline retained-evidence binding missing")
    req(rb.get("workflow_run_id") == EXPECTED_RUN_ID and rb.get("workflow_run_attempt") == 1, "workflow run binding drift")
    req(rb.get("executed_git_sha") == EXPECTED_EXEC_SHA, "execution SHA drift")
    req(rb.get("artifact_id") == EXPECTED_ARTIFACT_ID, "artifact ID drift")
    req(rb.get("artifact_sha256") == EXPECTED_ARTIFACT_SHA256, "artifact digest drift")
    req(rb.get("raw_live_summary_sha256") == EXPECTED_RAW_LIVE_SUMMARY_SHA256, "raw live summary digest drift")
    req(rb.get("raw_targets_sha256") == EXPECTED_RAW_TARGETS_SHA256, "raw target digest drift")
    req(rb.get("commercial_identity_sha256") == EXPECTED_COMMERCIAL_SHA256, "commercial binding drift")
    req(rb.get("leaf_digests_sha256") == EXPECTED_LEAF_DIGESTS_SHA256, "leaf binding drift")
    req(rb.get("provenance_sha256") == EXPECTED_PROVENANCE_SHA256, "provenance binding drift")
    req(rb.get("retained_manifest_sha256") == EXPECTED_RETAINED_SHA256, "retained-manifest binding drift")

    req(provenance.get("workflow_role") == "authoritative_full_sharded_headed_acquisition", "provenance role drift")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID and provenance.get("workflow_run_attempt") == 1, "provenance run drift")
    req(provenance.get("executed_git_sha") == EXPECTED_EXEC_SHA, "provenance execution SHA drift")
    req(provenance.get("artifact_id") == EXPECTED_ARTIFACT_ID, "provenance artifact ID drift")
    req(provenance.get("artifact_sha256") == EXPECTED_ARTIFACT_SHA256, "provenance artifact digest drift")
    req(provenance.get("raw_live_summary_sha256") == EXPECTED_RAW_LIVE_SUMMARY_SHA256, "provenance live-summary digest drift")
    req(provenance.get("raw_targets_sha256") == EXPECTED_RAW_TARGETS_SHA256, "provenance target digest drift")
    req(provenance.get("canonical_admission_authorized") is False, "provenance admitted canonical data")
    req(provenance.get("production_write_authorized") is False, "provenance authorized Production")
    req(provenance.get("runtime_programming_support_claimed") is False, "provenance claimed runtime support")

    shards = provenance.get("browser_shards")
    req(isinstance(shards, list) and len(shards) == 4, "browser shard provenance missing")
    req({row.get("shard_index") for row in shards if isinstance(row, dict)} == {0, 1, 2, 3}, "browser shard index drift")
    for row in shards:
        req(isinstance(row, dict), "malformed browser shard")
        req(row.get("headless") is False, "authoritative acquisition must remain headed")
        req(row.get("reuse_browser") is True, "browser reuse policy drift")
        req(row.get("per_device_global_deadline") is False, "global deadline policy drift")
        req(row.get("per_surface_timeout_seconds") == 90.0, "surface timeout policy drift")
        req(row.get("playwright_version") == "1.62.0", "Playwright version drift")
        req(row.get("browser_version") == "151.0.7922.34", "Chromium version drift")
        req(row.get("evidence_profile") == "stm32l1_l1_2_generation_aware_dual_surface_v1", "parser profile drift")

    counts = commercial.get("counts")
    req(isinstance(counts, dict), "retained discovery counts missing")
    expected_counts = {
        "base_devices": EXPECTED_BASE_COUNT,
        "evidence_surfaces": EXPECTED_SURFACE_COUNT,
        "generation_pairs": EXPECTED_GENERATION_PAIR_COUNT,
        "active_candidate_targets": EXPECTED_BASE_COUNT,
        "active_exact_icpns": EXPECTED_ACTIVE_EXACT_COUNT,
        "excluded_non_active_exact_icpns": EXPECTED_EXCLUDED_EXACT_COUNT,
        "lifecycle_excluded_targets": 0,
        "manual_intervention": 0,
        "acquisition_failure": 0,
        "source_unavailable": 0,
    }
    req(counts == expected_counts, "retained discovery count drift")
    req(commercial.get("clean") == {"bounded_discovery": True, "commercial_identity": True, "representative_continuity": True}, "clean-state drift")
    routing = commercial.get("openocd_routing")
    req(isinstance(routing, dict), "routing summary missing")
    req(routing.get("unique") == EXPECTED_BASE_COUNT and routing.get("ambiguous") == 0 and routing.get("unmapped") == 0, "routing summary drift")
    req(routing.get("not_applicable") == 0 and routing.get("gates_commercial_identity") is False, "routing authority drift")
    req(commercial.get("routing_followup_required") == 0, "routing follow-up unexpectedly required")

    records = commercial.get("records")
    req(isinstance(records, list) and len(records) == EXPECTED_BASE_COUNT, "retained commercial record count drift")
    deterministic = {target.base_device: target for target in deterministic_targets(read_catalog(DEFAULT_CATALOG))}
    bases: set[str] = set()
    active: set[str] = set()
    excluded: set[str] = set()
    pair_count = 0
    for record in records:
        req(isinstance(record, list) and len(record) == 5, "malformed retained commercial record")
        subfamily, base, active_rows, excluded_rows, route = record
        req(isinstance(base, str) and base in deterministic and base not in bases, "unknown/duplicate retained Base Device")
        target = deterministic[base]
        req(subfamily == target.subfamily, f"{base}: retained subfamily drift")
        req(route == "unique", f"{base}: routing no longer unique")
        req(isinstance(active_rows, list) and bool(active_rows), f"{base}: Active exact set missing")
        req(isinstance(excluded_rows, list), f"{base}: excluded exact set malformed")
        req(all(isinstance(v, str) and v.startswith(base) for v in active_rows), f"{base}: foreign Active ICPN")
        req(all(isinstance(v, str) and v.startswith(base) for v in excluded_rows), f"{base}: foreign excluded ICPN")
        req(not set(active_rows) & set(excluded_rows), f"{base}: lifecycle overlap")
        req(not active.intersection(active_rows), f"{base}: duplicate Active exact identity")
        req(not excluded.intersection(excluded_rows), f"{base}: duplicate excluded exact identity")
        bases.add(base)
        active.update(active_rows)
        excluded.update(excluded_rows)
        pair_count += int(len(target.surfaces) == 2)

    req(bases == set(deterministic), "retained Base Device coverage drift")
    req(len(active) == EXPECTED_ACTIVE_EXACT_COUNT, "Active exact ICPN count drift")
    req(len(excluded) == EXPECTED_EXCLUDED_EXACT_COUNT, "excluded exact ICPN count drift")
    req(not active & excluded, "global Active/excluded lifecycle overlap")
    req(pair_count == EXPECTED_GENERATION_PAIR_COUNT, "generation-aware target count drift")
    req(EXPECTED_L1_1_REPRESENTATIVES.issubset(bases), "L1.1 representative coverage drift")
    req(set_sha(bases) == EXPECTED_BASE_SET_SHA256, "Base Device set digest drift")
    req(set_sha(active) == EXPECTED_ACTIVE_SET_SHA256, "Active exact set digest drift")
    req(set_sha(excluded) == EXPECTED_EXCLUDED_SET_SHA256, "excluded exact set digest drift")

    set_hashes = commercial.get("set_sha256")
    req(isinstance(set_hashes, dict), "retained set digests missing")
    req(set_hashes.get("base_devices") == EXPECTED_BASE_SET_SHA256, "retained Base set digest drift")
    req(set_hashes.get("active_exact_icpns") == EXPECTED_ACTIVE_SET_SHA256, "retained Active set digest drift")
    req(set_hashes.get("excluded_exact_icpns") == EXPECTED_EXCLUDED_SET_SHA256, "retained excluded set digest drift")

    leaf_map = leafs.get("leaf_sha256")
    req(isinstance(leaf_map, dict) and len(leaf_map) == EXPECTED_BASE_COUNT, "leaf digest map coverage drift")
    req(set(leaf_map) == {base.lower() + ".json" for base in bases}, "leaf digest map Base Device drift")
    req(all(hex64(value) for value in leaf_map.values()), "malformed leaf digest")
    req(leafs.get("source_artifact_id") == EXPECTED_ARTIFACT_ID, "leaf artifact ID drift")
    req(leafs.get("source_artifact_sha256") == EXPECTED_ARTIFACT_SHA256, "leaf artifact digest drift")

    file_hashes = retained.get("retained_files_sha256")
    req(isinstance(file_hashes, dict), "retained file digest map missing")
    req(file_hashes == {
        "commercial-identity.json": EXPECTED_COMMERCIAL_SHA256,
        "leaf-digests.json": EXPECTED_LEAF_DIGESTS_SHA256,
        "provenance.json": EXPECTED_PROVENANCE_SHA256,
    }, "retained file digest map drift")
    req(retained.get("source_artifact_sha256") == EXPECTED_ARTIFACT_SHA256, "retained artifact binding drift")
    req(retained.get("source_raw_live_summary_sha256") == EXPECTED_RAW_LIVE_SUMMARY_SHA256, "retained live summary binding drift")
    req(retained.get("source_raw_targets_sha256") == EXPECTED_RAW_TARGETS_SHA256, "retained target binding drift")

    print(
        "STM32L1 L1.2 retained evidence: PASS "
        f"({len(bases)} Base Devices, {len(active)} Active exact ICPNs, "
        f"{len(excluded)} excluded non-Active exact variants)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

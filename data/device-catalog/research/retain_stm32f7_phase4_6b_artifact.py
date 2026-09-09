#!/usr/bin/env python3
"""Deterministically retain a clean STM32F7 Phase 4.6B live artifact.

Raw rendered-browser evidence remains in the immutable GitHub Actions artifact.
The repository retains a compact decision projection, including Active exact
ICPN candidates, manufacturer-verified lifecycle exclusions, and deterministic
canonical-page-unavailable exclusions. No exclusion is promoted to admission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from stm32f7_phase4_6b_discovery import MAX_TARGETS

HERE = Path(__file__).resolve().parent
DEFAULT_DISCOVERY_MANIFEST = HERE / "stm32f7-phase4.6b-discovery-manifest.json"
DEFAULT_OPENOCD_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_PRODUCTION_MANIFEST = HERE.parent / "production/icpn-v1-manifest.json"
DEFAULT_BASELINE = HERE / "stm32f7-phase4.6b-discovery-baseline.json"
DEFAULT_EVIDENCE_DIR = (
    HERE / "evidence/stm32f7-phase4.6b-official-st-discovery-live-2026-09-09"
)

PHASE = "4.6B"
FAMILY = "STM32F7"
MANUFACTURER = "STMicroelectronics"
PROFILE = "stm32f7_dual_surface_v1"
ACTIVE_STATUS = "Active Product is in volume production."
EXPECTED_PLAYWRIGHT = "1.62.0"
EXPECTED_CHROMIUM = "151.0.7922.34"
EXPECTED_OPENOCD_BLOB = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_PRODUCTION_MANIFEST_BLOB = "8c9bf60bcbae81c145f647deabbcaf3af63c35e6"
EXPECTED_DISCOVERY_MANIFEST_BLOB = "706613e1894b88261d1769f14631655e76bce27c"
EXPECTED_PRODUCTION_FAMILY_COUNTS = {
    "STM32F0": 42,
    "STM32F1": 75,
    "STM32F2": 33,
    "STM32F3": 10,
    "STM32F4": 384,
}
EXPECTED_PRODUCTION_EXACT_COUNT = 544
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RetentionError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetentionError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode("ascii") + body).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def all_false_claims(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def _compact_timestamp(value: str) -> str:
    require(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is not None,
        "invalid acquisition timestamp",
    )
    return value.replace("-", "").replace(":", "")


def _validate_source_bindings() -> dict[str, object]:
    require(
        git_blob_sha(DEFAULT_DISCOVERY_MANIFEST) == EXPECTED_DISCOVERY_MANIFEST_BLOB,
        "discovery manifest Git blob drifted",
    )
    require(
        git_blob_sha(DEFAULT_OPENOCD_CATALOG) == EXPECTED_OPENOCD_BLOB,
        "OpenOCD source Git blob drifted",
    )
    require(
        git_blob_sha(DEFAULT_PRODUCTION_MANIFEST) == EXPECTED_PRODUCTION_MANIFEST_BLOB,
        "Production manifest Git blob drifted",
    )
    manifest = read_json(DEFAULT_PRODUCTION_MANIFEST)
    counts = {
        str(item["family"]): int(item["row_count"])
        for item in manifest.get("sources", [])
    }
    require(
        counts == EXPECTED_PRODUCTION_FAMILY_COUNTS,
        f"Production family snapshot drifted: {counts}",
    )
    require(
        sum(counts.values()) == EXPECTED_PRODUCTION_EXACT_COUNT,
        "Production exact ICPN count drifted",
    )
    require(FAMILY not in counts, "STM32F7 must remain absent from Production during Phase 4.6B")
    return {
        "discovery_manifest_git_blob_sha": EXPECTED_DISCOVERY_MANIFEST_BLOB,
        "openocd_catalog_git_blob_sha": EXPECTED_OPENOCD_BLOB,
        "production_exact_icpn_count": EXPECTED_PRODUCTION_EXACT_COUNT,
        "production_family_counts": EXPECTED_PRODUCTION_FAMILY_COUNTS,
        "production_manifest_git_blob_sha": EXPECTED_PRODUCTION_MANIFEST_BLOB,
        "stm32f7_production_prestate_count": 0,
    }


def _validate_exclusions(value: object, base: str) -> list[dict[str, str]]:
    require(isinstance(value, list), f"{base}: lifecycle exclusions must be a list")
    normalized: list[dict[str, str]] = []
    for item in value:
        require(isinstance(item, dict), f"{base}: lifecycle exclusion must be an object")
        icpn = item.get("icpn")
        status = item.get("marketing_status")
        require(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign lifecycle ICPN")
        require(isinstance(status, str) and status.strip(), f"{base}: lifecycle status missing")
        normalized.append({"icpn": icpn, "marketing_status": status})
    return normalized


def retain(
    *,
    artifact_root: Path,
    artifact_id: int,
    artifact_zip_sha256: str,
    workflow_run_id: int,
    executed_git_sha: str,
    baseline_path: Path = DEFAULT_BASELINE,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
) -> dict[str, object]:
    require(SHA256_RE.fullmatch(artifact_zip_sha256) is not None, "invalid artifact ZIP SHA-256")
    require(re.fullmatch(r"[0-9a-f]{40}", executed_git_sha) is not None, "invalid executed Git SHA")

    summary_path = artifact_root / "live-summary.json"
    metadata_path = artifact_root / "execution-metadata.json"
    exit_code_path = artifact_root / "exit-code.txt"
    raw_evidence_dir = artifact_root / "evidence"
    require(summary_path.is_file(), "live-summary.json is missing from artifact")
    require(metadata_path.is_file(), "execution-metadata.json is missing from artifact")
    require(exit_code_path.read_text(encoding="utf-8").strip() == "0", "live discovery exit code is not zero")
    require(raw_evidence_dir.is_dir(), "raw evidence directory is missing")

    live = read_json(summary_path)
    metadata = read_json(metadata_path)
    require(live.get("schema_version") == 1 and live.get("phase") == PHASE, "live phase/schema mismatch")
    require(live.get("family") == FAMILY, "live family mismatch")
    require(live.get("attempted") == MAX_TARGETS, "live target count mismatch")
    require(live.get("dispositioned_targets") == MAX_TARGETS, "live target disposition count mismatch")
    require(live.get("acquisition_failure") == 0, "live technical acquisition failure is nonzero")
    require(live.get("bounded_discovery_clean") is True, "live bounded discovery gate is not clean")
    require(live.get("identity_manual_intervention_required") == 0, "live manual intervention required")
    require(all_false_claims(live.get("claims")), "live claims must all remain false")

    routing = live.get("openocd_routing")
    require(
        isinstance(routing, dict) and routing.get("gates_commercial_identity") is False,
        "routing must not gate commercial identity",
    )
    browser = live.get("browser")
    require(isinstance(browser, dict), "live browser binding missing")
    require(browser.get("evidence_profile") == PROFILE, "live evidence profile mismatch")
    require(browser.get("playwright_version") == EXPECTED_PLAYWRIGHT, "live Playwright version mismatch")
    require(browser.get("browser_version") == EXPECTED_CHROMIUM, "live Chromium version mismatch")
    require(browser.get("headless") is False, "retained live run must use headed Chromium")

    require(metadata.get("github_sha") == executed_git_sha, "execution metadata Git SHA mismatch")
    require(str(metadata.get("github_run_id")) == str(workflow_run_id), "execution metadata run ID mismatch")

    discovery_manifest = read_json(DEFAULT_DISCOVERY_MANIFEST)
    require(live.get("pilot_id") == discovery_manifest.get("pilot_id"), "pilot identity mismatch")
    manifest_targets = discovery_manifest.get("targets")
    results = live.get("results")
    require(isinstance(manifest_targets, list) and len(manifest_targets) == MAX_TARGETS, "manifest target count mismatch")
    require(isinstance(results, list) and len(results) == MAX_TARGETS, "live result count mismatch")

    retained_targets: list[dict[str, object]] = []
    active_icpns: list[str] = []
    lifecycle_exclusions: list[dict[str, str]] = []
    source_unavailable: list[dict[str, str]] = []
    timestamps: list[str] = []

    for manifest_target, result in zip(manifest_targets, results):
        require(isinstance(manifest_target, dict) and isinstance(result, dict), "target/result entry must be an object")
        base = manifest_target.get("base_device")
        subfamily = manifest_target.get("subfamily")
        source_url = manifest_target.get("source_url")
        require(isinstance(base, str) and isinstance(subfamily, str) and isinstance(source_url, str), "invalid manifest target")
        require(result.get("base_device") == base and result.get("subfamily") == subfamily, f"{base}: target ordering mismatch")
        require(result.get("source_url") == source_url, f"{base}: source URL mismatch")
        disposition = result.get("disposition")

        if disposition == "source_unavailable_excluded":
            require(result.get("acquisition_status") == "source_unavailable", f"{base}: invalid source-unavailable state")
            require(result.get("source_unavailable_status") == "http_404", f"{base}: unsupported source-unavailable reason")
            require(result.get("manual_intervention_required") is False, f"{base}: source exclusion cannot require manual review")
            require(not (raw_evidence_dir / f"{base}.json").exists(), f"{base}: unexpected raw evidence for unavailable page")
            retained_targets.append({
                "base_device": base,
                "commercial_identity_status": "unverified",
                "disposition": disposition,
                "routing_gates_commercial_identity": False,
                "source_unavailable_status": "http_404",
                "source_url": source_url,
                "subfamily": subfamily,
            })
            source_unavailable.append({
                "base_device": base,
                "reason": "canonical_product_page_http_404",
                "source_url": source_url,
                "subfamily": subfamily,
            })
            continue

        require(disposition in {"active_candidates", "lifecycle_excluded"}, f"{base}: unexpected disposition {disposition!r}")
        require(result.get("acquisition_status") == "success", f"{base}: evidence acquisition was not successful")
        evidence = result.get("evidence")
        require(isinstance(evidence, dict), f"{base}: live evidence missing")
        raw_path = raw_evidence_dir / f"{base}.json"
        require(raw_path.is_file(), f"{base}: raw evidence file missing")
        require(read_json(raw_path) == evidence, f"{base}: raw evidence differs from live summary")

        exact = evidence.get("exact_icpns")
        require(isinstance(exact, list), f"{base}: exact ICPNs must be a list")
        require(all(isinstance(value, str) and value.startswith(base) for value in exact), f"{base}: foreign Active ICPN")
        excluded = _validate_exclusions(evidence.get("excluded_non_active_part_numbers"), base)
        if disposition == "active_candidates":
            require(bool(exact), f"{base}: Active disposition lacks Active exact ICPNs")
            require(result.get("commercial_identity_status") == "verified_active", f"{base}: Active identity status mismatch")
        else:
            require(not exact and bool(excluded), f"{base}: lifecycle-only disposition is inconsistent")
            require(result.get("commercial_identity_status") == "verified_non_active_only", f"{base}: lifecycle identity status mismatch")

        for digest_field in ("evidence_section_sha256", "rendered_dom_sha256"):
            digest = evidence.get(digest_field)
            require(isinstance(digest, str) and SHA256_RE.fullmatch(digest) is not None, f"{base}: invalid {digest_field}")
        retrieved = evidence.get("retrieved_at_utc")
        require(isinstance(retrieved, str), f"{base}: retrieval timestamp missing")
        timestamps.append(retrieved)
        target_routing = result.get("openocd_routing")
        require(isinstance(target_routing, dict), f"{base}: routing observation missing")
        require(target_routing.get("gates_commercial_identity") is False, f"{base}: routing gate boundary mismatch")

        retained_targets.append({
            "base_device": base,
            "commercial_identity_status": result.get("commercial_identity_status"),
            "disposition": disposition,
            "evidence_section_sha256": evidence["evidence_section_sha256"],
            "exact_icpns": exact,
            "excluded_non_active_part_numbers": excluded,
            "historical_openocd_routing_status": target_routing.get("status"),
            "historical_openocd_target_configs": target_routing.get("target_configs", []),
            "rendered_dom_sha256": evidence["rendered_dom_sha256"],
            "retrieved_at_utc": retrieved,
            "routing_gates_commercial_identity": False,
            "source_url": source_url,
            "subfamily": subfamily,
        })
        active_icpns.extend(str(value) for value in exact)
        lifecycle_exclusions.extend({"base_device": base, **item} for item in excluded)

    require(len(retained_targets) == MAX_TARGETS, "retained target count mismatch")
    require(len(set(active_icpns)) == len(active_icpns), "duplicate Active exact ICPN across targets")
    require(len(active_icpns) == int(live.get("active_exact_icpn_candidates", -1)), "aggregate Active ICPN count mismatch")
    require(len(lifecycle_exclusions) == int(live.get("excluded_non_active_part_numbers", -1)), "aggregate lifecycle exclusion mismatch")
    require(len(source_unavailable) == int(live.get("source_unavailable_exclusions", -1)), "aggregate source-unavailable count mismatch")
    require(timestamps, "no retained manufacturer evidence timestamps")

    source_bindings = _validate_source_bindings()
    aggregate_keys = (
        "acquisition_failure",
        "acquisition_success",
        "active_candidate_targets",
        "active_exact_icpn_candidates",
        "attempted",
        "bounded_discovery_clean",
        "commercial_identity_clean",
        "commercial_identity_unresolved_targets",
        "commercial_identity_verified_targets",
        "dispositioned_targets",
        "excluded_non_active_part_numbers",
        "identity_manual_intervention_required",
        "lifecycle_excluded_targets",
        "openocd_routing",
        "routing_followup_required",
        "source_unavailable_exclusions",
    )
    aggregate = {key: live[key] for key in aggregate_keys}

    baseline = {
        "aggregate": aggregate,
        "browser": browser,
        "claims": live["claims"],
        "discovery_execution": {
            "artifact_id": artifact_id,
            "artifact_zip_sha256": artifact_zip_sha256,
            "github_checkout_sha": metadata["github_sha"],
            "head_git_sha": executed_git_sha,
            "pre_policy_fix_artifact_id": metadata.get("pre_policy_fix_artifact_id"),
            "pre_policy_fix_run_id": metadata.get("pre_policy_fix_run_id"),
            "workflow_run_id": workflow_run_id,
        },
        "family": FAMILY,
        "phase": PHASE,
        "pilot_id": live["pilot_id"],
        "schema_version": 1,
        "source_bindings": source_bindings,
        "targets": retained_targets,
    }
    write_json(baseline_path, baseline)

    pilot_summary = {
        "aggregate": aggregate,
        "claims": live["claims"],
        "exact_icpns": active_icpns,
        "family": FAMILY,
        "lifecycle": {
            "excluded_non_active_part_numbers": lifecycle_exclusions,
            "marketing_status_for_all_exact_icpns": ACTIVE_STATUS,
        },
        "phase": PHASE,
        "pilot_id": live["pilot_id"],
        "schema_version": 1,
        "source_unavailable_exclusions": source_unavailable,
    }

    first_time = min(timestamps)
    last_time = max(timestamps)
    evidence_id = (
        "stm32f7-phase4.6b-official-st-discovery-2026-09-09-retained-"
        f"{_compact_timestamp(last_time)}-{executed_git_sha[:8]}"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    pilot_path = evidence_dir / "pilot-summary.json"
    provenance_path = evidence_dir / "provenance.json"
    readme_path = evidence_dir / "README.md"
    manifest_path = evidence_dir / "manifest.json"
    write_json(pilot_path, pilot_summary)

    provenance = {
        "acquisition_failure": live["acquisition_failure"],
        "acquisition_success": live["acquisition_success"],
        "acquisition_time_utc": {"first": first_time, "last": last_time},
        "acquisition_transport": live.get("acquisition_transport"),
        "artifact_id": artifact_id,
        "artifact_zip_sha256": artifact_zip_sha256,
        "baseline_sha256": sha256(baseline_path),
        "bounded_discovery_clean": True,
        "canonical_dataset_admission": False,
        "chromium_version": browser["browser_version"],
        "commercial_identity_clean": live["commercial_identity_clean"],
        "evaluator_result": "phase4_6b_bounded_discovery_clean",
        "evidence_id": evidence_id,
        "evidence_profile": browser["evidence_profile"],
        "exact_icpn_candidate_count": len(active_icpns),
        "excluded_non_active_part_number_count": len(lifecycle_exclusions),
        "executed_git_sha": executed_git_sha,
        "execution_mode": "github_actions_headed_chromium",
        "github_checkout_sha": metadata["github_sha"],
        "headed": True,
        "live_artifact_summary_sha256": sha256(summary_path),
        "manufacturer": MANUFACTURER,
        "pilot_summary_sha256": sha256(pilot_path),
        "playwright_version": browser["playwright_version"],
        "pre_policy_fix_artifact_id": metadata.get("pre_policy_fix_artifact_id"),
        "pre_policy_fix_run_id": metadata.get("pre_policy_fix_run_id"),
        "production_admission_ready": False,
        "retained_pilot_summary_kind": "normalized_decision_projection",
        "routing_gates_commercial_identity": False,
        "schema_version": 1,
        "source_bindings": source_bindings,
        "source_repository": "physicslu/plasma",
        "source_unavailable_exclusion_count": len(source_unavailable),
        "target_count": MAX_TARGETS,
        "workflow_run_id": workflow_run_id,
    }
    write_json(provenance_path, provenance)

    readme_path.write_text(
        "# STM32F7 Phase 4.6B retained manufacturer evidence\n\n"
        f"Controlled official-ST discovery run: `{workflow_run_id}` at `{executed_git_sha}`.\n\n"
        f"The immutable Actions artifact `{artifact_id}` (ZIP SHA-256 `{artifact_zip_sha256}`) "
        "retains raw per-target rendered-browser evidence. This directory retains only the "
        "normalized decision projection and provenance.\n\n"
        f"- deterministic targets: {MAX_TARGETS}\n"
        f"- Active exact ICPN candidates: {len(active_icpns)}\n"
        f"- lifecycle-excluded exact identities: {len(lifecycle_exclusions)}\n"
        f"- canonical-page-unavailable targets: {len(source_unavailable)}\n"
        "- manual-review targets: 0\n"
        "- bounded discovery clean: true\n"
        "- canonical admission: false\n"
        "- Production write authorization: false\n"
        "- runtime programming support claim: false\n\n"
        f"Evidence ID: `{evidence_id}`\n",
        encoding="utf-8",
    )

    retained_manifest = {
        "schema_version": 1,
        "evidence_id": evidence_id,
        "canonical_dataset_admission": False,
        "files": [
            {"path": "README.md", "sha256": sha256(readme_path)},
            {"path": "pilot-summary.json", "sha256": sha256(pilot_path)},
            {"path": "provenance.json", "sha256": sha256(provenance_path)},
        ],
    }
    write_json(manifest_path, retained_manifest)

    report = {
        "status": "retained",
        "evidence_id": evidence_id,
        "baseline_sha256": sha256(baseline_path),
        "pilot_summary_sha256": sha256(pilot_path),
        "provenance_sha256": sha256(provenance_path),
        "manifest_sha256": sha256(manifest_path),
        "live_summary_sha256": sha256(summary_path),
        "target_count": MAX_TARGETS,
        "active_exact_icpn_candidates": len(active_icpns),
        "excluded_non_active_part_numbers": len(lifecycle_exclusions),
        "source_unavailable_exclusions": len(source_unavailable),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-zip-sha256", required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--executed-git-sha", required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    args = parser.parse_args()
    try:
        retain(
            artifact_root=args.artifact_root,
            artifact_id=args.artifact_id,
            artifact_zip_sha256=args.artifact_zip_sha256,
            workflow_run_id=args.workflow_run_id,
            executed_git_sha=args.executed_git_sha,
            baseline_path=args.baseline,
            evidence_dir=args.evidence_dir,
        )
    except (RetentionError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

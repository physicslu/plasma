#!/usr/bin/env python3
"""Retain one immutable STM32 U0/C0/L1 accessibility-probe artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROBE_MANIFEST = HERE / "stm32-evidence-accessibility-probe-manifest.json"
PRIORITIZATION = HERE / "stm32-cross-family-prioritization-baseline.json"
OPENOCD = HERE / "openocd-parts-canonical.csv"
PRODUCTION = HERE.parent / "production" / "icpn-v1-manifest.json"
BASELINE = HERE / "stm32-evidence-accessibility-probe-baseline.json"
EVIDENCE_DIR = HERE / "evidence" / "stm32-u0-c0-l1-evidence-accessibility-probe-live-2026-09-10"
PROFILE = "stm32_cross_family_accessibility_probe_v1"
PROBE_ID = "stm32-cross-family-official-st-evidence-accessibility-probe-v1"
EXPECTED_TARGET_COUNT = 13
EXPECTED_PRODUCTION_COUNTS = {
    "STM32F0": 42,
    "STM32F1": 75,
    "STM32F2": 33,
    "STM32F3": 10,
    "STM32F4": 384,
    "STM32F7": 19,
    "STM32G0": 47,
    "STM32G4": 25,
}
EXPECTED_PRIORITIZATION_SHA256 = "9a99865865f048e6a7636efd82cb17958fdc593240a329e18e3b68d8b0f862f9"
EXPECTED_PRODUCTION_SHA256 = "93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d"


class RetentionError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetentionError(message)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"{path}: object required")
    return payload


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def source_bindings() -> dict[str, object]:
    require(sha256(PRIORITIZATION) == EXPECTED_PRIORITIZATION_SHA256, "cross-family prioritization baseline drifted")
    require(sha256(PRODUCTION) == EXPECTED_PRODUCTION_SHA256, "Production manifest prestate drifted")
    production = read_json(PRODUCTION)
    sources = production.get("sources")
    require(isinstance(sources, list), "Production sources missing")
    counts = {str(item["family"]): int(item["row_count"]) for item in sources}
    require(counts == EXPECTED_PRODUCTION_COUNTS, f"Production family counts drifted: {counts}")
    require(sum(counts.values()) == 635, "Production exact count drifted")
    require(not ({"STM32U0", "STM32C0", "STM32L1"} & set(counts)), "probe families must be absent from Production")
    return {
        "probe_manifest_sha256": sha256(PROBE_MANIFEST),
        "probe_manifest_git_blob_sha": git_blob(PROBE_MANIFEST),
        "cross_family_prioritization_sha256": sha256(PRIORITIZATION),
        "cross_family_prioritization_git_blob_sha": git_blob(PRIORITIZATION),
        "openocd_catalog_sha256": sha256(OPENOCD),
        "openocd_catalog_git_blob_sha": git_blob(OPENOCD),
        "production_manifest_sha256": sha256(PRODUCTION),
        "production_manifest_git_blob_sha": git_blob(PRODUCTION),
        "production_exact_icpn_count": 635,
        "production_family_counts": counts,
        "probe_family_production_prestate_counts": {"STM32U0": 0, "STM32C0": 0, "STM32L1": 0},
    }


def retain(
    *,
    artifact_root: Path,
    artifact_id: int,
    artifact_zip_sha256: str,
    workflow_run_id: int,
    executed_git_sha: str,
) -> dict[str, object]:
    require(re.fullmatch(r"[0-9a-f]{64}", artifact_zip_sha256) is not None, "invalid artifact digest")
    require(re.fullmatch(r"[0-9a-f]{40}", executed_git_sha) is not None, "invalid execution SHA")

    summary_path = artifact_root / "summary.json"
    metadata_path = artifact_root / "execution-metadata.json"
    exit_path = artifact_root / "runner-exit-code.txt"
    raw_dir = artifact_root / "evidence"
    require(summary_path.is_file(), "probe summary missing")
    require(metadata_path.is_file(), "execution metadata missing")
    require(exit_path.is_file(), "runner exit code missing")
    require(raw_dir.is_dir(), "raw evidence directory missing")
    require(exit_path.read_text(encoding="utf-8").strip() == "0", "live probe runner was not clean")

    metadata = read_json(metadata_path)
    require(str(metadata.get("github_run_id")) == str(workflow_run_id), "artifact run-id binding mismatch")
    require(metadata.get("github_sha") == executed_git_sha, "artifact execution-SHA binding mismatch")

    live = read_json(summary_path)
    require(live.get("probe_id") == PROBE_ID, "probe id mismatch")
    require(live.get("attempted_targets") == EXPECTED_TARGET_COUNT, "probe target count mismatch")
    require(live.get("dispositioned_targets") == EXPECTED_TARGET_COUNT, "probe disposition count mismatch")
    require(live.get("manual_review_targets") == 0, "manual review remains")
    require(live.get("bounded_probe_clean") is True, "bounded probe not clean")
    require(live.get("selected_next_research_family") is None, "live probe must not select a family")
    require(all_false(live.get("claims")), "live probe claims must remain false")

    browser = live.get("browser")
    require(isinstance(browser, dict), "browser binding missing")
    require(browser.get("evidence_profile") == PROFILE, "browser evidence profile mismatch")
    require(browser.get("playwright_version") == "1.62.0", "Playwright version mismatch")
    require(browser.get("headless") is False, "retained probe must use headed browser")

    manifest = read_json(PROBE_MANIFEST)
    targets = manifest.get("targets")
    results = live.get("results")
    require(isinstance(targets, list) and isinstance(results, list), "target/result lists missing")
    require(len(targets) == len(results) == EXPECTED_TARGET_COUNT, "target/result list mismatch")

    compact: list[dict[str, object]] = []
    exact_active: list[str] = []
    lifecycle_excluded: list[dict[str, str]] = []
    source_unavailable: list[dict[str, str]] = []
    times: list[str] = []

    for target, result in zip(targets, results):
        require(isinstance(target, dict) and isinstance(result, dict), "target/result object required")
        series = str(target["series"])
        subfamily = str(target["subfamily"])
        base = str(target["base_device"])
        require(result.get("series") == series and result.get("subfamily") == subfamily, f"{base}: series/subfamily ordering mismatch")
        require(result.get("base_device") == base, f"{base}: target ordering mismatch")
        require(result.get("source_url") == target["source_url"], f"{base}: source URL drift")
        disposition = result.get("disposition")

        if disposition == "source_unavailable_excluded":
            require(result.get("source_unavailable_status") == "http_404", f"{base}: invalid source-unavailable disposition")
            require(result.get("manual_intervention_required") is False, f"{base}: 404 cannot require manual intervention")
            require(not (raw_dir / f"{base}.json").exists(), f"{base}: 404 cannot have raw evidence")
            compact.append({
                "series": series,
                "subfamily": subfamily,
                "base_device": base,
                "source_url": target["source_url"],
                "disposition": disposition,
                "commercial_identity_status": "unverified",
                "source_unavailable_status": "http_404",
            })
            source_unavailable.append({"series": series, "subfamily": subfamily, "base_device": base, "reason": "canonical_product_page_http_404"})
            continue

        require(disposition in {"active_candidates", "lifecycle_excluded"}, f"{base}: unknown disposition")
        evidence = result.get("evidence")
        require(isinstance(evidence, dict), f"{base}: evidence missing")
        raw_path = raw_dir / f"{base}.json"
        require(raw_path.is_file() and read_json(raw_path) == evidence, f"{base}: raw/live evidence mismatch")
        exact = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        require(isinstance(exact, list) and isinstance(excluded, list), f"{base}: identity lists missing")
        require(all(isinstance(value, str) and value.startswith(base) for value in exact), f"{base}: foreign Active ICPN")
        require(all(
            isinstance(item, dict)
            and isinstance(item.get("icpn"), str)
            and item["icpn"].startswith(base)
            and isinstance(item.get("marketing_status"), str)
            and bool(item["marketing_status"].strip())
            for item in excluded
        ), f"{base}: invalid lifecycle exclusion")
        if disposition == "active_candidates":
            require(bool(exact) and result.get("commercial_identity_status") == "verified_active", f"{base}: Active disposition inconsistent")
        else:
            require(not exact and bool(excluded) and result.get("commercial_identity_status") == "verified_non_active_only", f"{base}: lifecycle-only disposition inconsistent")
        for key in ("evidence_section_sha256", "rendered_dom_sha256"):
            require(isinstance(evidence.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", evidence[key]) is not None, f"{base}: bad {key}")
        retrieved = evidence.get("retrieved_at_utc")
        require(isinstance(retrieved, str) and retrieved, f"{base}: retrieval timestamp missing")
        times.append(retrieved)
        compact.append({
            "series": series,
            "subfamily": subfamily,
            "base_device": base,
            "source_url": target["source_url"],
            "disposition": disposition,
            "commercial_identity_status": result.get("commercial_identity_status"),
            "exact_icpns": exact,
            "excluded_non_active_part_numbers": excluded,
            "evidence_section_sha256": evidence["evidence_section_sha256"],
            "rendered_dom_sha256": evidence["rendered_dom_sha256"],
            "retrieved_at_utc": retrieved,
        })
        exact_active.extend(str(value) for value in exact)
        lifecycle_excluded.extend(
            {"series": series, "base_device": base, "icpn": str(item["icpn"]), "marketing_status": str(item["marketing_status"])}
            for item in excluded
        )

    require(len(exact_active) == len(set(exact_active)), "duplicate Active exact ICPNs across probe")
    require(times, "no manufacturer evidence retained")

    bindings = source_bindings()
    live_sha = sha256(summary_path)
    baseline = {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "pilot_id": live["pilot_id"],
        "scope": live["scope"],
        "by_series": live["by_series"],
        "candidate_series": live["candidate_series"],
        "attempted_targets": live["attempted_targets"],
        "dispositioned_targets": live["dispositioned_targets"],
        "manual_review_targets": live["manual_review_targets"],
        "bounded_probe_clean": live["bounded_probe_clean"],
        "selected_next_research_family": None,
        "claims": live["claims"],
        "browser": browser,
        "targets": compact,
        "source_unavailable": source_unavailable,
        "source_bindings": bindings,
        "discovery_execution": {
            "workflow_run_id": workflow_run_id,
            "artifact_id": artifact_id,
            "artifact_zip_sha256": artifact_zip_sha256,
            "executed_git_sha": executed_git_sha,
            "live_summary_sha256": live_sha,
        },
    }
    write_json(BASELINE, baseline)
    baseline_sha = sha256(BASELINE)

    evidence_id = (
        "stm32-u0-c0-l1-evidence-accessibility-probe-retained-"
        + max(times).replace("-", "").replace(":", "")
        + "-"
        + executed_git_sha[:8]
    )
    retained_summary = {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "pilot_id": live["pilot_id"],
        "by_series": live["by_series"],
        "targets": compact,
        "source_unavailable": source_unavailable,
        "selected_next_research_family": None,
        "claims": live["claims"],
    }
    provenance = {
        "schema_version": 1,
        "evidence_id": evidence_id,
        "manufacturer": "STMicroelectronics",
        "source_repository": "physicslu/plasma",
        "acquisition_transport": "chromium_rendered_dom",
        "headed": True,
        "evidence_profile": PROFILE,
        "playwright_version": browser["playwright_version"],
        "chromium_version": browser.get("browser_version"),
        "acquisition_time_utc": {"first": min(times), "last": max(times)},
        "workflow_run_id": workflow_run_id,
        "artifact_id": artifact_id,
        "artifact_zip_sha256": artifact_zip_sha256,
        "executed_git_sha": executed_git_sha,
        "live_artifact_summary_sha256": live_sha,
        "baseline_sha256": baseline_sha,
        "source_bindings": bindings,
        "target_count": EXPECTED_TARGET_COUNT,
        "selected_next_research_family": None,
        "production_write_authorized": False,
        "programming_policy_defined": False,
        "runtime_support_claimed": False,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    write_json(EVIDENCE_DIR / "probe-summary.json", retained_summary)
    write_json(EVIDENCE_DIR / "provenance.json", provenance)
    (EVIDENCE_DIR / "README.md").write_text(
        "# STM32 U0/C0/L1 evidence accessibility probe\n\n"
        f"Compact projection of immutable GitHub Actions artifact {artifact_id} from run {workflow_run_id}. "
        "Raw rendered-browser evidence remains in the workflow artifact. This probe compares official ST commercial identity/lifecycle evidence accessibility only. It does not select a next family, authorize catalog admission or Production writes, or claim programming/HIL/runtime support.\n",
        encoding="utf-8",
    )
    files = {name: sha256(EVIDENCE_DIR / name) for name in ("README.md", "probe-summary.json", "provenance.json")}
    write_json(EVIDENCE_DIR / "manifest.json", {"schema_version": 1, "evidence_id": evidence_id, "files": files})

    print(json.dumps({
        "evidence_id": evidence_id,
        "baseline_sha256": baseline_sha,
        "probe_summary_sha256": sha256(EVIDENCE_DIR / "probe-summary.json"),
        "provenance_sha256": sha256(EVIDENCE_DIR / "provenance.json"),
        "manifest_sha256": sha256(EVIDENCE_DIR / "manifest.json"),
        "by_series": live["by_series"],
        "active_exact_icpn_count": len(exact_active),
        "lifecycle_excluded_count": len(lifecycle_excluded),
        "source_unavailable_count": len(source_unavailable),
    }, indent=2, sort_keys=True))
    return baseline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-zip-sha256", required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--executed-git-sha", required=True)
    args = parser.parse_args()
    retain(
        artifact_root=args.artifact_root,
        artifact_id=args.artifact_id,
        artifact_zip_sha256=args.artifact_zip_sha256,
        workflow_run_id=args.workflow_run_id,
        executed_git_sha=args.executed_git_sha,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

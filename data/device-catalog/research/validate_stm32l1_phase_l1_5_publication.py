#!/usr/bin/env python3
"""Permanent offline hard-lock validation for STM32L1 L1.5 publication."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from publish_stm32l1_phase_l1_5 import (
    AUDIT_PATH,
    BASELINE_PATH,
    CANONICAL_PATH,
    EXPECTED_EXACT_SET_SHA256,
    EXPECTED_PLAN_GIT_BLOB,
    EXPECTED_POSTSTATE,
    EXPECTED_PRESTATE,
    EXPECTED_PRESTATE_MANIFEST_BLOB,
    EXPECTED_PRESTATE_MANIFEST_SHA256,
    EXPECTED_PUBLISHED_BASES,
    EXPECTED_PUBLISHED_ROWS,
    FAMILY,
    PLAN_PATH,
    PRESTATE_MANIFEST,
    PRODUCTION_MANIFEST,
    PROPOSAL_PATH,
    _git_blob_sha,
    verify_current_publication,
)

HERE = Path(__file__).resolve().parent
PROVENANCE = HERE / "stm32l1-phase-l1.5-publication-provenance.json"

EXPECTED_CANONICAL_BLOB = "8c4ff4b3331f6fe21f04c117fa952802ed587f71"
EXPECTED_CANONICAL_SHA256 = "72fcaf7e50537749f101e80cab7a403f3b3878006fe4019b99b99dadd2f409ec"
EXPECTED_PROPOSAL_BLOB = "fcb388739f5796859d715b512b89ac8c0d379075"
EXPECTED_PROPOSAL_SHA256 = "c6569d29dbaaa45fa79c3c9a019bb993128d91f45feb79a717fd86afacc5f371"
EXPECTED_AUDIT_BLOB = "0cb14c4889e61a6b1ae70b2210f45a891176179a"
EXPECTED_AUDIT_SHA256 = "62b5102282b7fa08c4536896a77e5e7286df3791b1660e9f9aa13ffb95365558"
EXPECTED_BASELINE_BLOB = "5e044cf2381ba4d5aebdd005766cecbdbced976a"
EXPECTED_BASELINE_SHA256 = "902b1983715d48228e9bca6d7025d5d23126b28d603d7c217c9343439273b81e"
EXPECTED_POSTSTATE_MANIFEST_BLOB = "9c1f1a2c7c1ff3bea7892c5decf408ece676d7a3"
EXPECTED_POSTSTATE_MANIFEST_SHA256 = "64074683cb01d3584da314f15e499f3db2c4b586d96def3ab8371dd2b50d93f5"
EXPECTED_PROVENANCE_BLOB = "d42048ca2c7befd691d7cdaf68ee9549ef6aa7ee"
EXPECTED_CALIBRATION_RUN_ID = 34810850178
EXPECTED_CALIBRATION_EXEC_SHA = "d80a3c96b31d19a659498387351227134d674aee"
EXPECTED_PUBLICATION_COMMIT_SHA = "a5b79be6d7970526b42425db5161cec92d6b9486"
EXPECTED_ARTIFACT_ID = 10334622426
EXPECTED_ARTIFACT_SHA256 = "484959cb309c5c91d1f29a1c8c7f7c6f9f5d967accacfc4b093e3d3e02703469"


def req(state: bool, message: str) -> None:
    if not state:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    return _git_blob_sha(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected JSON object")
    return value


def main() -> int:
    # Frozen transaction inputs remain immutable historical artifacts.
    req(git_blob(PLAN_PATH) == EXPECTED_PLAN_GIT_BLOB, "L1.4 admission-plan Git blob drifted")
    req(git_blob(PRESTATE_MANIFEST) == EXPECTED_PRESTATE_MANIFEST_BLOB, "L1.5 prestate Git blob drifted")
    req(sha256(PRESTATE_MANIFEST) == EXPECTED_PRESTATE_MANIFEST_SHA256, "L1.5 prestate SHA-256 drifted")

    # Family publication artifacts are immutable even if the global Production manifest grows later.
    hardlocks = (
        (CANONICAL_PATH, EXPECTED_CANONICAL_BLOB, EXPECTED_CANONICAL_SHA256),
        (PROPOSAL_PATH, EXPECTED_PROPOSAL_BLOB, EXPECTED_PROPOSAL_SHA256),
        (AUDIT_PATH, EXPECTED_AUDIT_BLOB, EXPECTED_AUDIT_SHA256),
        (BASELINE_PATH, EXPECTED_BASELINE_BLOB, EXPECTED_BASELINE_SHA256),
    )
    for path, expected_blob, expected_sha in hardlocks:
        req(path.exists(), f"{path.name}: missing publication artifact")
        req(git_blob(path) == expected_blob, f"{path.name}: Git blob drifted")
        req(sha256(path) == expected_sha, f"{path.name}: SHA-256 drifted")

    req(PROVENANCE.exists(), "L1.5 publication provenance missing")
    req(git_blob(PROVENANCE) == EXPECTED_PROVENANCE_BLOB, "L1.5 publication provenance Git blob drifted")
    provenance = read_json(PROVENANCE)
    req(provenance.get("phase") == "L1.5" and provenance.get("family") == FAMILY, "publication provenance identity drifted")
    req(provenance.get("workflow_run_id") == EXPECTED_CALIBRATION_RUN_ID, "publication calibration run drifted")
    req(provenance.get("workflow_run_attempt") == 1, "publication calibration run attempt drifted")
    req(provenance.get("executed_git_sha") == EXPECTED_CALIBRATION_EXEC_SHA, "publication execution SHA drifted")
    req(provenance.get("publication_commit_sha") == EXPECTED_PUBLICATION_COMMIT_SHA, "publication commit SHA drifted")
    req(provenance.get("artifact_id") == EXPECTED_ARTIFACT_ID, "publication artifact ID drifted")
    req(provenance.get("artifact_sha256") == EXPECTED_ARTIFACT_SHA256, "publication artifact digest drifted")
    req(set((provenance.get("claims") or {}).values()) == {False}, "publication provenance overclaim escaped")

    logical = provenance.get("logical_files")
    req(isinstance(logical, dict), "publication logical-file digest map missing")
    expected_logical = {
        "data/device-catalog/production/icpn-v1-manifest.json": EXPECTED_POSTSTATE_MANIFEST_SHA256,
        "data/device-catalog/research/stm32l1-commercial-icpn.csv": EXPECTED_CANONICAL_SHA256,
        "data/device-catalog/research/stm32l1-phase-l1.5-publication-audit.json": EXPECTED_AUDIT_SHA256,
        "data/device-catalog/research/stm32l1-phase-l1.5-publication-baseline.json": EXPECTED_BASELINE_SHA256,
        "data/device-catalog/research/stm32l1-phase-l1.5-publication-proposal.json": EXPECTED_PROPOSAL_SHA256,
    }
    req(logical == expected_logical, "publication logical-file digest map drifted")

    baseline = read_json(BASELINE_PATH)
    req(baseline.get("published_exact_icpn_set_sha256") == EXPECTED_EXACT_SET_SHA256, "published exact set drifted")
    req(baseline.get("published_exact_icpn_count") == EXPECTED_PUBLISHED_ROWS, "published exact count drifted")
    req(baseline.get("published_base_device_count") == EXPECTED_PUBLISHED_BASES, "published Base Device count drifted")
    req(baseline.get("production_manifest_git_blob_sha_after") == EXPECTED_POSTSTATE_MANIFEST_BLOB, "historical poststate manifest Git blob drifted")
    req(baseline.get("production_manifest_sha256_after") == EXPECTED_POSTSTATE_MANIFEST_SHA256, "historical poststate manifest SHA-256 drifted")
    req(baseline.get("production_prestate") == {"exact_icpns": EXPECTED_PRESTATE[0], "base_devices": EXPECTED_PRESTATE[1], "families": EXPECTED_PRESTATE[2], "stm32l1": 0}, "semantic Production prestate drifted")
    req(baseline.get("production_poststate") == {"exact_icpns": EXPECTED_POSTSTATE[0], "base_devices": EXPECTED_POSTSTATE[1], "families": EXPECTED_POSTSTATE[2], "stm32l1": EXPECTED_PUBLISHED_ROWS}, "semantic Production poststate drifted")
    req(set((baseline.get("claims") or {}).values()) == {False}, "publication baseline overclaim escaped")

    # Current-state validation intentionally permits later unrelated Production growth,
    # while requiring the exact STM32L1 source and its 144 rows to remain unchanged.
    current = verify_current_publication()
    req(current.get("stm32l1_production") == EXPECTED_PUBLISHED_ROWS, "current STM32L1 Production count drifted")
    req(current.get("published_exact_icpns") == EXPECTED_PUBLISHED_ROWS, "current published exact count drifted")
    req(current.get("published_base_devices") == EXPECTED_PUBLISHED_BASES, "current published Base Device count drifted")
    req(current.get("production_exact_icpns", 0) >= EXPECTED_POSTSTATE[0], "Production exact count regressed")
    req(current.get("production_base_devices", 0) >= EXPECTED_POSTSTATE[1], "Production Base Device count regressed")
    req(current.get("production_family_count", 0) >= EXPECTED_POSTSTATE[2], "Production family count regressed")

    print("STM32L1 L1.5 publication hard-lock: PASS")
    print(json.dumps({
        "phase": "L1.5",
        "family": FAMILY,
        "published_exact_icpns": EXPECTED_PUBLISHED_ROWS,
        "published_base_devices": EXPECTED_PUBLISHED_BASES,
        "published_exact_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "production_exact_icpns": current["production_exact_icpns"],
        "production_base_devices": current["production_base_devices"],
        "production_family_count": current["production_family_count"],
        "stm32l1_production": current["stm32l1_production"],
        "calibration_run_id": EXPECTED_CALIBRATION_RUN_ID,
        "artifact_id": EXPECTED_ARTIFACT_ID,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

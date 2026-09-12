#!/usr/bin/env python3
"""Hard-lock validator for STM32L0 L0.5 controlled publication."""
from __future__ import annotations

import hashlib
import json

from publish_stm32l0_phase_l0_5 import (
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
    PROPOSAL_PATH,
    _git_blob_sha,
    verify_current_publication,
)

EXPECTED_BASELINE_GIT_BLOB = "61d49d3517c7351bec38973c116dfd1c925807e4"
EXPECTED_CANONICAL_GIT_BLOB = "8484a3ca22ae141621247e1a947b993803710467"
EXPECTED_CANONICAL_SHA256 = "2a40e482b0e9084feb930b94fd2cac7029d8ecbdf4b69743f99d1e5a3c2439b7"
EXPECTED_PROPOSAL_GIT_BLOB = "f225f3a5c457024aa16bff7ac700db3570f41be7"
EXPECTED_PROPOSAL_SHA256 = "061e60ec3678d41edb182f0274ff64d935af3b026b50e4a144b2527e45652bb0"
EXPECTED_AUDIT_GIT_BLOB = "03de66dd75f0d2b881fe45a4284e46a33bebfa00"
EXPECTED_AUDIT_SHA256 = "62be237f9f012e12fcb5605f8831d2954ec02907cdbb43671333b8e3f9cc44e6"
EXPECTED_POST_MANIFEST_GIT_BLOB = "4e6a53695e86729063acd8ae102f66cc7eeb06c8"
EXPECTED_POST_MANIFEST_SHA256 = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if _git_blob_sha(BASELINE_PATH.read_bytes()) != EXPECTED_BASELINE_GIT_BLOB:
        raise RuntimeError("L0.5 publication baseline bytes drifted")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    expected = {
        "admission_plan_git_blob_sha": EXPECTED_PLAN_GIT_BLOB,
        "prestate_manifest_git_blob_sha": EXPECTED_PRESTATE_MANIFEST_BLOB,
        "prestate_manifest_sha256": EXPECTED_PRESTATE_MANIFEST_SHA256,
        "published_exact_icpn_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "published_exact_icpn_count": EXPECTED_PUBLISHED_ROWS,
        "published_base_device_count": EXPECTED_PUBLISHED_BASES,
        "canonical_csv_git_blob_sha": EXPECTED_CANONICAL_GIT_BLOB,
        "canonical_csv_sha256": EXPECTED_CANONICAL_SHA256,
        "publication_proposal_git_blob_sha": EXPECTED_PROPOSAL_GIT_BLOB,
        "publication_proposal_sha256": EXPECTED_PROPOSAL_SHA256,
        "publication_audit_git_blob_sha": EXPECTED_AUDIT_GIT_BLOB,
        "publication_audit_sha256": EXPECTED_AUDIT_SHA256,
        "production_manifest_git_blob_sha_after": EXPECTED_POST_MANIFEST_GIT_BLOB,
        "production_manifest_sha256_after": EXPECTED_POST_MANIFEST_SHA256,
    }
    for key, value in expected.items():
        if baseline.get(key) != value:
            raise RuntimeError(f"L0.5 baseline {key} drifted")
    if baseline.get("phase") != "L0.5" or baseline.get("family") != "STM32L0":
        raise RuntimeError("L0.5 baseline identity drifted")
    if baseline.get("production_prestate") != {
        "exact_icpns": EXPECTED_PRESTATE[0], "base_devices": EXPECTED_PRESTATE[1],
        "families": EXPECTED_PRESTATE[2], "stm32l0": 0,
    }:
        raise RuntimeError("L0.5 baseline Production prestate drifted")
    if baseline.get("production_poststate") != {
        "exact_icpns": EXPECTED_POSTSTATE[0], "base_devices": EXPECTED_POSTSTATE[1],
        "families": EXPECTED_POSTSTATE[2], "stm32l0": EXPECTED_PUBLISHED_ROWS,
    }:
        raise RuntimeError("L0.5 baseline Production poststate drifted")
    if set((baseline.get("claims") or {}).values()) != {False}:
        raise RuntimeError("L0.5 publication escaped fail-closed support claims")

    if _git_blob_sha(CANONICAL_PATH.read_bytes()) != EXPECTED_CANONICAL_GIT_BLOB or _sha256(CANONICAL_PATH) != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("L0.5 canonical CSV bytes drifted")
    if _git_blob_sha(PROPOSAL_PATH.read_bytes()) != EXPECTED_PROPOSAL_GIT_BLOB or _sha256(PROPOSAL_PATH) != EXPECTED_PROPOSAL_SHA256:
        raise RuntimeError("L0.5 publication proposal bytes drifted")
    if _git_blob_sha(AUDIT_PATH.read_bytes()) != EXPECTED_AUDIT_GIT_BLOB or _sha256(AUDIT_PATH) != EXPECTED_AUDIT_SHA256:
        raise RuntimeError("L0.5 publication audit bytes drifted")

    summary = verify_current_publication()
    if summary != {
        "status": "valid",
        "phase": "L0.5",
        "published_exact_icpns": 360,
        "published_base_devices": 99,
        "production_exact_icpns": 1272,
        "production_base_devices": 392,
        "production_family_count": 11,
        "stm32l0_production": 360,
    }:
        raise RuntimeError(f"L0.5 current publication summary drifted: {summary}")

    print("STM32L0 L0.5 publication: VALID")
    print("Published exact ICPNs: 360")
    print("Published Base Devices: 99")
    print("Production exact ICPNs: 1272")
    print("Production Base Devices: 392")
    print("STM32 families: 11")
    print("STM32L0 Production: 360")
    print("PPU/Socket/HIL/runtime support claimed: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

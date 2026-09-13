#!/usr/bin/env python3
"""Hard-lock validator for STM32L4 L4.5 controlled publication."""
from __future__ import annotations

import hashlib
import json

from publish_stm32l4_phase_l4_5 import (
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

EXPECTED_BASELINE_GIT_BLOB = "dd031a661cf0c3734eb0dd3f6bd7d274de708c8f"
EXPECTED_CANONICAL_GIT_BLOB = "5548df18cd8a8797ad8d2c3d3160af1c4c85cfad"
EXPECTED_CANONICAL_SHA256 = "75062ea1ac51cfa66f0fd76025f74504aad92ea8f982f9b7b2c743ab541fe93e"
EXPECTED_PROPOSAL_GIT_BLOB = "0d849436a304e2363d30915cfdef54c1d6d6e3f7"
EXPECTED_PROPOSAL_SHA256 = "2347bf8158e3ca6441ad8a6484130f3dfed98c3592a2ac9f4539a4768a97b16e"
EXPECTED_AUDIT_GIT_BLOB = "8914420c67266234e5ef671ebff1e6156f856500"
EXPECTED_AUDIT_SHA256 = "295d174fae4a02bd03c2ca3872b47e3dbc378afe3ebfc0aee07fd943fc81c7c4"
EXPECTED_POST_MANIFEST_GIT_BLOB = "ee77f620ba77015382239c15bd6459aad60f19b0"
EXPECTED_POST_MANIFEST_SHA256 = "bea4ef5bda39e26bf0a8aef9c2bee33c5b1233452f1f4b83c944495bc9a3f2e4"


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if _git_blob_sha(BASELINE_PATH.read_bytes()) != EXPECTED_BASELINE_GIT_BLOB:
        raise RuntimeError("L4.5 publication baseline bytes drifted")
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
            raise RuntimeError(f"L4.5 baseline {key} drifted")
    if baseline.get("phase") != "L4.5" or baseline.get("family") != "STM32L4":
        raise RuntimeError("L4.5 baseline identity drifted")
    if baseline.get("production_prestate") != {
        "exact_icpns": EXPECTED_PRESTATE[0], "base_devices": EXPECTED_PRESTATE[1],
        "families": EXPECTED_PRESTATE[2], "stm32l4": 0,
    }:
        raise RuntimeError("L4.5 baseline Production prestate drifted")
    if baseline.get("production_poststate") != {
        "exact_icpns": EXPECTED_POSTSTATE[0], "base_devices": EXPECTED_POSTSTATE[1],
        "families": EXPECTED_POSTSTATE[2], "stm32l4": EXPECTED_PUBLISHED_ROWS,
    }:
        raise RuntimeError("L4.5 baseline Production poststate drifted")
    if set((baseline.get("claims") or {}).values()) != {False}:
        raise RuntimeError("L4.5 publication escaped fail-closed support claims")

    if _git_blob_sha(CANONICAL_PATH.read_bytes()) != EXPECTED_CANONICAL_GIT_BLOB or _sha256(CANONICAL_PATH) != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("L4.5 canonical CSV bytes drifted")
    if _git_blob_sha(PROPOSAL_PATH.read_bytes()) != EXPECTED_PROPOSAL_GIT_BLOB or _sha256(PROPOSAL_PATH) != EXPECTED_PROPOSAL_SHA256:
        raise RuntimeError("L4.5 publication proposal bytes drifted")
    if _git_blob_sha(AUDIT_PATH.read_bytes()) != EXPECTED_AUDIT_GIT_BLOB or _sha256(AUDIT_PATH) != EXPECTED_AUDIT_SHA256:
        raise RuntimeError("L4.5 publication audit bytes drifted")

    summary = verify_current_publication()
    if summary != {
        "status": "valid",
        "phase": "L4.5",
        "published_exact_icpns": 446,
        "published_base_devices": 138,
        "production_exact_icpns": 1718,
        "production_base_devices": 530,
        "production_family_count": 12,
        "stm32l4_production": 446,
    }:
        raise RuntimeError(f"L4.5 current publication summary drifted: {summary}")

    print("STM32L4 L4.5 publication: VALID")
    print("Published exact ICPNs: 446")
    print("Published Base Devices: 138")
    print("Production exact ICPNs: 1718")
    print("Production Base Devices: 530")
    print("STM32 families: 12")
    print("STM32L4 Production: 446")
    print("PPU/Socket/HIL/runtime support claimed: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

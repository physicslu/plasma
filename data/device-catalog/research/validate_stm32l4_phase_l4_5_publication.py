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

EXPECTED_BASELINE_GIT_BLOB = "d43143e3f48a75c886810be1fc7b70061cc3966c"
EXPECTED_CANONICAL_GIT_BLOB = "6cbb7ee5f5189c7d510623940a8945a2bde38399"
EXPECTED_CANONICAL_SHA256 = "f9ab12f70221a7a6fd934e977d2bed2fed7bdca8fdee9208aaf0a5082533793c"
EXPECTED_PROPOSAL_GIT_BLOB = "24a3166fe302e60a184f8623a164e2a2df3b7afd"
EXPECTED_PROPOSAL_SHA256 = "b390447109da6f836e06722a050cdec7c883f695d7f1df7c8be64eab356790d7"
EXPECTED_AUDIT_GIT_BLOB = "9bd87bffea6880bfa2e2d373f5ac0c33e02625da"
EXPECTED_AUDIT_SHA256 = "0c6a0d9ebdc5d97a7238333592f298d786000df1b466e698996695192fe12053"
EXPECTED_POST_MANIFEST_GIT_BLOB = "1aa2311a25a69742c428147a402816ed5071e04e"
EXPECTED_POST_MANIFEST_SHA256 = "b88adcb38f0833a25da1671592ea98496d61166b9d0e51877ffb92ad2820b9fe"


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

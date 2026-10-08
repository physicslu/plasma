#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import propose_openocd_consolidated_backend_promotion_v614 as v614

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_V614_EXACT_SET_SHA256 = "86844a6f58112ea721f15668f371579aa283dcfc174ccf1eabc275f042ebbfcc"
EXPECTED_V614_BINDING_SHA256 = "3e2eafbc959a3d045911487809487642e0f90a5853522155c8413dd0a5a3662e"
EXPECTED_V614_DELTA_SHA256 = "a015a0747354a41459e0d49c5bb5f4ddfb8bca04f9b509a8558b570253c13ed5"
EXPECTED_PROMOTION_COUNT = 364

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data, usedforsecurity=False).hexdigest()

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def build() -> tuple[dict[str,Any], dict[str,bytes], dict[str,bytes]]:
    deltas, patched_files, summary = v614.build()

    req(summary["promotion_exact_count"] == EXPECTED_PROMOTION_COUNT, "v6.14 promotion count drift")
    req(summary["promotion_exact_set_sha256"] == EXPECTED_V614_EXACT_SET_SHA256, "v6.14 exact-set hash drift")
    req(summary["promotion_binding_sha256"] == EXPECTED_V614_BINDING_SHA256, "v6.14 binding hash drift")
    req(summary["promotion_delta_csv_sha256"] == EXPECTED_V614_DELTA_SHA256, "v6.14 delta hash drift")
    req(summary["production_write_authorized"] is False, "v6.14 unexpectedly authorizes Production write")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source_by_family = {s["family"]: s for s in manifest["sources"]}

    preimages: dict[str,bytes] = {}
    postimages: dict[str,bytes] = {}
    files: dict[str,Any] = {}

    for family, post_text in sorted(patched_files.items()):
        source = source_by_family[family]
        path = (MANIFEST.parent / source["path"]).resolve()
        pre = path.read_bytes()
        post = post_text.encode("utf-8")
        preimages[family] = pre
        postimages[family] = post
        files[family] = {
            "production_path": str(path.relative_to(ROOT)),
            "pre_sha256": sha256(pre),
            "pre_git_blob_sha": git_blob_sha(pre),
            "post_sha256": sha256(post),
            "post_git_blob_sha": git_blob_sha(post),
            "expected_row_count": int(source["row_count"]),
            "rollback_preimage_sha256": sha256(pre),
        }

    req(set(files) == set(summary["affected_family_source_bindings_after_if_approved"]),
        "affected-family set drift")
    for family, hashes in summary["affected_family_source_bindings_after_if_approved"].items():
        req(files[family]["post_sha256"] == hashes["sha256"], f"{family}: post SHA mismatch vs v6.14")
        req(files[family]["post_git_blob_sha"] == hashes["git_blob_sha"], f"{family}: post blob mismatch vs v6.14")

    txn = {
        "schema_version": 1,
        "transaction_id": "openocd-production-backend-mapping-v6.15",
        "record_state": "DRY_RUN_TRANSACTION_REQUIRES_OWNER_APPROVAL",
        "source_proposal": "openocd-consolidated-backend-promotion-v6.14",
        "promotion_exact_count": EXPECTED_PROMOTION_COUNT,
        "promotion_exact_set_sha256": EXPECTED_V614_EXACT_SET_SHA256,
        "promotion_binding_sha256": EXPECTED_V614_BINDING_SHA256,
        "promotion_delta_csv_sha256": EXPECTED_V614_DELTA_SHA256,
        "affected_family_count": len(files),
        "affected_files": files,
        "prestate": {
            "production_exact_total": 4629,
            "production_source_count": 28,
            "mapped": 3673,
            "no_mapping": 956,
            "active_openocd_route": 3594,
        },
        "poststate_if_approved": {
            "production_exact_total": 4629,
            "production_source_count": 28,
            "mapped": 4037,
            "no_mapping": 592,
            "active_openocd_route": 3958,
            "active_openocd_route_denominator": 4550,
            "active_openocd_route_coverage_percent": 86.9890,
        },
        "governance": {
            "production_write_authorized": False,
            "requires_explicit_owner_approval": True,
            "backend_fields_only": True,
            "identity_fields_immutable": True,
            "rollback_preimages_frozen": True,
            "programming_profile_binding_claimed": False,
            "programming_verified_claimed": False,
            "engineering_verified_claimed": False,
            "hil_verified_claimed": False,
        },
    }
    return txn, preimages, postimages

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--package-dir", type=Path)
    args = parser.parse_args()

    txn, preimages, postimages = build()
    if args.manifest_out:
        args.manifest_out.write_text(json.dumps(txn, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.package_dir:
        before = args.package_dir / "before"
        after = args.package_dir / "after"
        before.mkdir(parents=True, exist_ok=True)
        after.mkdir(parents=True, exist_ok=True)
        for family, data in preimages.items():
            (before / f"{family}.csv").write_bytes(data)
        for family, data in postimages.items():
            (after / f"{family}.csv").write_bytes(data)

    print(json.dumps(txn, indent=2, sort_keys=True))
    print("OPENOCD_PRODUCTION_TRANSACTION_V615_DRY_RUN_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

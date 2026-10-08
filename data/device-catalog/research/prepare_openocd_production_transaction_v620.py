#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
POLICY = HERE / "openocd-bounded-identifier-bridge-v6.19.json"

EXPECTED_EXACT_COUNT = 17
EXPECTED_FAMILIES = {"STM32F3", "STM32G0", "STM32L1"}
EXPECTED_EXACT_SET_SHA256 = "20b3910840a802a8855ad9022aa6bc67a35e8b169bd71726189eb803ded8636f"
EXPECTED_BINDING_SHA256 = "c986e9dbd6e365b3ed6a7054f62e01ae2cd0e18e15cb3841321d43d20fc94892"

BACKEND_FIELDS = (
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()

def exact_set_sha(icpns: list[str]) -> str:
    return sha256(("\n".join(sorted(icpns)) + "\n").encode())

def binding_sha(bridges: dict[str,dict[str,str]]) -> str:
    text = "\n".join(
        f"{icpn}|{b['existing_identifier']}|{b['existing_identifier_kind']}|{b['openocd_target_config']}"
        for icpn,b in sorted(bridges.items())
    ) + "\n"
    return sha256(text.encode())

def render_csv(fields: list[str], rows: list[dict[str,str]]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")

def build() -> tuple[dict[str,Any], dict[str,bytes], dict[str,bytes]]:
    policy_raw = POLICY.read_bytes()
    policy = json.loads(policy_raw)
    gov = policy["governance"]
    req(policy["scope"]["exact_icpn_count"] == EXPECTED_EXACT_COUNT, "v6.19 scope count drift")
    req(set(policy["scope"]["family_counts"]) == EXPECTED_FAMILIES, "v6.19 family scope drift")
    req(exact_set_sha(policy["scope"]["exact_icpns"]) == EXPECTED_EXACT_SET_SHA256,
        "v6.19 exact-set digest drift")
    req(binding_sha(policy["bridges"]) == EXPECTED_BINDING_SHA256,
        "v6.19 binding digest drift")
    req(gov["generic_one_char_generalization_authorized"] is False,
        "generic one-char normalization unexpectedly authorized")
    req(gov["exact_set_bridge_only"] is True, "v6.19 bounded scope drift")
    req(gov["production_mapping_write_authorized"] is False,
        "v6.19 unexpectedly authorizes Production write")

    manifest_pre = MANIFEST.read_bytes()
    manifest = json.loads(manifest_pre)
    req(len(manifest["sources"]) == 28, "Production source count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"]) == 4629,
        "Production exact total drift")

    source_by_family = {s["family"]: s for s in manifest["sources"]}
    req(EXPECTED_FAMILIES <= set(source_by_family), "affected family missing from manifest")

    preimages: dict[str,bytes] = {"MANIFEST": manifest_pre}
    postimages: dict[str,bytes] = {}
    affected_files: dict[str,Any] = {}
    seen: set[str] = set()

    for family in sorted(EXPECTED_FAMILIES):
        source = source_by_family[family]
        path = (MANIFEST.parent / source["path"]).resolve()
        pre = path.read_bytes()
        with io.StringIO(pre.decode("utf-8")) as stream:
            reader = csv.DictReader(stream)
            fields = list(reader.fieldnames or [])
            rows = list(reader)
        req(fields, f"{family}: missing CSV header")
        req(len(rows) == int(source["row_count"]), f"{family}: row count drift")

        family_bridges = {
            icpn:b for icpn,b in policy["bridges"].items()
            if icpn in set(policy["scope"]["exact_icpns"])
        }
        changed = 0
        for row in rows:
            icpn = row["icpn"]
            bridge = policy["bridges"].get(icpn)
            if bridge is None:
                continue
            req(row["family"] == family, f"{icpn}: family drift")
            req(row["mapping_status"] == "no_mapping", f"{icpn}: no longer no_mapping")
            for field in ("cmsis_device_name","existing_identifier","existing_identifier_kind","openocd_target_config"):
                req(row.get(field,"") == "", f"{icpn}: backend preimage field {field} not empty")
            before = dict(row)
            row["cmsis_device_name"] = ""
            row["existing_identifier"] = bridge["existing_identifier"]
            row["existing_identifier_kind"] = bridge["existing_identifier_kind"]
            row["mapping_status"] = "deterministic_ordering_pattern"
            row["openocd_target_config"] = bridge["openocd_target_config"]
            for key in fields:
                if key not in BACKEND_FIELDS:
                    req(row[key] == before[key], f"{icpn}: identity/metadata field changed: {key}")
            changed += 1
            seen.add(icpn)

        post = render_csv(fields, rows)
        req(changed > 0, f"{family}: no rows changed")
        preimages[family] = pre
        postimages[family] = post

        source["sha256"] = sha256(post)
        source["git_blob_sha"] = git_blob_sha(post)

        affected_files[family] = {
            "production_path": str(path.relative_to(ROOT)),
            "changed_exact_count": changed,
            "expected_row_count": int(source["row_count"]),
            "pre_sha256": sha256(pre),
            "pre_git_blob_sha": git_blob_sha(pre),
            "post_sha256": sha256(post),
            "post_git_blob_sha": git_blob_sha(post),
            "rollback_preimage_sha256": sha256(pre),
        }

    req(seen == set(policy["scope"]["exact_icpns"]),
        f"exact-set application drift: missing={sorted(set(policy['scope']['exact_icpns'])-seen)} extra={sorted(seen-set(policy['scope']['exact_icpns']))}")

    manifest_post = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    postimages["MANIFEST"] = manifest_post
    affected_files["MANIFEST"] = {
        "production_path": str(MANIFEST.relative_to(ROOT)),
        "pre_sha256": sha256(manifest_pre),
        "pre_git_blob_sha": git_blob_sha(manifest_pre),
        "post_sha256": sha256(manifest_post),
        "post_git_blob_sha": git_blob_sha(manifest_post),
        "rollback_preimage_sha256": sha256(manifest_pre),
    }

    txn = {
        "schema_version": 1,
        "transaction_id": "openocd-production-bounded-bridge-v6.20",
        "record_state": "DRY_RUN_TRANSACTION_REQUIRES_OWNER_APPROVAL",
        "source_policy": "openocd-bounded-identifier-bridge-v6.19",
        "source_policy_sha256": sha256(policy_raw),
        "promotion_exact_count": EXPECTED_EXACT_COUNT,
        "promotion_exact_set_sha256": EXPECTED_EXACT_SET_SHA256,
        "promotion_binding_sha256": EXPECTED_BINDING_SHA256,
        "affected_family_count": 3,
        "affected_family_counts": dict(sorted(Counter(
            next(
                family for family in EXPECTED_FAMILIES
                if icpn.startswith(family)
            )
            for icpn in policy["scope"]["exact_icpns"]
        ).items())),
        "affected_files": affected_files,
        "prestate": {
            "production_exact_total": 4629,
            "production_source_count": 28,
            "mapped": 4037,
            "no_mapping": 592,
            "active_openocd_route": 3958,
        },
        "poststate_if_approved": {
            "production_exact_total": 4629,
            "production_source_count": 28,
            "mapped": 4054,
            "no_mapping": 575,
            "active_openocd_route": 3975,
            "active_openocd_route_denominator": 4550,
            "active_openocd_route_coverage_percent": 87.3626,
        },
        "governance": {
            "production_write_authorized": False,
            "requires_explicit_owner_approval": True,
            "backend_fields_only": True,
            "identity_fields_immutable": True,
            "manifest_integrity_updates_only": True,
            "rollback_preimages_frozen": True,
            "generic_one_char_generalization_authorized": False,
            "exact_set_bridge_only": True,
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

    txn, before, after = build()
    if args.manifest_out:
        args.manifest_out.write_text(
            json.dumps(txn, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.package_dir:
        before_dir = args.package_dir / "before"
        after_dir = args.package_dir / "after"
        before_dir.mkdir(parents=True, exist_ok=True)
        after_dir.mkdir(parents=True, exist_ok=True)
        for key,data in before.items():
            name = "icpn-v1-manifest.json" if key == "MANIFEST" else f"{key}.csv"
            (before_dir / name).write_bytes(data)
        for key,data in after.items():
            name = "icpn-v1-manifest.json" if key == "MANIFEST" else f"{key}.csv"
            (after_dir / name).write_bytes(data)

    print(json.dumps(txn, indent=2, sort_keys=True))
    print("OPENOCD_PRODUCTION_TRANSACTION_V620_DRY_RUN_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

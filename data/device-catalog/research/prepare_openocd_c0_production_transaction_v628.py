#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
POLICY = HERE / "openocd-c0-production-backend-dry-run-v6.28.json"
V627_RECEIPT = HERE / "openocd-c0-canonical-route-write-v6.27.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

BACKEND_FIELDS = (
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
)

ROUTE_FIELDS = (
    "vendor","family","subfamily","plasma_series","part_number","identifier_kind",
    "cpu_architectures","target_config","openocd_distribution","mapping_status",
    "validation_status","catalog_origin",
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

def binding_sha(bindings: dict[str,dict[str,str]]) -> str:
    text = "\n".join(
        f"{icpn}|{b['existing_identifier']}|{b['existing_identifier_kind']}|{b['openocd_target_config']}"
        for icpn,b in sorted(bindings.items())
    ) + "\n"
    return sha256(text.encode())

def render_csv(fields: list[str], rows: list[dict[str,str]]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")

def read_csv_bytes(raw: bytes) -> tuple[list[str],list[dict[str,str]]]:
    with io.StringIO(raw.decode("utf-8")) as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    req(bool(fields), "CSV header missing")
    return fields, rows

def commercial_core(row: dict[str,str]) -> str:
    icpn = row["icpn"]
    suffix = row.get("option_suffix", "")
    if suffix and icpn.endswith(suffix):
        return icpn[:-len(suffix)]
    return icpn

def matching_routes(row: dict[str,str], routes: list[dict[str,str]]) -> list[dict[str,str]]:
    core = commercial_core(row)
    matches = []
    for route in routes:
        pattern = route.get("part_number", "")
        if (
            route.get("vendor") == "STMicroelectronics"
            and route.get("plasma_series") == "STM32C0"
            and route.get("identifier_kind") == "ordering_pattern"
            and route.get("target_config") == "tcl/target/stm32c0x.cfg"
            and pattern.endswith("x")
            and core.startswith(pattern[:-1])
        ):
            matches.append(route)
    unique = {
        (r["part_number"],r["identifier_kind"],r["target_config"]):r
        for r in matches
    }
    return list(unique.values())

def build() -> tuple[dict[str,Any],dict[str,bytes],dict[str,bytes]]:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    receipt = json.loads(V627_RECEIPT.read_text(encoding="utf-8"))

    scope = policy["scope"]
    bindings = policy["bindings"]
    req(scope["exact_icpn_count"] == 5, "scope count drift")
    req(set(bindings) == set(scope["exact_icpns"]), "binding scope drift")
    req(exact_set_sha(scope["exact_icpns"]) == scope["exact_set_sha256"], "exact-set hash drift")
    req(binding_sha(bindings) == scope["binding_sha256"], "binding hash drift")

    inventory = policy["route_inventory"]
    inv_path = ROOT / inventory["path"]
    inv_raw = inv_path.read_bytes()
    req(git_blob_sha(inv_raw) == inventory["git_blob_sha"], "v6.27 successor Git blob drift")
    req(sha256(inv_raw) == inventory["sha256"], "v6.27 successor SHA256 drift")
    inv_fields, routes = read_csv_bytes(inv_raw)
    req(tuple(inv_fields) == ROUTE_FIELDS, "route-inventory schema drift")
    req(len(routes) == inventory["row_count"] == 7661, "route-inventory row-count drift")

    receipt_scope = receipt["approved_scope"]
    req(receipt["transaction_id"] == inventory["source_transaction"], "v6.27 receipt identity drift")
    req(receipt_scope["successor_git_blob_sha"] == inventory["git_blob_sha"], "v6.27 receipt successor blob drift")
    req(receipt_scope["successor_sha256"] == inventory["sha256"], "v6.27 receipt successor hash drift")

    delta = policy["route_delta"]
    delta_path = ROOT / delta["path"]
    delta_raw = delta_path.read_bytes()
    req(sha256(delta_raw) == delta["sha256"], "route delta SHA256 drift")
    delta_fields, delta_rows = read_csv_bytes(delta_raw)
    req(tuple(delta_fields) == ROUTE_FIELDS, "route-delta schema drift")
    req(len(delta_rows) == delta["row_count"] == 4, "route-delta row-count drift")
    req(
        {r["part_number"] for r in delta_rows}
        == {b["existing_identifier"] for b in bindings.values()},
        "route delta pattern set differs from v6.28 bindings",
    )

    pre = policy["production_preimage"]
    manifest_raw = MANIFEST.read_bytes()
    req(git_blob_sha(manifest_raw) == pre["manifest_git_blob_sha"], "Production manifest preimage blob drift")
    req(sha256(manifest_raw) == pre["manifest_sha256"], "Production manifest preimage SHA drift")
    manifest = json.loads(manifest_raw)
    req(len(manifest["sources"]) == pre["production_source_count"] == 28, "Production source count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"]) == pre["production_exact_total"] == 4629,
        "Production exact total drift")

    source_by_family = {s["family"]:s for s in manifest["sources"]}
    c0_source = source_by_family["STM32C0"]
    c0_path = (MANIFEST.parent / c0_source["path"]).resolve()
    req(str(c0_path.relative_to(ROOT)) == pre["c0_path"], "C0 Production path drift")
    c0_raw = c0_path.read_bytes()
    req(git_blob_sha(c0_raw) == pre["c0_git_blob_sha"], "C0 Production preimage blob drift")
    req(sha256(c0_raw) == pre["c0_sha256"], "C0 Production preimage SHA drift")
    req(c0_source["git_blob_sha"] == pre["c0_git_blob_sha"], "manifest C0 blob binding drift")
    req(c0_source["sha256"] == pre["c0_sha256"], "manifest C0 SHA binding drift")

    c0_fields,c0_rows = read_csv_bytes(c0_raw)
    req(len(c0_rows) == c0_source["row_count"] == pre["c0_row_count"] == 226, "C0 row-count drift")

    mapped = no_mapping = 0
    for source in manifest["sources"]:
        path = (MANIFEST.parent / source["path"]).resolve()
        with path.open(newline="",encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["mapping_status"] == "no_mapping":
                    no_mapping += 1
                else:
                    mapped += 1
    req(mapped == pre["mapped"] == 4054, f"mapped prestate drift: {mapped}")
    req(no_mapping == pre["no_mapping"] == 575, f"no_mapping prestate drift: {no_mapping}")

    before_rows = [dict(r) for r in c0_rows]
    seen:set[str] = set()
    for row in c0_rows:
        icpn = row["icpn"]
        expected = bindings.get(icpn)
        if expected is None:
            continue

        req(row["family"] == "STM32C0", f"{icpn}: family drift")
        req(row["mapping_status"] == "no_mapping", f"{icpn}: no longer no_mapping")
        for field in ("cmsis_device_name","existing_identifier","existing_identifier_kind","openocd_target_config"):
            req(row.get(field,"") == "", f"{icpn}: backend preimage field {field} is not empty")

        matches = matching_routes(row,routes)
        req(len(matches) == 1, f"{icpn}: successor route resolution count={len(matches)}")
        match = matches[0]
        req(match["part_number"] == expected["existing_identifier"], f"{icpn}: successor resolved wrong identifier")
        req(match["identifier_kind"] == expected["existing_identifier_kind"], f"{icpn}: successor identifier kind drift")
        req(match["target_config"] == expected["openocd_target_config"], f"{icpn}: successor target drift")

        before = dict(row)
        row["cmsis_device_name"] = ""
        row["existing_identifier"] = expected["existing_identifier"]
        row["existing_identifier_kind"] = expected["existing_identifier_kind"]
        row["mapping_status"] = "deterministic_ordering_pattern"
        row["openocd_target_config"] = expected["openocd_target_config"]

        for field in c0_fields:
            if field not in BACKEND_FIELDS:
                req(row[field] == before[field], f"{icpn}: immutable field changed: {field}")
        seen.add(icpn)

    req(seen == set(scope["exact_icpns"]), f"exact-set application drift: {sorted(seen)}")

    before_by_icpn = {r["icpn"]:r for r in before_rows}
    after_by_icpn = {r["icpn"]:r for r in c0_rows}
    for icpn in set(before_by_icpn) - set(scope["exact_icpns"]):
        req(before_by_icpn[icpn] == after_by_icpn[icpn], f"{icpn}: out-of-scope C0 row changed")

    c0_post = render_csv(c0_fields,c0_rows)

    manifest_after = deepcopy(manifest)
    after_source = next(s for s in manifest_after["sources"] if s["family"] == "STM32C0")
    after_source["sha256"] = sha256(c0_post)
    after_source["git_blob_sha"] = git_blob_sha(c0_post)

    manifest_compare_before = deepcopy(manifest)
    manifest_compare_after = deepcopy(manifest_after)
    before_c0 = next(s for s in manifest_compare_before["sources"] if s["family"] == "STM32C0")
    after_c0 = next(s for s in manifest_compare_after["sources"] if s["family"] == "STM32C0")
    before_c0["sha256"] = after_c0["sha256"]
    before_c0["git_blob_sha"] = after_c0["git_blob_sha"]
    req(manifest_compare_before == manifest_compare_after, "manifest changed outside C0 integrity hashes")

    manifest_post = (json.dumps(manifest_after,indent=2) + "\n").encode("utf-8")

    projected = policy["projected_poststate"]
    req(projected["mapped"] == mapped + 5 == 4059, "projected mapped count drift")
    req(projected["no_mapping"] == no_mapping - 5 == 570, "projected no_mapping count drift")
    req(projected["active_openocd_route"] == pre["active_openocd_route"] + 5 == 3980,
        "projected active route drift")
    req(projected["active_openocd_route_denominator"] == 4550, "active denominator drift")
    req(round(3980/4550*100,4) == projected["active_openocd_route_coverage_percent"] == 87.4725,
        "coverage projection drift")

    frozen = policy["frozen_postimages"]
    c0_post_blob = git_blob_sha(c0_post)
    c0_post_sha = sha256(c0_post)
    manifest_post_blob = git_blob_sha(manifest_post)
    manifest_post_sha = sha256(manifest_post)

    if frozen["lock_state"] == "FROZEN":
        req(frozen["c0_git_blob_sha"] == c0_post_blob, "frozen C0 postimage blob mismatch")
        req(frozen["c0_sha256"] == c0_post_sha, "frozen C0 postimage SHA mismatch")
        req(frozen["c0_byte_count"] == len(c0_post), "frozen C0 postimage byte count mismatch")
        req(frozen["manifest_git_blob_sha"] == manifest_post_blob, "frozen manifest postimage blob mismatch")
        req(frozen["manifest_sha256"] == manifest_post_sha, "frozen manifest postimage SHA mismatch")
        req(frozen["manifest_byte_count"] == len(manifest_post), "frozen manifest postimage byte count mismatch")
    else:
        req(frozen["lock_state"] == "DISCOVERY_PENDING", "unknown postimage lock state")
        req(all(frozen[k] is None for k in (
            "c0_git_blob_sha","c0_sha256","c0_byte_count",
            "manifest_git_blob_sha","manifest_sha256","manifest_byte_count"
        )), "partial postimage lock in discovery state")

    gov = policy["governance"]
    req(gov["production_write_authorized"] is False, "dry-run self-authorized Production write")
    req(gov["requires_explicit_owner_approval"] is True, "owner approval gate missing")
    req(gov["backend_fields_only"] is True, "backend-only boundary disabled")
    req(gov["identity_fields_immutable"] is True, "identity immutability disabled")
    req(gov["manifest_integrity_updates_only"] is True, "manifest mutation boundary disabled")
    req(gov["rollback_preimages_frozen"] is True, "rollback preimages not frozen")
    req(gov["route_inventory_successor_explicit"] is True, "successor source not explicit")
    req(gov["exact_set_only"] is True, "exact-set boundary disabled")
    for key in (
        "programming_profile_binding_claimed","programming_verified_claimed",
        "engineering_verified_claimed","hil_verified_claimed",
    ):
        req(gov[key] is False, f"v6.28 overclaim: {key}")

    txn = {
        "schema_version":1,
        "transaction_id":policy["transaction_id"],
        "record_state":"DRY_RUN_ONLY",
        "postimage_lock_state":frozen["lock_state"],
        "route_inventory":{
            "path":inventory["path"],
            "git_blob_sha":git_blob_sha(inv_raw),
            "sha256":sha256(inv_raw),
            "row_count":len(routes),
        },
        "promotion_exact_count":5,
        "promotion_exact_set_sha256":scope["exact_set_sha256"],
        "promotion_binding_sha256":scope["binding_sha256"],
        "affected_family_count":1,
        "affected_family_counts":{"STM32C0":5},
        "affected_files":{
            "STM32C0":{
                "production_path":pre["c0_path"],
                "changed_exact_count":5,
                "expected_row_count":226,
                "pre_sha256":sha256(c0_raw),
                "pre_git_blob_sha":git_blob_sha(c0_raw),
                "post_sha256":c0_post_sha,
                "post_git_blob_sha":c0_post_blob,
                "post_byte_count":len(c0_post),
                "rollback_preimage_sha256":sha256(c0_raw),
                "rollback_preimage_git_blob_sha":git_blob_sha(c0_raw),
            },
            "MANIFEST":{
                "production_path":pre["manifest_path"],
                "pre_sha256":sha256(manifest_raw),
                "pre_git_blob_sha":git_blob_sha(manifest_raw),
                "post_sha256":manifest_post_sha,
                "post_git_blob_sha":manifest_post_blob,
                "post_byte_count":len(manifest_post),
                "rollback_preimage_sha256":sha256(manifest_raw),
                "rollback_preimage_git_blob_sha":git_blob_sha(manifest_raw),
            },
        },
        "prestate":{
            "production_exact_total":4629,
            "production_source_count":28,
            "mapped":mapped,
            "no_mapping":no_mapping,
            "active_openocd_route":pre["active_openocd_route"],
            "active_openocd_route_denominator":4550,
            "active_openocd_route_coverage_percent":round(pre["active_openocd_route"]/4550*100,4),
        },
        "poststate_if_approved":projected,
        "governance":gov,
    }
    before={"STM32C0":c0_raw,"MANIFEST":manifest_raw}
    after={"STM32C0":c0_post,"MANIFEST":manifest_post}
    return txn,before,after

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--transaction-out",type=Path)
    parser.add_argument("--package-dir",type=Path)
    args=parser.parse_args()

    txn,before,after=build()
    if args.transaction_out:
        args.transaction_out.write_text(json.dumps(txn,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if args.package_dir:
        before_dir=args.package_dir/"before"
        after_dir=args.package_dir/"after"
        before_dir.mkdir(parents=True,exist_ok=True)
        after_dir.mkdir(parents=True,exist_ok=True)
        before_dir.joinpath("STM32C0.csv").write_bytes(before["STM32C0"])
        before_dir.joinpath("icpn-v1-manifest.json").write_bytes(before["MANIFEST"])
        after_dir.joinpath("STM32C0.csv").write_bytes(after["STM32C0"])
        after_dir.joinpath("icpn-v1-manifest.json").write_bytes(after["MANIFEST"])

    print(json.dumps(txn,indent=2,sort_keys=True))
    print("OPENOCD_C0_PRODUCTION_TRANSACTION_V628_DRY_RUN_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

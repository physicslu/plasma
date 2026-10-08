#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
POLICY = HERE / "openocd-bounded-identifier-bridge-v6.19.json"
EVIDENCE = HERE / "openocd-production-backend-mapping-v6.21.json"

EXPECTED_POST = {
    "STM32F3": {
        "sha256": "0c48633a81ff6eb8785d5e730ee06f6f596a30f2264b4fea374d8df62b3f1573",
        "git_blob_sha": "42e3cab58f7863e1cf44502cb15c5d85086e2a0e",
    },
    "STM32G0": {
        "sha256": "8d6a556364835a00aa479434ebd10977721fb61b2d45485e4e662620a33fcdef",
        "git_blob_sha": "504623e5f7dd459336cc805d00af5636901dc19e",
    },
    "STM32L1": {
        "sha256": "8271258806e3ef240c33818c975f0a3928c27312999b4c1c737f7fc3e2a1e99c",
        "git_blob_sha": "ace1ca1d0be56b24e1ab7fc9a388c7da518eeead",
    },
}
EXPECTED_MANIFEST_SHA256 = "6bd23d2bf0b31fe0302e23add861abcf92f8500755c0649ee8adc335608c3d70"
EXPECTED_MANIFEST_BLOB = "f3c65c166e49b107d0bd25050062f8084aeeda30"


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)

    req(sha256(manifest_raw) == EXPECTED_MANIFEST_SHA256, "manifest post SHA drift")
    req(git_blob_sha(manifest_raw) == EXPECTED_MANIFEST_BLOB, "manifest post blob drift")
    req(len(manifest["sources"]) == 28, "Production source count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"]) == 4629, "Production exact total drift")

    source_by_family = {s["family"]: s for s in manifest["sources"]}
    rows_by_icpn = {}
    mapped = 0
    no_mapping = 0

    for source in manifest["sources"]:
        path = (MANIFEST.parent / source["path"]).resolve()
        raw = path.read_bytes()
        if source["family"] in EXPECTED_POST:
            expected = EXPECTED_POST[source["family"]]
            req(sha256(raw) == expected["sha256"], f"{source['family']}: post SHA drift")
            req(git_blob_sha(raw) == expected["git_blob_sha"], f"{source['family']}: post blob drift")
            req(source["sha256"] == expected["sha256"], f"{source['family']}: manifest SHA binding drift")
            req(source["git_blob_sha"] == expected["git_blob_sha"], f"{source['family']}: manifest blob binding drift")
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        req(len(rows) == int(source["row_count"]), f"{source['family']}: row-count drift")
        for row in rows:
            req(row["icpn"] not in rows_by_icpn, f"{row['icpn']}: duplicate Production ICPN")
            rows_by_icpn[row["icpn"]] = row
            if row["mapping_status"] == "no_mapping":
                no_mapping += 1
            else:
                mapped += 1

    req(mapped == 4054, f"mapped poststate drift: {mapped}")
    req(no_mapping == 575, f"no_mapping poststate drift: {no_mapping}")

    bridges = policy["bridges"]
    req(len(bridges) == 17, "v6.19 bridge scope drift")
    for icpn, bridge in bridges.items():
        row = rows_by_icpn[icpn]
        req(row["cmsis_device_name"] == "", f"{icpn}: unexpected CMSIS binding")
        req(row["existing_identifier"] == bridge["existing_identifier"], f"{icpn}: identifier drift")
        req(row["existing_identifier_kind"] == bridge["existing_identifier_kind"], f"{icpn}: identifier kind drift")
        req(row["openocd_target_config"] == bridge["openocd_target_config"], f"{icpn}: target config drift")
        req(row["mapping_status"] == "deterministic_ordering_pattern", f"{icpn}: mapping status drift")

    req(evidence["promotion_exact_count"] == 17, "evidence exact count drift")
    req(evidence["poststate"]["mapped"] == 4054, "evidence mapped drift")
    req(evidence["poststate"]["no_mapping"] == 575, "evidence no_mapping drift")
    req(evidence["poststate"]["active_openocd_route"] == 3975, "evidence active route drift")
    req(evidence["poststate"]["active_openocd_route_coverage_percent"] == 87.3626, "evidence coverage drift")

    gov = evidence["governance"]
    req(gov["merge_requires_explicit_owner_approval"] is True, "merge gate opened")
    req(gov["backend_fields_only"] is True, "backend-only boundary drift")
    req(gov["identity_fields_immutable"] is True, "identity immutability drift")
    req(gov["generic_one_char_generalization_authorized"] is False, "generic one-char rule authorized")
    for key in (
        "programming_profile_binding_claimed",
        "programming_verified_claimed",
        "engineering_verified_claimed",
        "hil_verified_claimed",
    ):
        req(gov[key] is False, f"v6.21 overclaim: {key}")

    print("OPENOCD_PRODUCTION_WRITE_V621_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SNAPSHOT = HERE / "stm32u5-exact-orderable-identity-enumeration.json"
PARENT = HERE / "stm32u5-manufacturer-identity-discovery.json"
SECURITY = HERE / "stm32u5-security-scope-foundation.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"

EXPECTED_PRODUCTION = 2017
EXPECTED_BASE_COUNT = 74
EXPECTED_BASE_HASH = "ab83ea88d30d173e3809b3c1245691a0fb6be4a78f6fa35bd47f6caa8533bcdf"
EXPECTED_EXACT_COUNT = 266
EXPECTED_EXACT_HASH = "ea5e3edc302a022281618ecfa73af8ac6109ad287dcf36e6f1175d20f567caf3"
EXPECTED_STATUS_COUNTS = {
    "Active Product is in volume production.": 265,
    "Preview Product is in design stage. EN": 1,
}
EXPECTED_PROVENANCE = [
    {
        "stage": "first_pass_dual_surface",
        "run_id": 35041196885,
        "artifact_id": 10426086086,
        "artifact_sha256": "92dd546e14da115aab06abfe403b58bf53123f4af2158c9388a3b8a6494d31a2",
        "head_sha": "d25c4337a0ef7a16bd7c2e69b1ffee673b181d99",
        "base_devices": 63,
        "exact_icpns": 211,
    },
    {
        "stage": "bounded_qr_retry",
        "run_id": 35045120632,
        "artifact_id": 10426716893,
        "artifact_sha256": "d9df421105005893d0306559b8b7d88926010ad21246ec5d44f605dab94dbf86",
        "head_sha": "627c017629ca4af7516576e759b617811c0a04cf",
        "base_devices": 11,
        "merged_exact_icpns": 266,
    },
]
BASE_RE = re.compile(r"^STM32U5[A-Z0-9]+$")
ICPN_RE = re.compile(r"^STM32U5[A-Z0-9]+$")


def req(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def digest(values: list[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def production_count(manifest: dict) -> int:
    sources = manifest.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    return sum(int(row.get("row_count", -1)) for row in sources if isinstance(row, dict))


def validate(
    snapshot: dict,
    parent: dict,
    security: dict,
    production: dict,
    policy: dict,
) -> None:
    req(snapshot.get("schema_version") == 1, "snapshot schema version drifted")
    req(snapshot.get("transaction") == "stm32u5-exact-orderable-identity-enumeration", "snapshot transaction drifted")
    req(snapshot.get("authority") == "research_only", "exact identity snapshot escaped research_only")
    req(snapshot.get("parent_identity_discovery") == PARENT.name, "parent discovery binding drifted")
    req(snapshot.get("series") == "STM32U5", "snapshot series drifted")
    req(snapshot.get("manufacturer") == "STMicroelectronics", "snapshot manufacturer drifted")
    req(snapshot.get("observed_at") == "2026-09-16", "snapshot observation date drifted")
    req(snapshot.get("identity_authority") == "ST Quality & Reliability exact Part Number rows", "identity authority drifted")
    req("no synthesized order codes" in str(snapshot.get("identity_scope", "")), "no-synthesis scope missing")
    req(snapshot.get("production_exact_icpn_count") == EXPECTED_PRODUCTION, "snapshot Production count drifted")
    req(production_count(production) == EXPECTED_PRODUCTION, "Production manifest count drifted")

    req(snapshot.get("acquisition_provenance") == EXPECTED_PROVENANCE, "acquisition provenance drifted")
    req(snapshot.get("base_device_count") == EXPECTED_BASE_COUNT, "snapshot Base Device count drifted")
    req(snapshot.get("exact_icpn_count") == EXPECTED_EXACT_COUNT, "snapshot exact ICPN count drifted")
    req(snapshot.get("exact_icpn_set_sha256") == EXPECTED_EXACT_HASH, "snapshot exact ICPN digest drifted")
    req(snapshot.get("marketing_status_counts") == EXPECTED_STATUS_COUNTS, "snapshot Marketing Status counts drifted")
    req(snapshot.get("next_research_gate") == "stm32u5-metadata-policy", "snapshot next gate drifted")

    req(parent.get("transaction") == "stm32u5-manufacturer-identity-discovery", "parent discovery missing")
    req(parent.get("authority") == "research_only", "parent authority drifted")
    req(parent.get("production_exact_icpn_count") == EXPECTED_PRODUCTION, "parent Production count drifted")
    parent_bases = parent.get("base_devices")
    req(isinstance(parent_bases, list) and len(parent_bases) == EXPECTED_BASE_COUNT, "parent Base Device set missing")
    req(len(set(parent_bases)) == EXPECTED_BASE_COUNT, "parent Base Device set contains duplicates")
    req(digest(parent_bases) == EXPECTED_BASE_HASH, "parent Base Device digest drifted")
    req(parent.get("base_device_set_sha256") == EXPECTED_BASE_HASH, "parent recorded Base Device digest drifted")

    exact_boundary = parent.get("exact_orderable_identity_enumeration")
    req(isinstance(exact_boundary, dict), "parent exact identity boundary missing")
    req(exact_boundary.get("complete") is True, "parent exact identity enumeration is not complete")
    req(exact_boundary.get("observed_at") == "2026-09-16", "parent exact identity observation date drifted")
    req(exact_boundary.get("identity_authority") == "ST Quality & Reliability exact Part Number rows", "parent exact identity authority drifted")
    req(exact_boundary.get("snapshot") == SNAPSHOT.name, "parent exact identity snapshot binding drifted")
    req(exact_boundary.get("exact_icpn_count") == EXPECTED_EXACT_COUNT, "parent exact ICPN count drifted")
    req(exact_boundary.get("exact_icpn_set_sha256") == EXPECTED_EXACT_HASH, "parent exact ICPN digest drifted")
    req(exact_boundary.get("synthesized_exact_icpns") == 0, "parent synthesized exact ICPN count drifted")
    req(parent.get("claims", {}).get("exact_icpn_enumeration_complete") is True, "parent completion claim missing")
    req(parent.get("next_research_gate") == "stm32u5-metadata-policy", "parent next gate drifted")

    records = snapshot.get("base_device_records")
    req(isinstance(records, list) and len(records) == EXPECTED_BASE_COUNT, "snapshot Base Device records drifted")
    seen_bases: set[str] = set()
    seen_icpns: set[str] = set()
    statuses: Counter[str] = Counter()
    for item in records:
        req(isinstance(item, list) and len(item) == 2, "invalid Base Device record shape")
        base, part_records = item
        req(isinstance(base, str) and BASE_RE.fullmatch(base) is not None, f"invalid Base Device: {base}")
        req(base not in seen_bases, f"duplicate Base Device record: {base}")
        req(isinstance(part_records, list) and part_records, f"{base}: no exact Part Number records")
        seen_bases.add(base)
        for part in part_records:
            req(isinstance(part, list) and len(part) == 2, f"{base}: invalid exact Part Number record shape")
            icpn, status = part
            req(isinstance(icpn, str) and ICPN_RE.fullmatch(icpn) is not None, f"invalid exact ICPN: {icpn}")
            req(icpn.startswith(base), f"Base Device/exact ICPN mismatch: {base} -> {icpn}")
            req(icpn not in seen_icpns, f"duplicate exact ICPN: {icpn}")
            req(status in EXPECTED_STATUS_COUNTS, f"unrecognized Marketing Status: {icpn}")
            seen_icpns.add(icpn)
            statuses[status] += 1

    req(seen_bases == set(parent_bases), "snapshot/parent Base Device set mismatch")
    req(len(seen_icpns) == EXPECTED_EXACT_COUNT, "enumerated exact ICPN count drifted")
    req(digest(list(seen_icpns)) == EXPECTED_EXACT_HASH, "enumerated exact ICPN digest drifted")
    req(dict(statuses) == EXPECTED_STATUS_COUNTS, "enumerated Marketing Status counts drifted")

    result = snapshot.get("result")
    req(isinstance(result, dict), "snapshot result missing")
    req(result.get("bounded_identity_enumeration_clean") is True, "bounded identity enumeration is not clean")
    req(result.get("complete_exact_identity_observation") is True, "complete identity observation missing")
    req(result.get("base_devices_with_exact_identity") == EXPECTED_BASE_COUNT, "Base Device identity coverage drifted")
    req(result.get("acquisition_failures") == 0, "acquisition failures admitted")
    req(result.get("duplicate_exact_icpns") == 0, "duplicate exact ICPNs admitted")
    req(result.get("synthesized_exact_icpns") == 0, "synthetic exact ICPNs admitted")

    claims = snapshot.get("claims")
    req(isinstance(claims, dict) and claims, "snapshot claims missing")
    req(all(value is False for value in claims.values()), "capability/admission claim escaped false")
    parent_claims = parent.get("claims")
    req(isinstance(parent_claims, dict), "parent claims missing")
    req(parent_claims.get("catalog_admission_blocked_by_hil") is False, "HIL coupling reintroduced")
    for key in (
        "physical_validation_claimed",
        "security_semantics_supported",
        "runtime_programming_supported",
        "debug_attach_supported",
        "hil_validated",
    ):
        req(parent_claims.get(key) is False, f"parent forbidden capability claim enabled: {key}")

    admission = policy.get("catalog_admission")
    physical = policy.get("physical_validation")
    req(isinstance(admission, dict), "catalog admission policy missing")
    req(admission.get("requires_ppu_hil") is False, "PPU HIL leaked into catalog admission")
    req(admission.get("requires_socket_hil") is False, "Socket HIL leaked into catalog admission")
    req(admission.get("requires_physical_programming_success") is False, "physical programming leaked into catalog admission")
    req(isinstance(physical, dict) and physical.get("independent_from_catalog_admission") is True, "physical validation separation drifted")

    req(security.get("transaction") == "stm32u5-security-scope-foundation", "security foundation missing")
    req(security.get("exact_icpn_count") == EXPECTED_PRODUCTION, "security Production count drifted")


def expect_rejected(name: str, snapshot: dict, parent: dict, security: dict, production: dict, policy: dict) -> None:
    try:
        validate(snapshot, parent, security, production, policy)
    except ValueError:
        return
    raise SystemExit(f"FAIL: negative control admitted: {name}")


def negative_controls(snapshot: dict, parent: dict, security: dict, production: dict, policy: dict) -> int:
    rejected = 0

    wrong_count = copy.deepcopy(snapshot)
    wrong_count["exact_icpn_count"] = EXPECTED_EXACT_COUNT - 1
    expect_rejected("exact count drift", wrong_count, copy.deepcopy(parent), security, production, policy); rejected += 1

    wrong_hash = copy.deepcopy(snapshot)
    wrong_hash["exact_icpn_set_sha256"] = "0" * 64
    expect_rejected("exact digest drift", wrong_hash, copy.deepcopy(parent), security, production, policy); rejected += 1

    duplicate = copy.deepcopy(snapshot)
    duplicate["base_device_records"][0][1][1][0] = duplicate["base_device_records"][0][1][0][0]
    expect_rejected("duplicate exact ICPN", duplicate, copy.deepcopy(parent), security, production, policy); rejected += 1

    bad_status = copy.deepcopy(snapshot)
    bad_status["base_device_records"][0][1][0][1] = "Unknown"
    expect_rejected("unknown Marketing Status", bad_status, copy.deepcopy(parent), security, production, policy); rejected += 1

    synthesized = copy.deepcopy(snapshot)
    synthesized["base_device_records"][0][1][0][0] = "STM32U535CBZZ"
    expect_rejected("synthetic identity", synthesized, copy.deepcopy(parent), security, production, policy); rejected += 1

    incomplete_parent = copy.deepcopy(parent)
    incomplete_parent["exact_orderable_identity_enumeration"]["complete"] = False
    incomplete_parent["claims"]["exact_icpn_enumeration_complete"] = False
    expect_rejected("parent completion regression", copy.deepcopy(snapshot), incomplete_parent, security, production, policy); rejected += 1

    production_claim = copy.deepcopy(snapshot)
    production_claim["claims"]["production_admission_authorized"] = True
    expect_rejected("Production admission inferred", production_claim, copy.deepcopy(parent), security, production, policy); rejected += 1

    hil = copy.deepcopy(parent)
    hil["claims"]["catalog_admission_blocked_by_hil"] = True
    expect_rejected("HIL coupling", copy.deepcopy(snapshot), hil, security, production, policy); rejected += 1

    return rejected


def main() -> int:
    snapshot = load_json(SNAPSHOT)
    parent = load_json(PARENT)
    security = load_json(SECURITY)
    production = load_json(PRODUCTION)
    policy = load_json(POLICY)
    validate(snapshot, parent, security, production, policy)
    rejected = negative_controls(snapshot, parent, security, production, policy)
    req(rejected == 8, "negative-control rejection count drifted")
    print("STM32U5 exact orderable identity enumeration: PASS")
    print("base_devices=74")
    print("exact_icpns=266")
    print("active=265")
    print("preview=1")
    print("synthesized_exact_icpns=0")
    print("negative_controls_rejected=8")
    print("production_exact_icpn_count=2017")
    print("production_admission_authorized=false")
    print("next_research_gate=stm32u5-metadata-policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

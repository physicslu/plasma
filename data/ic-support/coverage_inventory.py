#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PRODUCTION_MANIFEST = REPO_ROOT / "data" / "device-catalog" / "production" / "icpn-v1-manifest.json"
BINDINGS_ROOT = HERE / "bindings"
PROFILE_ROOT = HERE / "profiles"


class CoverageError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CoverageError(message)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    require(isinstance(payload, dict), f"{path}: top-level JSON must be an object")
    return payload


def git_blob_sha_bytes(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def load_production_catalog() -> tuple[dict[str, Any], list[dict[str, str]]]:
    manifest = load_json(PRODUCTION_MANIFEST)
    require(manifest.get("status") == "production", "Device Catalog manifest must be production")
    require(
        manifest.get("selection_policy") == "admitted_exact_manufacturer_part_number_only",
        "Device Catalog selection policy must remain exact-ICPN-only",
    )
    sources = manifest.get("sources")
    require(isinstance(sources, list) and sources, "production manifest must contain sources")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        require(isinstance(source, dict), "production source entries must be objects")
        relative_path = source.get("path")
        require(isinstance(relative_path, str) and relative_path, "production source path is required")
        path = (PRODUCTION_MANIFEST.parent / relative_path).resolve()
        require(path.is_file(), f"production source not found: {path}")
        payload = path.read_bytes()
        require(
            hashlib.sha256(payload).hexdigest() == source.get("sha256"),
            f"{path}: production SHA-256 drift",
        )
        require(
            git_blob_sha_bytes(payload) == source.get("git_blob_sha"),
            f"{path}: production Git blob drift",
        )
        with path.open("r", encoding="utf-8", newline="") as handle:
            source_rows = list(csv.DictReader(handle))
        require(len(source_rows) == source.get("row_count"), f"{path}: production row-count drift")
        for row in source_rows:
            icpn = (row.get("icpn") or "").strip()
            require(icpn, f"{path}: empty ICPN")
            require(icpn not in seen, f"duplicate production ICPN: {icpn}")
            seen.add(icpn)
            rows.append(row)
    return manifest, rows


def load_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(PROFILE_ROOT.glob("*/*.json")):
        payload = load_json(path)
        profile_id = payload.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id:
            continue
        require(profile_id not in profiles, f"duplicate profile_id: {profile_id}")
        profiles[profile_id] = payload
    return profiles


def load_programming_bindings(
    production_icpns: set[str], profiles: dict[str, dict[str, Any]]
) -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for path in sorted(BINDINGS_ROOT.glob("*.json")):
        payload = load_json(path)
        binding_set_id = payload.get("binding_set_id")
        entries = payload.get("bindings")
        require(isinstance(entries, list), f"{path}: bindings must be an array")
        for entry in entries:
            require(isinstance(entry, dict), f"{path}: binding entry must be an object")
            icpn = entry.get("icpn")
            require(isinstance(icpn, str) and icpn, f"{path}: binding ICPN is required")
            require(icpn in production_icpns, f"{icpn}: IC Support binding is not in production Device Catalog")
            require(icpn not in bindings, f"duplicate IC Support binding for {icpn}")
            refs = entry.get("profiles")
            require(isinstance(refs, dict), f"{icpn}: profiles object is required")
            programming = refs.get("programming")
            require(isinstance(programming, str) and programming, f"{icpn}: programming profile is required")
            require(programming in profiles, f"{icpn}: dangling programming profile {programming!r}")
            profile = profiles[programming]
            require(profile.get("kind") == "programming", f"{programming}: expected programming profile")
            status = profile.get("status")
            require(isinstance(status, str) and status, f"{programming}: profile status is required")
            bindings[icpn] = {
                "binding_set_id": str(binding_set_id),
                "programming_profile_id": programming,
                "programming_profile_status": status,
            }
    return bindings


def summarize_base_device(
    manufacturer: str,
    base_device: str,
    members: list[dict[str, str]],
    bindings: dict[str, dict[str, str]],
) -> dict[str, Any]:
    require(members, f"{base_device}: base-device group must not be empty")
    families = {row["family"] for row in members}
    flash_sizes = {row["flash_size"] for row in members}
    openocd_targets = {row["openocd_target_config"] for row in members if row.get("openocd_target_config")}
    require(len(families) == 1, f"{base_device}: base device spans multiple families: {sorted(families)}")
    require(len(flash_sizes) == 1, f"{base_device}: base device has conflicting Flash sizes: {sorted(flash_sizes)}")
    require(
        len(openocd_targets) <= 1,
        f"{base_device}: base device has conflicting OpenOCD targets: {sorted(openocd_targets)}",
    )

    bound_profile_ids = {
        bindings[row["icpn"]]["programming_profile_id"]
        for row in members
        if row["icpn"] in bindings
    }
    require(
        len(bound_profile_ids) <= 1,
        f"{base_device}: bound exact ICPNs disagree on programming profile: {sorted(bound_profile_ids)}",
    )

    if bound_profile_ids:
        profile_state = "partially_or_fully_bound"
        profile_id = next(iter(bound_profile_ids))
    else:
        profile_state = "unresolved"
        profile_id = None

    return {
        "manufacturer": manufacturer,
        "family": next(iter(families)),
        "base_device": base_device,
        "exact_icpn_count": len(members),
        "flash_size": next(iter(flash_sizes)),
        "openocd_target_config": next(iter(openocd_targets)) if openocd_targets else None,
        "programming_profile_state": profile_state,
        "programming_profile_id": profile_id,
        "bound_exact_icpn_count": sum(1 for row in members if row["icpn"] in bindings),
    }


def build_inventory() -> dict[str, Any]:
    manifest, rows = load_production_catalog()
    production_icpns = {row["icpn"] for row in rows}
    profiles = load_profiles()
    bindings = load_programming_bindings(production_icpns, profiles)

    base_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    family_counts: Counter[str] = Counter()
    openocd_mapped_count = 0
    inventory_rows: list[dict[str, Any]] = []

    for row in rows:
        manufacturer = row["manufacturer"]
        family = row["family"]
        base_device = row["base_device"]
        family_counts[family] += 1
        base_rows[(manufacturer, base_device)].append(row)

        mapping_status = row.get("mapping_status", "")
        openocd_target = row.get("openocd_target_config", "")
        deterministic_openocd = bool(openocd_target) and mapping_status.startswith("deterministic")
        if deterministic_openocd:
            openocd_mapped_count += 1

        binding = bindings.get(row["icpn"])
        if binding:
            profile_state = "evidence_backed_pilot"
            profile_id: str | None = binding["programming_profile_id"]
            native_ppu_state = "profile_available_research_only"
        else:
            profile_state = "unresolved"
            profile_id = None
            native_ppu_state = "profile_unresolved"

        inventory_rows.append(
            {
                "manufacturer": manufacturer,
                "family": family,
                "series": row["series"],
                "icpn": row["icpn"],
                "base_device": base_device,
                "package": row["package"],
                "pin_count": int(row["pin_count"]),
                "flash_size": row["flash_size"],
                "openocd": {
                    "state": "deterministic_target_mapped" if deterministic_openocd else "unresolved",
                    "target_config": openocd_target or None,
                    "mapping_status": mapping_status or None,
                },
                "programming_profile": {
                    "state": profile_state,
                    "profile_id": profile_id,
                    "status": binding["programming_profile_status"] if binding else None,
                },
                "native_ppu": {
                    "state": native_ppu_state,
                    "runtime_resolver": "not_implemented",
                    "runtime_ready": False,
                },
            }
        )

    base_devices = [
        summarize_base_device(manufacturer, base_device, members, bindings)
        for (manufacturer, base_device), members in sorted(base_rows.items())
    ]

    programming_profile_ids = sorted({binding["programming_profile_id"] for binding in bindings.values()})
    inventory_rows.sort(key=lambda item: (item["family"], item["base_device"], item["icpn"]))

    return {
        "schema_version": 1,
        "source": {
            "catalog_id": manifest.get("catalog_id"),
            "catalog_version": manifest.get("catalog_version"),
            "selection_policy": manifest.get("selection_policy"),
            "production_manifest": str(PRODUCTION_MANIFEST.relative_to(REPO_ROOT)),
        },
        "metrics": {
            "exact_icpns": len(rows),
            "families": len(family_counts),
            "family_exact_icpns": dict(sorted(family_counts.items())),
            "base_devices": len(base_devices),
            "deterministic_openocd_exact_icpns": openocd_mapped_count,
            "ic_support_bound_exact_icpns": len(bindings),
            "unresolved_programming_profile_exact_icpns": len(rows) - len(bindings),
            "evidence_backed_programming_profiles": len(programming_profile_ids),
            "native_ppu_runtime_ready_exact_icpns": 0,
        },
        "programming_profile_ids": programming_profile_ids,
        "base_devices": base_devices,
        "exact_icpns": inventory_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the derived production IC Support coverage inventory")
    parser.add_argument("--json", action="store_true", help="emit the complete deterministic inventory as JSON")
    parser.add_argument("--summary", action="store_true", help="emit only summary metrics as JSON")
    args = parser.parse_args()

    inventory = build_inventory()
    payload: Any = inventory["metrics"] if args.summary else inventory
    if args.json or args.summary:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        metrics = inventory["metrics"]
        print(
            "IC Support coverage PASS: "
            f"{metrics['exact_icpns']} exact ICPNs, "
            f"{metrics['base_devices']} base devices, "
            f"{metrics['evidence_backed_programming_profiles']} evidence-backed programming profiles, "
            f"{metrics['ic_support_bound_exact_icpns']} bound exact ICPNs, "
            f"{metrics['native_ppu_runtime_ready_exact_icpns']} Native PPU runtime-ready exact ICPNs"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoverageError as exc:
        print(f"IC Support coverage FAIL: {exc}")
        raise SystemExit(1)

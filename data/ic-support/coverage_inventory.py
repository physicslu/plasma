#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
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
ENRICHMENT_EVIDENCE_FILE = HERE / "enrichment-coverage" / "evidence-v1.json"
DEVICE_BASIC_ROOT = HERE / "device-basic"
DEVICE_BASIC_GLOB = "*-device-basic-v1.json"

ENRICHMENT_LEVELS = ("M0", "M1", "M2", "M3", "M4", "M5")
ENRICHMENT_DIMENSIONS = (
    "catalog_identity",
    "manufacturer_device_basic_profile",
    "ram",
    "operating_vdd",
    "io_supply",
    "vdda",
    "operating_temperature",
    "manufacturer_device_profile",
    "operating_electrical",
    "memory_map",
    "manufacturer_programming_profile",
    "programming_electrical",
    "programming_interfaces",
    "flash_geometry",
    "execution_ir",
    "generated_programmer",
    "independent_software_differential",
    "physical_hil",
)


class CoverageError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CoverageError(message)


def parse_pin_count(value: str, package: str = "") -> int:
    """Normalize manufacturer pin-count notation for the numeric IC-support inventory.

    Device Catalog intentionally preserves manufacturer ordering-table text.
    Most rows use a plain integer; some STM32 families use additive BGA notation
    such as 240+25. STM32H5 also uses slash notation when one ordering pin-code
    spans more than one physical package population. In that case the exact
    package is required to resolve the numeric count; unknown combinations fail
    closed instead of choosing an arbitrary alternative.
    """
    text = value.strip()
    package_text = package.strip()
    require(bool(text), "pin_count must not be empty")

    if "/" in text:
        alternatives = text.split("/")
        require(all(alternatives), f"unsupported pin_count notation: {value!r}")
        if len(set(alternatives)) == 1:
            text = alternatives[0]
        elif text == "64/68":
            by_package = {"LQFP": "64", "VFQFPN": "68"}
            require(
                package_text in by_package,
                f"cannot resolve pin_count {value!r} for package {package!r}",
            )
            text = by_package[package_text]
        elif text == "176/176+25":
            if package_text == "LQFP":
                text = "176"
            elif package_text.startswith("UFBGA 10x10"):
                text = "176+25"
            else:
                raise CoverageError(
                    f"cannot resolve pin_count {value!r} for package {package!r}"
                )
        elif text == "100/105":
            require(
                package_text == "LQFP",
                f"cannot resolve pin_count {value!r} for package {package!r}",
            )
            text = "100"
        else:
            raise CoverageError(f"unsupported pin_count notation: {value!r}")

    parts = text.split("+")
    require(
        all(part.isdigit() and part for part in parts),
        f"unsupported pin_count notation: {value!r}",
    )
    count = sum(int(part) for part in parts)
    require(count > 0, f"pin_count must be positive: {value!r}")
    return count

def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    require(isinstance(payload, dict), f"{path}: top-level JSON must be an object")
    return payload


def git_blob_sha_bytes(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def repo_file(relative_path: str) -> Path:
    path = (REPO_ROOT / relative_path).resolve()
    require(path.is_file(), f"coverage evidence path not found: {relative_path}")
    require(
        REPO_ROOT.resolve() in path.parents,
        f"coverage evidence path escapes repository: {relative_path}",
    )
    return path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_device_basic_coverage(
    production_rows: list[dict[str, str]],
) -> dict[str, dict[str, Any]]:
    required_fields = [
        "icpn", "base_device", "package", "pin_count", "flash",
        "ram", "operating_vdd", "io_supply", "vdda", "operating_temperature",
    ]
    catalog_owned_fields = [
        "icpn", "base_device", "package", "pin_count", "flash",
        "operating_temperature",
    ]
    catalog_by_icpn = {row["icpn"]: row for row in production_rows}
    paths = sorted(DEVICE_BASIC_ROOT.glob(DEVICE_BASIC_GLOB))
    require(paths, "no Manufacturer Device Basic Profile files found")

    result: dict[str, dict[str, Any]] = {}
    profile_ids: set[str] = set()
    family_keys: set[tuple[str, str]] = set()
    for path in paths:
        payload = load_json(path)
        require(
            payload.get("schema_version") == "1.0.0",
            f"{path}: device basic coverage schema drift",
        )
        profile_id = payload.get("profile_id")
        manufacturer = payload.get("manufacturer")
        family = payload.get("family")
        require(
            isinstance(profile_id, str) and profile_id.endswith("-device-basic-v1"),
            f"{path}: device basic profile identity drift",
        )
        require(profile_id not in profile_ids, f"duplicate device basic profile_id: {profile_id}")
        profile_ids.add(profile_id)
        require(
            payload.get("status") == "manufacturer_device_basic_available",
            f"{profile_id}: device basic profile status drift",
        )
        require(
            manufacturer == "STMicroelectronics",
            f"{profile_id}: device basic manufacturer drift",
        )
        require(
            isinstance(family, str) and family.startswith("STM32"),
            f"{profile_id}: device basic family drift",
        )
        family_key = (manufacturer, family)
        require(
            family_key not in family_keys,
            f"{profile_id}: duplicate Manufacturer Device Basic family profile",
        )
        family_keys.add(family_key)
        require(
            payload.get("fields") == required_fields,
            f"{profile_id}: device basic ten-field contract drift",
        )
        composition = payload.get("composition")
        require(
            isinstance(composition, dict),
            f"{profile_id}: device basic composition contract is required",
        )
        require(
            composition.get("catalog_owned_fields") == catalog_owned_fields,
            f"{profile_id}: device basic catalog-owned field contract drift",
        )
        require(
            composition.get("profile_owned_fields") == ["ram", "operating_vdd"],
            f"{profile_id}: device basic profile-owned field contract drift",
        )
        require(
            composition.get("nullable_unenriched_fields") == ["io_supply", "vdda"],
            f"{profile_id}: nullable field contract drift",
        )

        groups = payload.get("groups")
        bindings = payload.get("bindings")
        binding_count = payload.get("binding_count")
        require(
            isinstance(groups, dict) and groups,
            f"{profile_id}: device basic groups are required",
        )
        require(
            isinstance(bindings, dict) and bindings,
            f"{profile_id}: device basic bindings are required",
        )
        require(
            isinstance(binding_count, int) and binding_count == len(bindings),
            f"{profile_id}: binding_count drift",
        )

        expected = {
            row["icpn"]
            for row in production_rows
            if row["manufacturer"] == manufacturer and row["family"] == family
        }
        require(
            expected,
            f"{profile_id}: family has no Production exact ICPNs",
        )
        require(
            len(expected) == binding_count,
            f"{profile_id}: Production family count {len(expected)} != profile binding_count {binding_count}",
        )
        require(
            set(bindings) == expected,
            f"{profile_id}: device basic exact-ICPN applicability set drift",
        )

        for icpn, group_id in sorted(bindings.items()):
            require(icpn not in result, f"duplicate device basic exact ICPN: {icpn}")
            require(
                isinstance(group_id, str) and group_id in groups,
                f"{icpn}: dangling device basic group",
            )
            row = catalog_by_icpn[icpn]
            group = groups[group_id]
            require(
                isinstance(group, dict),
                f"{icpn}: device basic group must be an object",
            )
            require(
                group.get("series") == row["series"],
                f"{icpn}: device basic series mismatch",
            )
            require(
                group.get("flash_size") == row["flash_size"],
                f"{icpn}: device basic Flash mismatch",
            )
            require(
                isinstance(group.get("ram_size"), str)
                and group["ram_size"].endswith((" KiB", " MiB", " MB")),
                f"{icpn}: RAM missing",
            )
            vdd = group.get("operating_vdd_v")
            require(
                isinstance(vdd, dict)
                and isinstance(vdd.get("min"), (int, float))
                and isinstance(vdd.get("max"), (int, float))
                and vdd["min"] < vdd["max"],
                f"{icpn}: operating VDD missing",
            )
            optional_voltages: dict[str, dict[str, float] | None] = {}
            for optional_name, label in (
                ("io_supply_v", "I/O Supply"),
                ("vdda_v", "VDDA"),
            ):
                optional_voltage = group.get(optional_name)
                if optional_voltage is None:
                    optional_voltages[optional_name] = None
                else:
                    require(
                        isinstance(optional_voltage, dict)
                        and isinstance(optional_voltage.get("min"), (int, float))
                        and isinstance(optional_voltage.get("max"), (int, float))
                        and optional_voltage["min"] < optional_voltage["max"],
                        f"{icpn}: invalid {label}",
                    )
                    optional_voltages[optional_name] = copy.deepcopy(optional_voltage)
            for field in ("base_device", "package", "pin_count", "temperature_grade"):
                require(
                    isinstance(row.get(field), str) and row[field],
                    f"{icpn}: Production Catalog {field} missing",
                )
            evidence = group.get("evidence")
            require(isinstance(evidence, dict), f"{icpn}: device basic evidence missing")
            require(
                evidence.get("authority") == "STMicroelectronics official",
                f"{icpn}: device basic authority invalid",
            )
            surface = evidence.get("source_surface")
            source_url = evidence.get("selector_url")
            if surface == "st_product_selector":
                require(
                    isinstance(source_url, str)
                    and source_url.startswith("https://www.st.com/")
                    and "/products.html" in source_url
                    and evidence.get("evidence_strength")
                    == "official_product_selector_observation",
                    f"{icpn}: Product Selector evidence boundary invalid",
                )
            elif surface == "st_estore":
                require(
                    isinstance(source_url, str)
                    and source_url.startswith("https://estore.st.com/")
                    and evidence.get("evidence_strength") == "official_estore_observation",
                    f"{icpn}: eStore evidence boundary invalid",
                )
            else:
                raise CoverageError(f"{icpn}: unsupported device basic evidence surface")
            require(
                evidence.get("content_lock") is None,
                f"{icpn}: dynamic source must not fabricate a content lock",
            )
            result[icpn] = {
                "profile_id": profile_id,
                "profile_path": str(path.relative_to(REPO_ROOT)),
                "group_id": group_id,
                "ram_size": group["ram_size"],
                "operating_vdd_v": copy.deepcopy(vdd),
                "io_supply_v": optional_voltages["io_supply_v"],
                "vdda_v": optional_voltages["vdda_v"],
                "operating_temperature": row["temperature_grade"],
                "evidence": copy.deepcopy(evidence),
            }
    return result


def load_manufacturer_enrichment_evidence(
    production_icpns: set[str],
) -> dict[str, dict[str, Any]]:
    registry = load_json(ENRICHMENT_EVIDENCE_FILE)
    require(registry.get("schema_version") == "1.0.0", "unsupported manufacturer enrichment coverage schema")
    require(registry.get("coverage_id") == "manufacturer-enrichment-coverage-v1", "unexpected coverage_id")
    require(registry.get("status") == "research_coverage_only", "coverage registry must remain research-only")
    require(registry.get("runtime_authority") is False, "coverage registry must not grant runtime authority")
    require(registry.get("hardware_authority") is False, "coverage registry must not grant hardware authority")
    level_contract = registry.get("level_contract")
    require(isinstance(level_contract, dict), "coverage registry level_contract is required")
    require(set(level_contract) == set(ENRICHMENT_LEVELS), "coverage level contract drifted")

    raw_targets = registry.get("targets")
    require(isinstance(raw_targets, dict), "coverage registry targets must be an object")
    resolved: dict[str, dict[str, Any]] = {}

    for icpn, evidence in sorted(raw_targets.items()):
        require(icpn in production_icpns, f"{icpn}: enrichment target is not a Production ICPN")
        require(isinstance(evidence, dict), f"{icpn}: enrichment evidence must be an object")
        dimensions = {name: name == "catalog_identity" for name in ENRICHMENT_DIMENSIONS}
        evidence_paths: dict[str, str | None] = {}
        highest_level = "M0"

        baseline_ref = evidence.get("manufacturer_baseline")
        require(isinstance(baseline_ref, dict), f"{icpn}: manufacturer_baseline evidence is required")
        baseline_path = repo_file(str(baseline_ref.get("path", "")))
        lock_path = repo_file(str(baseline_ref.get("lock_path", "")))
        baseline_bytes = baseline_path.read_bytes()
        baseline = load_json(baseline_path)
        lock = load_json(lock_path)
        baseline_id = baseline_ref.get("baseline_id")
        require(baseline.get("baseline_id") == baseline_id, f"{icpn}: baseline identity mismatch")
        require(baseline.get("status") == "frozen_manufacturer_only", f"{icpn}: baseline is not manufacturer-only frozen")
        require(
            baseline.get("target", {}).get("icpn") == icpn,
            f"{icpn}: manufacturer baseline exact-target mismatch",
        )
        require(
            baseline.get("source_policy", {}).get("derivation_authority") == "manufacturer_official_only",
            f"{icpn}: manufacturer-only derivation authority is required",
        )
        baseline_digest = hashlib.sha256(baseline_bytes).hexdigest()
        require(lock.get("baseline_id") == baseline_id, f"{icpn}: baseline lock identity mismatch")
        require(
            lock.get("canonical_file_sha256") == baseline_digest,
            f"{icpn}: baseline lock digest drift",
        )
        evidence_paths["manufacturer_baseline"] = str(baseline_path.relative_to(REPO_ROOT))

        device_profile = baseline.get("device_profile")
        require(isinstance(device_profile, dict), f"{icpn}: device_profile is required")
        require(
            isinstance(device_profile.get("operating_electrical"), dict)
            and bool(device_profile["operating_electrical"])
            and isinstance(device_profile.get("memory_map"), dict)
            and bool(device_profile["memory_map"]),
            f"{icpn}: M1 requires operating electrical and memory map",
        )
        dimensions["manufacturer_device_profile"] = True
        dimensions["operating_electrical"] = True
        dimensions["memory_map"] = True
        highest_level = "M1"

        programming_profile = baseline.get("programming_profile")
        if programming_profile is not None:
            require(isinstance(programming_profile, dict), f"{icpn}: programming_profile must be an object")
            for key in ("interfaces", "programming_electrical", "flash_geometry"):
                require(
                    isinstance(programming_profile.get(key), dict) and programming_profile[key],
                    f"{icpn}: M2 requires programming_profile.{key}",
                )
            dimensions["manufacturer_programming_profile"] = True
            dimensions["programming_electrical"] = True
            dimensions["programming_interfaces"] = True
            dimensions["flash_geometry"] = True
            highest_level = "M2"

        execution = evidence.get("execution")
        if execution is not None:
            require(highest_level == "M2", f"{icpn}: M3 execution evidence requires complete M2")
            require(isinstance(execution, dict), f"{icpn}: execution evidence must be an object")
            execution_ir_path = repo_file(str(execution.get("execution_ir_path", "")))
            execution_ir = load_json(execution_ir_path)
            require(
                execution_ir.get("ir_id") == execution.get("execution_ir_id"),
                f"{icpn}: Execution IR identity mismatch",
            )
            ir_targets = execution_ir.get("targets")
            require(
                isinstance(ir_targets, list)
                and any(isinstance(item, dict) and item.get("icpn") == icpn for item in ir_targets),
                f"{icpn}: Execution IR does not bind the exact ICPN",
            )
            require(
                isinstance(baseline.get("program_model"), dict)
                and isinstance(baseline["program_model"].get("operations"), dict)
                and baseline["program_model"]["operations"],
                f"{icpn}: executable manufacturer program_model operations are required",
            )
            generator_path = repo_file(str(execution.get("generator_path", "")))
            behavior_test_path = repo_file(str(execution.get("behavior_test_path", "")))
            dimensions["execution_ir"] = True
            dimensions["generated_programmer"] = True
            highest_level = "M3"
            evidence_paths["execution_ir"] = str(execution_ir_path.relative_to(REPO_ROOT))
            evidence_paths["generator"] = str(generator_path.relative_to(REPO_ROOT))
            evidence_paths["generator_test"] = str(behavior_test_path.relative_to(REPO_ROOT))

        differential = evidence.get("independent_software_differential")
        if differential is not None:
            require(highest_level == "M3", f"{icpn}: M4 differential evidence requires complete M3")
            require(isinstance(differential, dict), f"{icpn}: independent software differential must be an object")
            comparison_path = repo_file(str(differential.get("openocd_comparison_path", "")))
            comparison = load_json(comparison_path)
            require(comparison.get("status") == "post_freeze_comparison", f"{icpn}: OpenOCD comparison is not post-freeze")
            require(comparison.get("target", {}).get("icpn") == icpn, f"{icpn}: OpenOCD comparison target mismatch")
            manufacturer_control = comparison.get("manufacturer_control")
            require(isinstance(manufacturer_control, dict), f"{icpn}: comparison manufacturer_control is required")
            require(manufacturer_control.get("baseline_id") == baseline_id, f"{icpn}: comparison baseline identity mismatch")
            require(
                manufacturer_control.get("baseline_sha256") == baseline_digest,
                f"{icpn}: comparison baseline digest mismatch",
            )
            conclusions = comparison.get("conclusions")
            require(
                isinstance(conclusions, dict)
                and conclusions.get("same_core_flash_programming_semantics") is True
                and conclusions.get("manufacturer_baseline_remains_immutable") is True
                and conclusions.get("hardware_runtime_ready") is False
                and conclusions.get("physical_programming_qualified") is False,
                f"{icpn}: independent comparison conclusions are incomplete",
            )
            real_binary_validator_path = repo_file(str(differential.get("real_binary_validator_path", "")))
            real_binary_test_path = repo_file(str(differential.get("real_binary_test_path", "")))
            dimensions["independent_software_differential"] = True
            highest_level = "M4"
            evidence_paths["openocd_comparison"] = str(comparison_path.relative_to(REPO_ROOT))
            evidence_paths["real_openocd_validator"] = str(real_binary_validator_path.relative_to(REPO_ROOT))
            evidence_paths["real_openocd_test"] = str(real_binary_test_path.relative_to(REPO_ROOT))

        physical_hil = evidence.get("physical_hil")
        evidence_paths["physical_hil"] = None
        if physical_hil is not None:
            require(highest_level == "M4", f"{icpn}: M5 HIL evidence requires complete M4")
            require(isinstance(physical_hil, dict), f"{icpn}: physical_hil must be null or an object")
            hil_path = str(physical_hil.get("evidence_path", ""))
            hil = load_json(repo_file(hil_path))
            require(hil.get("icpn") == icpn, f"{icpn}: HIL evidence target mismatch")
            require(
                hil.get("physical_programming_qualified") is True,
                f"{icpn}: M5 requires explicit physical_programming_qualified=true",
            )
            dimensions["physical_hil"] = True
            highest_level = "M5"
            evidence_paths["physical_hil"] = hil_path

        resolved[icpn] = {
            "highest_level": highest_level,
            "dimensions": dimensions,
            "missing_dimensions": [name for name in ENRICHMENT_DIMENSIONS if not dimensions[name]],
            "evidence": evidence_paths,
        }
    return resolved

def empty_manufacturer_enrichment() -> dict[str, Any]:
    dimensions = {name: name == "catalog_identity" for name in ENRICHMENT_DIMENSIONS}
    return {
        "highest_level": "M0",
        "dimensions": dimensions,
        "missing_dimensions": [name for name in ENRICHMENT_DIMENSIONS if not dimensions[name]],
        "evidence": {},
    }


def summarize_manufacturer_enrichment(rows: list[dict[str, Any]]) -> dict[str, Any]:
    highest = Counter(row["manufacturer_enrichment"]["highest_level"] for row in rows)
    at_least: dict[str, int] = {}
    for level_index, level in enumerate(ENRICHMENT_LEVELS):
        at_least[level] = sum(
            1
            for row in rows
            if ENRICHMENT_LEVELS.index(row["manufacturer_enrichment"]["highest_level"]) >= level_index
        )

    by_vendor: dict[str, Counter[str]] = defaultdict(Counter)
    by_family: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        level = row["manufacturer_enrichment"]["highest_level"]
        by_vendor[row["manufacturer"]][level] += 1
        by_family[row["family"]][level] += 1

    def normalized(counter: Counter[str]) -> dict[str, int]:
        return {level: int(counter.get(level, 0)) for level in ENRICHMENT_LEVELS}

    return {
        "highest_level_counts": {level: int(highest.get(level, 0)) for level in ENRICHMENT_LEVELS},
        "at_least_level_counts": at_least,
        "by_vendor_highest_level": {
            key: normalized(value) for key, value in sorted(by_vendor.items())
        },
        "by_family_highest_level": {
            key: normalized(value) for key, value in sorted(by_family.items())
        },
    }


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
    manufacturer_enrichment = load_manufacturer_enrichment_evidence(production_icpns)
    device_basic_coverage = load_device_basic_coverage(rows)

    base_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    family_counts: Counter[str] = Counter()
    openocd_mapped_count = 0
    openocd_unmapped_count = 0
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
        else:
            require(
                mapping_status == "no_mapping" and not openocd_target,
                f"{row['icpn']}: non-deterministic backend state must be explicit no_mapping",
            )
            openocd_unmapped_count += 1

        enrichment = copy.deepcopy(manufacturer_enrichment.get(row["icpn"], empty_manufacturer_enrichment()))
        basic = device_basic_coverage.get(row["icpn"])
        if basic is not None:
            enrichment["dimensions"]["manufacturer_device_basic_profile"] = True
            enrichment["dimensions"]["ram"] = True
            enrichment["dimensions"]["operating_vdd"] = True
            enrichment["dimensions"]["io_supply"] = basic["io_supply_v"] is not None
            enrichment["dimensions"]["vdda"] = basic["vdda_v"] is not None
            enrichment["dimensions"]["operating_temperature"] = True
            if enrichment["highest_level"] == "M0":
                enrichment["highest_level"] = "M1"
            enrichment["evidence"]["device_basic_profile"] = basic["profile_path"]
            enrichment["evidence"]["device_basic_group_id"] = basic["group_id"]
            enrichment["missing_dimensions"] = [
                name for name in ENRICHMENT_DIMENSIONS
                if not enrichment["dimensions"][name]
            ]

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
                # ADR-0002 L1 requires exact identity and programming-route
                # relevance, not fabricated physical package or memory data.
                # Only the source-pinned PIC32MX identity cohort may have
                # unknown optional dimensions; all other family invariants
                # retain their historical strict pin-count validation.
                "pin_count": (
                    None
                    if (manufacturer == "Microchip" and family == "PIC32MX"
                        and mapping_status == "no_mapping"
                        and not row["package"] and not row["pin_count"])
                    else parse_pin_count(row["pin_count"], row["package"])
                ),
                "flash_size": (
                    None
                    if (manufacturer == "Microchip" and family == "PIC32MX"
                        and not row["flash_size"])
                    else row["flash_size"]
                ),
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
                "manufacturer_enrichment": enrichment,
            }
        )

    base_devices = [
        summarize_base_device(manufacturer, base_device, members, bindings)
        for (manufacturer, base_device), members in sorted(base_rows.items())
    ]

    programming_profile_ids = sorted({binding["programming_profile_id"] for binding in bindings.values()})
    inventory_rows.sort(key=lambda item: (item["family"], item["base_device"], item["icpn"]))
    manufacturer_enrichment_summary = summarize_manufacturer_enrichment(inventory_rows)

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
            "openocd_unmapped_exact_icpns": openocd_unmapped_count,
            "ic_support_bound_exact_icpns": len(bindings),
            "unresolved_programming_profile_exact_icpns": len(rows) - len(bindings),
            "evidence_backed_programming_profiles": len(programming_profile_ids),
            "native_ppu_runtime_ready_exact_icpns": 0,
            "manufacturer_enrichment_m1_or_higher_exact_icpns": manufacturer_enrichment_summary["at_least_level_counts"]["M1"],
            "manufacturer_enrichment_m4_or_higher_exact_icpns": manufacturer_enrichment_summary["at_least_level_counts"]["M4"],
            "manufacturer_enrichment_m5_exact_icpns": manufacturer_enrichment_summary["at_least_level_counts"]["M5"],
        },
        "manufacturer_enrichment": manufacturer_enrichment_summary,
        "programming_profile_ids": programming_profile_ids,
        "base_devices": base_devices,
        "exact_icpns": inventory_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the derived production IC Support coverage inventory")
    parser.add_argument("--json", action="store_true", help="emit the complete deterministic inventory as JSON")
    parser.add_argument("--summary", action="store_true", help="emit only summary metrics as JSON")
    parser.add_argument(
        "--manufacturer-summary",
        action="store_true",
        help="emit Manufacturer Enrichment M0-M5 summary and vendor/family coverage",
    )
    parser.add_argument("--icpn", help="emit one exact ICPN coverage row")
    args = parser.parse_args()

    inventory = build_inventory()
    if args.icpn:
        matches = [row for row in inventory["exact_icpns"] if row["icpn"] == args.icpn]
        require(len(matches) == 1, f"exact Production ICPN not found: {args.icpn}")
        payload: Any = matches[0]
    elif args.manufacturer_summary:
        payload = inventory["manufacturer_enrichment"]
    elif args.summary:
        payload = inventory["metrics"]
    else:
        payload = inventory
    if args.json or args.summary or args.manufacturer_summary or args.icpn:
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

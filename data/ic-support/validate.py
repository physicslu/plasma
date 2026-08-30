#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PROFILE_ROOT = HERE / "profiles"
BINDING_FILE = HERE / "bindings" / "stm32f103c-pilot-v0.json"
SOURCE_FILE = HERE / "evidence" / "sources.json"
SCHEMA_FILE = HERE / "schema" / "ic-support-v0.schema.json"

EXPECTED_KINDS = {
    "programming",
    "memory_geometry",
    "package_hardware",
    "option",
    "security",
}
PROFILE_DIR_KIND = {
    "programming": "programming",
    "memory-geometry": "memory_geometry",
    "package-hardware": "package_hardware",
    "option": "option",
    "security": "security",
}
FLASH_SIZE_BYTES = {"64 KiB": 64 * 1024, "128 KiB": 128 * 1024}


class ValidationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValidationError(f"{path}: top-level JSON must be an object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def git_blob_sha(path: Path) -> str:
    require(path.is_file(), f"Git-blob-pinned evidence path not found: {path}")
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def source_ids() -> set[str]:
    payload = load_json(SOURCE_FILE)
    sources = payload.get("sources")
    require(isinstance(sources, list) and sources, "sources.json must contain non-empty sources")
    ids: list[str] = []
    for source in sources:
        require(isinstance(source, dict), "source entries must be objects")
        sid = source.get("source_id")
        require(isinstance(sid, str) and sid, "source_id must be a non-empty string")
        ids.append(sid)
        integrity = source.get("integrity")
        require(isinstance(integrity, dict), f"{sid}: integrity object is required")
        status = integrity.get("status")
        require(
            status in {"not_content_pinned", "git_blob_pinned"},
            f"{sid}: unsupported integrity status {status!r}",
        )
        if status == "git_blob_pinned":
            evidence_path = source.get("path")
            expected_sha = integrity.get("git_blob_sha")
            require(isinstance(evidence_path, str) and evidence_path, f"{sid}: path is required for git_blob_pinned evidence")
            require(
                isinstance(expected_sha, str) and len(expected_sha) == 40,
                f"{sid}: 40-character git_blob_sha is required",
            )
            actual_sha = git_blob_sha(REPO_ROOT / evidence_path)
            require(actual_sha == expected_sha, f"{sid}: pinned Git blob drift: expected {expected_sha}, got {actual_sha}")
    require(len(ids) == len(set(ids)), "source_id values must be unique")
    return set(ids)


def validate_evidence(payload: dict[str, Any], known_sources: set[str], owner: str) -> None:
    evidence = payload.get("evidence")
    require(isinstance(evidence, list) and evidence, f"{owner}: evidence must be non-empty")
    for item in evidence:
        require(isinstance(item, dict), f"{owner}: evidence entries must be objects")
        source_id = item.get("source_id")
        require(source_id in known_sources, f"{owner}: unknown evidence source {source_id!r}")


def load_profiles(known_sources: set[str]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for dirname, expected_kind in PROFILE_DIR_KIND.items():
        directory = PROFILE_ROOT / dirname
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            profile = load_json(path)
            pid = profile.get("profile_id")
            require(isinstance(pid, str) and pid, f"{path}: profile_id is required")
            require(pid not in profiles, f"duplicate profile_id: {pid}")
            kind = profile.get("kind")
            require(kind == expected_kind, f"{path}: kind {kind!r} does not match directory {dirname!r}")
            require(kind in EXPECTED_KINDS, f"{path}: unsupported profile kind {kind!r}")
            status = profile.get("status")
            require(isinstance(status, str) and status.startswith("pilot"), f"{path}: pilot status required")
            validate_evidence(profile, known_sources, pid)
            require(isinstance(profile.get("scope"), dict), f"{pid}: scope object is required")
            require(isinstance(profile.get("data"), dict), f"{pid}: data object is required")
            profiles[pid] = profile
    require(profiles, "no IC Support profiles found")
    return profiles


def load_catalog(path: Path) -> dict[str, dict[str, str]]:
    require(path.is_file(), f"catalog not found: {path}")
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            icpn = (row.get("icpn") or "").strip()
            if not icpn:
                continue
            require(icpn not in rows, f"duplicate ICPN in catalog: {icpn}")
            rows[icpn] = row
    return rows


def validate_geometry(profile: dict[str, Any], expected_flash_size: int, owner: str) -> None:
    data = profile["data"]
    start = int(data["main_flash_start"], 16)
    end = int(data["main_flash_end"], 16)
    size = data["main_flash_size_bytes"]
    page_size = data["page_size_bytes"]
    page_count = data["page_count"]
    require(size == expected_flash_size, f"{owner}: geometry size does not match Device Catalog")
    require(page_size > 0 and page_count > 0, f"{owner}: page geometry must be positive")
    require(size == page_size * page_count, f"{owner}: flash size != page_size * page_count")
    require(end == start + size - 1, f"{owner}: main_flash_end arithmetic mismatch")
    require(data["erase_granularity_bytes"] == page_size, f"{owner}: pilot erase granularity must equal page size")


def validate_programming(profile: dict[str, Any]) -> None:
    data = profile["data"]
    require(data["program_granularity_bytes"] == 2, "programming profile must use half-word granularity")
    require(data["unlock_keys"] == ["0x45670123", "0xCDEF89AB"], "unexpected STM32F1 unlock key sequence")
    require(data["write_erase_requires_hsi"] is True, "write/erase HSI requirement must be explicit")
    registers = data["registers"]
    require(registers["FLASH_KEYR"] == "0x40022004", "unexpected FLASH_KEYR")
    require(registers["FLASH_SR"] == "0x4002200C", "unexpected FLASH_SR")
    require(registers["FLASH_CR"] == "0x40022010", "unexpected FLASH_CR")


def validate_option(profile: dict[str, Any]) -> None:
    data = profile["data"]
    require(data["region_start"] == "0x1FFFF800", "unexpected option-byte base")
    require(data["region_size_bytes"] == 16, "unexpected option-byte region size")
    require(data["logical_option_bytes"] == 8, "unexpected logical option-byte count")
    require(data["encoding"] == "byte_plus_complement", "option-byte complement encoding must be explicit")
    require(data["reload"] == "system_reset", "option-byte reload requirement must be explicit")


def validate_security(profile: dict[str, Any]) -> None:
    data = profile["data"]
    unprotect = data["read_protection"]["disable_transition"]
    require(unprotect["destructive"] is True, "RDP disable transition must be marked destructive")
    require(unprotect["effect"] == "mass_erase_main_flash", "RDP disable effect must be explicit")
    require(unprotect["reset_required"] is True, "RDP disable reset requirement must be explicit")
    wrp = data["write_protection"]
    require(wrp["granularity_pages"] == 4, "medium-density WRP must cover four pages per bit")
    require(wrp["granularity_bytes"] == 4096, "medium-density WRP granularity must be 4096 bytes")


def main() -> int:
    schema = load_json(SCHEMA_FILE)
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "unexpected JSON Schema version")
    known_sources = source_ids()
    profiles = load_profiles(known_sources)
    bindings = load_json(BINDING_FILE)
    validate_evidence(bindings, known_sources, bindings.get("binding_set_id", "bindings"))
    require(bindings.get("status") == "pilot", "binding set must remain pilot")

    catalog_path = REPO_ROOT / bindings["catalog_source"]
    catalog = load_catalog(catalog_path)
    entries = bindings.get("bindings")
    require(isinstance(entries, list) and entries, "pilot bindings must be non-empty")

    seen: set[str] = set()
    resolved: dict[str, dict[str, Any]] = {}
    for entry in entries:
        require(isinstance(entry, dict), "binding entries must be objects")
        icpn = entry.get("icpn")
        require(isinstance(icpn, str) and icpn, "binding ICPN is required")
        require(icpn not in seen, f"duplicate IC Support binding: {icpn}")
        seen.add(icpn)
        require(icpn in catalog, f"{icpn}: exact ICPN not found in Device Catalog")
        row = catalog[icpn]
        expected = entry.get("expected_catalog")
        require(isinstance(expected, dict), f"{icpn}: expected_catalog is required")
        catalog_checks = {
            "manufacturer": "manufacturer",
            "base_device": "base_device",
            "package": "package",
            "pin_count": "pin_count",
            "flash_size": "flash_size",
            "openocd_target_config": "openocd_target_config",
        }
        for expected_key, catalog_key in catalog_checks.items():
            require(
                str(expected[expected_key]) == str(row[catalog_key]),
                f"{icpn}: Device Catalog {catalog_key} drift: expected {expected[expected_key]!r}, got {row[catalog_key]!r}",
            )

        refs = entry.get("profiles")
        require(isinstance(refs, dict), f"{icpn}: profiles object is required")
        require(set(refs) == EXPECTED_KINDS, f"{icpn}: profile kinds must be exactly {sorted(EXPECTED_KINDS)}")
        selected: dict[str, dict[str, Any]] = {}
        for kind, pid in refs.items():
            require(pid in profiles, f"{icpn}: dangling profile reference {pid!r}")
            profile = profiles[pid]
            require(profile["kind"] == kind, f"{icpn}: profile {pid} kind mismatch")
            selected[kind] = profile

        require(entry.get("revision_overrides") == [], f"{icpn}: pilot must not invent revision overrides")

        expected_flash_size = FLASH_SIZE_BYTES.get(row["flash_size"])
        require(expected_flash_size is not None, f"{icpn}: unsupported pilot flash size {row['flash_size']!r}")
        validate_geometry(selected["memory_geometry"], expected_flash_size, icpn)

        package_data = selected["package_hardware"]["data"]
        require(package_data["package"] == row["package"], f"{icpn}: package profile mismatch")
        require(str(package_data["pin_count"]) == row["pin_count"], f"{icpn}: pin-count profile mismatch")
        minimum_hw = package_data["pin_level_minimum_programming_hardware"]
        require(
            minimum_hw == {"status": "pending_evidence", "required_before_runtime_use": True},
            f"{icpn}: Phase A must remain fail-closed on minimum pin-level hardware",
        )
        resolved[icpn] = selected

    require(set(seen) == {"STM32F103C8T6", "STM32F103CBT6"}, "pilot target set drifted")

    c8 = resolved["STM32F103C8T6"]
    cb = resolved["STM32F103CBT6"]
    for shared_kind in {"programming", "package_hardware", "option", "security"}:
        require(c8[shared_kind]["profile_id"] == cb[shared_kind]["profile_id"], f"{shared_kind} should be shared")
    require(
        c8["memory_geometry"]["profile_id"] != cb["memory_geometry"]["profile_id"],
        "C8 and CB must not share memory geometry",
    )

    validate_programming(c8["programming"])
    validate_option(c8["option"])
    validate_security(c8["security"])
    print(f"IC Support validation PASS: {len(seen)} bindings, {len(profiles)} profiles")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"IC Support validation FAIL: {exc}")
        raise SystemExit(1)

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROFILE_ROOT = HERE / "profiles"
RULES_FILE = HERE / "semantic-rules-v0.json"

EXPECTED_RULE_IDS = {f"V{index:03d}" for index in range(1, 15)}


class SemanticValidationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise SemanticValidationError(f"{path}: top-level JSON must be an object")
    return value


def require_rule(condition: bool, rule_id: str, message: str) -> None:
    if not condition:
        raise SemanticValidationError(f"{rule_id}: {message}")


def parse_int(value: Any, owner: str) -> int:
    if isinstance(value, bool):
        raise SemanticValidationError(f"{owner}: Boolean is not an integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError as exc:
            raise SemanticValidationError(f"{owner}: invalid integer literal {value!r}") from exc
    raise SemanticValidationError(f"{owner}: expected integer or integer string, got {type(value).__name__}")


def validate_rule_registry(registry: dict[str, Any]) -> None:
    rules = registry.get("rules")
    require_rule(isinstance(rules, list), "REGISTRY", "rules must be a list")
    ids: list[str] = []
    for entry in rules:
        require_rule(isinstance(entry, dict), "REGISTRY", "rule entries must be objects")
        rule_id = entry.get("id")
        require_rule(isinstance(rule_id, str), "REGISTRY", "every rule requires a string id")
        ids.append(rule_id)
        require_rule(
            entry.get("status") in {"implemented", "partial", "requires_execution_ir", "requires_review_artifact_contract"},
            "REGISTRY",
            f"{rule_id}: unsupported status {entry.get('status')!r}",
        )
        require_rule(isinstance(entry.get("invariant"), str) and entry["invariant"], "REGISTRY", f"{rule_id}: invariant is required")
    require_rule(len(ids) == len(set(ids)), "REGISTRY", "rule ids must be unique")
    require_rule(set(ids) == EXPECTED_RULE_IDS, "REGISTRY", f"expected rule ids {sorted(EXPECTED_RULE_IDS)}, got {sorted(ids)}")


def load_profiles(profile_root: Path = PROFILE_ROOT) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(profile_root.glob("*/*.json")):
        profile = load_json(path)
        profile_id = profile.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id:
            raise SemanticValidationError(f"{path}: profile_id is required")
        if profile_id in profiles:
            raise SemanticValidationError(f"duplicate profile_id: {profile_id}")
        profiles[profile_id] = profile
    if not profiles:
        raise SemanticValidationError(f"no profiles found below {profile_root}")
    return profiles


def validate_numeric_masks(profile: dict[str, Any]) -> None:
    if profile.get("kind") != "programming":
        return
    owner = str(profile.get("profile_id", "programming-profile"))
    data = profile.get("data")
    require_rule(isinstance(data, dict), "V001", f"{owner}: data must be an object")
    control_bits = data.get("control_bits")
    symbols = data.get("operation_mode_bits")
    declared_mask = data.get("operation_mode_mask")
    require_rule(isinstance(control_bits, dict) and control_bits, "V001", f"{owner}: control_bits must be explicit")
    require_rule(isinstance(symbols, list) and symbols, "V001", f"{owner}: operation_mode_bits must be explicit")
    require_rule(declared_mask is not None, "V001", f"{owner}: operation_mode_mask must be explicit")

    calculated = 0
    seen: set[str] = set()
    for symbol in symbols:
        require_rule(isinstance(symbol, str) and symbol, "V001", f"{owner}: operation_mode_bits entries must be symbols")
        require_rule(symbol not in seen, "V001", f"{owner}: duplicate mask symbol {symbol!r}")
        seen.add(symbol)
        require_rule(symbol in control_bits, "V001", f"{owner}: mask references undefined symbol {symbol!r}")
        bit_value = parse_int(control_bits[symbol], f"{owner}.{symbol}")
        require_rule(bit_value > 0 and bit_value & (bit_value - 1) == 0, "V001", f"{owner}: {symbol} must be a single-bit mask")
        calculated |= bit_value

    observed = parse_int(declared_mask, f"{owner}.operation_mode_mask")
    require_rule(
        observed == calculated,
        "V001",
        f"{owner}: declared operation_mode_mask {observed:#x} != symbolic OR {calculated:#x}",
    )


def validate_geometry(profile: dict[str, Any]) -> None:
    if profile.get("kind") != "memory_geometry":
        return
    owner = str(profile.get("profile_id", "memory-geometry-profile"))
    data = profile.get("data")
    require_rule(isinstance(data, dict), "V008", f"{owner}: data must be an object")

    start = parse_int(data.get("main_flash_start"), f"{owner}.main_flash_start")
    end = parse_int(data.get("main_flash_end"), f"{owner}.main_flash_end")
    size = parse_int(data.get("main_flash_size_bytes"), f"{owner}.main_flash_size_bytes")
    page_size = parse_int(data.get("page_size_bytes"), f"{owner}.page_size_bytes")
    page_count = parse_int(data.get("page_count"), f"{owner}.page_count")
    erase = parse_int(data.get("erase_granularity_bytes"), f"{owner}.erase_granularity_bytes")

    require_rule(size > 0 and page_size > 0 and page_count > 0, "V008", f"{owner}: geometry values must be positive")
    require_rule(size % page_size == 0, "V008", f"{owner}: flash size must be divisible by page size")
    require_rule(size == page_size * page_count, "V008", f"{owner}: flash size != page_size * page_count")
    require_rule(end == start + size - 1, "V008", f"{owner}: flash end != start + size - 1")
    require_rule(erase == page_size, "V008", f"{owner}: pilot erase granularity must equal page size")


def validate_security_representations(profile: dict[str, Any]) -> None:
    if profile.get("kind") != "security":
        return
    owner = str(profile.get("profile_id", "security-profile"))
    data = profile.get("data")
    require_rule(isinstance(data, dict), "V007", f"{owner}: data must be an object")
    read_protection = data.get("read_protection")
    require_rule(isinstance(read_protection, dict), "V007", f"{owner}: read_protection must be an object")
    reps = read_protection.get("representations")
    require_rule(isinstance(reps, dict), "V007", f"{owner}: explicit read-protection representations are required")

    logical = parse_int(reps.get("logical_unprotected_byte"), f"{owner}.logical_unprotected_byte")
    complement = parse_int(reps.get("complement_byte"), f"{owner}.complement_byte")
    encoded = parse_int(reps.get("encoded_halfword"), f"{owner}.encoded_halfword")
    programming = parse_int(reps.get("programming_halfword"), f"{owner}.programming_halfword")

    require_rule(0 <= logical <= 0xFF, "V007", f"{owner}: logical byte must fit in 8 bits")
    require_rule(complement == ((~logical) & 0xFF), "V007", f"{owner}: complement byte is inconsistent with logical byte")
    require_rule(encoded == ((complement << 8) | logical), "V007", f"{owner}: encoded [nRDP:RDP] representation is inconsistent")
    require_rule(programming == logical, "V007", f"{owner}: programming halfword must be the zero-extended logical byte")

    legacy = read_protection.get("unprotected_key")
    if legacy is not None:
        require_rule(
            parse_int(legacy, f"{owner}.unprotected_key") == programming,
            "V007",
            f"{owner}: legacy unprotected_key alias must equal programming_halfword",
        )


def validate_program_address(
    geometry_data: dict[str, Any],
    address: int,
    width_bytes: int,
    alignment_bytes: int,
) -> None:
    """Validate one generated program access against exact target geometry.

    This is the implemented half of V009. A future execution IR will call the same
    invariant over every generated program/erase operation.
    """
    start = parse_int(geometry_data.get("main_flash_start"), "V009.main_flash_start")
    end = parse_int(geometry_data.get("main_flash_end"), "V009.main_flash_end")
    require_rule(width_bytes > 0, "V009", "access width must be positive")
    require_rule(alignment_bytes > 0, "V009", "alignment must be positive")
    require_rule(address % alignment_bytes == 0, "V009", f"address {address:#x} violates {alignment_bytes}-byte alignment")
    require_rule(address >= start, "V009", f"address {address:#x} is below Flash start {start:#x}")
    last = address + width_bytes - 1
    require_rule(last <= end, "V009", f"access ending at {last:#x} exceeds Flash end {end:#x}")


def validate_profile_set(profiles: dict[str, dict[str, Any]]) -> None:
    for profile in profiles.values():
        validate_numeric_masks(profile)
        validate_geometry(profile)
        validate_security_representations(profile)


def main() -> int:
    registry = load_json(RULES_FILE)
    validate_rule_registry(registry)
    profiles = load_profiles()
    validate_profile_set(profiles)
    implemented = [entry["id"] for entry in registry["rules"] if entry["status"] == "implemented"]
    partial = [entry["id"] for entry in registry["rules"] if entry["status"] == "partial"]
    print(
        "IC Support semantic validation PASS: "
        f"{len(profiles)} profiles; implemented={','.join(implemented)}; partial={','.join(partial)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SemanticValidationError as exc:
        print(f"IC Support semantic validation FAIL: {exc}")
        raise SystemExit(1)

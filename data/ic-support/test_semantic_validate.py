#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR_PATH = HERE / "semantic_validate.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("ic_support_semantic_validate", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load semantic_validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_failure(module, rule_id: str, fn, *args) -> None:
    try:
        fn(*args)
    except module.SemanticValidationError as exc:
        assert str(exc).startswith(f"{rule_id}:"), str(exc)
        return
    raise AssertionError(f"expected {rule_id} failure")


def profile_by_kind(profiles, kind: str):
    matches = [profile for profile in profiles.values() if profile.get("kind") == kind]
    if kind == "memory_geometry":
        return matches[0]
    assert len(matches) == 1, (kind, len(matches))
    return matches[0]


def test_current_profiles_pass(module) -> None:
    registry = module.load_json(module.RULES_FILE)
    module.validate_rule_registry(registry)
    profiles = module.load_profiles()
    module.validate_profile_set(profiles)


def test_v001_rejects_qwen_bad_mask(module) -> None:
    profiles = module.load_profiles()
    programming = copy.deepcopy(profile_by_kind(profiles, "programming"))
    programming["data"]["operation_mode_mask"] = "0x3B"
    expect_failure(module, "V001", module.validate_numeric_masks, programming)


def test_v007_rejects_representation_mix(module) -> None:
    profiles = module.load_profiles()
    security = copy.deepcopy(profile_by_kind(profiles, "security"))
    security["data"]["read_protection"]["representations"]["encoded_halfword"] = "0x00A5"
    expect_failure(module, "V007", module.validate_security_representations, security)


def test_v008_rejects_bad_geometry(module) -> None:
    profiles = module.load_profiles()
    geometry = copy.deepcopy(profile_by_kind(profiles, "memory_geometry"))
    geometry["data"]["page_count"] *= 2
    expect_failure(module, "V008", module.validate_geometry, geometry)


def test_v009_rejects_unaligned_and_out_of_range_access(module) -> None:
    profiles = module.load_profiles()
    geometries = [profile for profile in profiles.values() if profile.get("kind") == "memory_geometry"]
    c8 = next(profile for profile in geometries if profile["profile_id"] == "stm32f103c8-64k-v0")
    data = c8["data"]

    module.validate_program_address(data, 0x08000000, width_bytes=2, alignment_bytes=2)
    module.validate_program_address(data, 0x0800FFFE, width_bytes=2, alignment_bytes=2)
    expect_failure(module, "V009", module.validate_program_address, data, 0x08000001, 2, 2)
    expect_failure(module, "V009", module.validate_program_address, data, 0x08010000, 2, 2)
    expect_failure(module, "V009", module.validate_program_address, data, 0x0800FFFF, 2, 2)


def test_rule_registry_tracks_execution_ir_boundary(module) -> None:
    registry = module.load_json(module.RULES_FILE)
    by_id = {entry["id"]: entry for entry in registry["rules"]}
    for rule_id in {"V001", "V002", "V003", "V004", "V005", "V006", "V007", "V008", "V011", "V012", "V013"}:
        assert by_id[rule_id]["status"] == "implemented"
    assert by_id["V009"]["status"] == "partial"
    assert by_id["V010"]["status"] == "requires_execution_ir"
    assert by_id["V014"]["status"] == "requires_review_artifact_contract"


def main() -> int:
    module = load_validator_module()
    test_current_profiles_pass(module)
    test_v001_rejects_qwen_bad_mask(module)
    test_v007_rejects_representation_mix(module)
    test_v008_rejects_bad_geometry(module)
    test_v009_rejects_unaligned_and_out_of_range_access(module)
    test_rule_registry_tracks_execution_ir_boundary(module)
    print("IC Support semantic-validator tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

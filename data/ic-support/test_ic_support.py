#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPARE_PATH = HERE / "compare_benchmark.py"


def load_compare_module():
    spec = importlib.util.spec_from_file_location("ic_support_compare", COMPARE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load compare_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validator() -> None:
    subprocess.run([sys.executable, str(HERE / "validate.py")], check=True)


def test_socket_design_overlay_schema_contract() -> None:
    socket_root = HERE / "socket-design"
    schema = json.loads(
        (socket_root / "schema" / "socket-design-v1.schema.json").read_text(encoding="utf-8")
    )
    assert schema["$defs"]["binding"]["additionalProperties"] is False
    assert schema["$defs"]["binding"]["required"] == ["icpn", "profile_id"]

    profile = json.loads(
        (
            socket_root
            / "profiles"
            / "stm32f103c8t6-lqfp48-programming-hardware-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert profile["schema_version"] == schema["$defs"]["profile"]["properties"]["schema_version"]["const"]
    assert profile["kind"] == "package_hardware"
    assert profile["status"] == "pilot_socket_design_input_ready"
    assert profile["scope"]["exact_icpn"] == "STM32F103C8T6"
    assert profile["data"]["design_boundaries"]["hardware_runtime_ready"] is False
    assert profile["data"]["design_boundaries"]["physical_programming_qualified"] is False

    binding = json.loads(
        (socket_root / "bindings" / "stm32f103c8t6-v1.json").read_text(encoding="utf-8")
    )
    assert binding["status"] == "design_input_only"
    assert binding["bindings"] == [
        {
            "icpn": "STM32F103C8T6",
            "profile_id": "stm32f103c8t6-lqfp48-programming-hardware-v1",
        }
    ]


def test_socket_design_validator() -> None:
    subprocess.run([sys.executable, str(HERE / "socket-design" / "validate.py")], check=True)


def test_benchmark_positive_and_negative() -> None:
    module = load_compare_module()
    expected = module.load_json(module.GROUND_TRUTH)["expected"]
    observed = module.build_projection()
    assert module.compare(expected, observed) == []

    mutated = copy.deepcopy(observed)
    mutated["parts"]["STM32F103C8T6"]["flash_size_bytes"] = 131072
    errors = module.compare(expected, mutated)
    assert errors
    assert any("$.parts.STM32F103C8T6.flash_size_bytes" in error for error in errors)


def main() -> int:
    test_validator()
    test_socket_design_overlay_schema_contract()
    test_socket_design_validator()
    test_benchmark_positive_and_negative()
    print("IC Support tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

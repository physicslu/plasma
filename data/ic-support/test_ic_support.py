#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
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
    test_benchmark_positive_and_negative()
    print("IC Support tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

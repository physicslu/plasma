"""Host-only reference checks for the PLASMA 9x9 three-path experiment."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "scripts" / "experiments" / "plasma_three_path_nine_nine.py"
EXPECTED_SHA256 = "142d9b788a5902e98048690e75e9d91ac8e22334c592f7e2e5a93e8bc878bc5d"
EXPECTED_PRODUCTS = (
    (1, 2, 3, 4, 5, 6, 7, 8, 9),
    (2, 4, 6, 8, 10, 12, 14, 16, 18),
    (3, 6, 9, 12, 15, 18, 21, 24, 27),
    (4, 8, 12, 16, 20, 24, 28, 32, 36),
    (5, 10, 15, 20, 25, 30, 35, 40, 45),
    (6, 12, 18, 24, 30, 36, 42, 48, 54),
    (7, 14, 21, 28, 35, 42, 49, 56, 63),
    (8, 16, 24, 32, 40, 48, 56, 64, 72),
    (9, 18, 27, 36, 45, 54, 63, 72, 81),
)


def _run() -> bytes:
    result = subprocess.run(
        [sys.executable, str(PROGRAM)],
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert result.stderr == b""
    return result.stdout


def test_nine_nine_exact_81_products() -> None:
    lines = _run().decode("ascii").splitlines()
    assert len(lines) == 82
    assert lines[0] == "multiplicand,multiplier,product"
    for a in range(1, 10):
        for b in range(1, 10):
            index = 1 + (a - 1) * 9 + (b - 1)
            assert lines[index] == f"{a},{b},{EXPECTED_PRODUCTS[a - 1][b - 1]}"


def test_nine_nine_deterministic_sha256() -> None:
    first = _run()
    assert first == _run()
    assert first.endswith(b"9,9,81\n")
    assert hashlib.sha256(first).hexdigest() == EXPECTED_SHA256

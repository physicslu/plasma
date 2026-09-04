#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    required = [
        HERE / "schema" / "semantic-policy-v0.schema.json",
        HERE / "policies" / "st-ds5319-rev20-programming-v0.json",
        HERE / "fixtures" / "st-ds5319-rev20-outline-v0.json",
        HERE / "taxonomy-v0.json",
        HERE / "rules-v0.json",
    ]
    for path in required:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"IC semantic Evidence Pack FAIL: {path}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(value, dict):
            print(f"IC semantic Evidence Pack FAIL: {path}: JSON root must be object", file=sys.stderr)
            return 1

    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_semantic_pack.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print("IC semantic Evidence Pack PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

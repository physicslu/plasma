#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    schema_path = HERE / "schema" / "document-structure-v0.schema.json"
    normalization_path = HERE / "normalization-v0.json"
    fixture_path = HERE / "fixtures" / "synthetic-document-v0.json"

    for path in (schema_path, normalization_path, fixture_path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"IC document preprocessing FAIL: {path}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(value, dict):
            print(f"IC document preprocessing FAIL: {path}: JSON root must be object", file=sys.stderr)
            return 1

    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_preprocessing.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print("IC document preprocessing PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

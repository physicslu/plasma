#!/usr/bin/env python3
from __future__ import annotations

import unittest


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(
        start_dir="data/ic-support/evidence-pack",
        pattern="test_preprocessing.py",
        top_level_dir="data/ic-support/evidence-pack",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)

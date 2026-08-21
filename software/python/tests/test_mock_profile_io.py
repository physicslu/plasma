from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_profile import DEFAULT_MOCK_PROFILE
from plasma_core.mock_profile_io import load_mock_profile, write_mock_profile_atomic


class MockProfileIOTests(unittest.TestCase):
    def test_round_trip_preserves_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mock.yaml"
            profile = replace(DEFAULT_MOCK_PROFILE, revision=12, default_image_size_bytes=512 * 1024)
            write_mock_profile_atomic(path, profile)
            self.assertEqual(load_mock_profile(path), profile)

    def test_invalid_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mock.yaml"
            path.write_text(
                "profile_id: default\nrevision: 1\nenabled: true\ndefault_image_size_bytes: 65536\noperations: {}\n",
                encoding="utf-8",
            )
            with self.assertRaises(PlasmaError) as caught:
                load_mock_profile(path)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_atomic_write_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mock.yaml"
            write_mock_profile_atomic(path, DEFAULT_MOCK_PROFILE)
            self.assertTrue(path.is_file())
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

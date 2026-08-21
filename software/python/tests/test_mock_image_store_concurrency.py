from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from plasma_core.mock_image_store import SharedImageStore


class SharedImageStoreConcurrencyTests(unittest.TestCase):
    def test_concurrent_same_content_creation_leaves_one_valid_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            data = bytes(range(256)) * 4096
            with ThreadPoolExecutor(max_workers=8) as executor:
                refs = list(executor.map(lambda _: store.put(data), range(16)))
            self.assertEqual(len({ref.sha256 for ref in refs}), 1)
            self.assertEqual(len({ref.path for ref in refs}), 1)
            self.assertEqual(len(list(Path(directory).glob("*.bin"))), 1)
            resolved = store.resolve(refs[0].sha256, expected_size=len(data))
            self.assertEqual(resolved.size_bytes, len(data))


if __name__ == "__main__":
    unittest.main()

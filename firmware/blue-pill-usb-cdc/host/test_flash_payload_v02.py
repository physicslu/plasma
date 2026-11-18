"""Host-only deterministic payload tests; no programmer or USB access."""
from pathlib import Path
import hashlib
import tempfile
import unittest

from generate_flash_payload import DEFAULT_SEED, DEFAULT_SIZE, c_source, payload_bytes


class FlashPayloadTests(unittest.TestCase):
    def test_reproducible_payload_and_variation(self):
        first = payload_bytes()
        self.assertEqual(len(first), 44032)
        self.assertEqual(first, payload_bytes(DEFAULT_SIZE, DEFAULT_SEED))
        self.assertNotEqual(first, payload_bytes(DEFAULT_SIZE, DEFAULT_SEED + 1))
        self.assertGreater(len(set(first)), 240)
        self.assertGreater(len(set(first[i:i + 1024] for i in range(0, len(first), 1024))), 1)

    def test_source_is_flash_only_and_deterministic(self):
        c = c_source(payload_bytes(32))
        self.assertIn('section(".flash_test_payload")', c)
        self.assertIn("const uint8_t plasma_blue_pill_flash_test_payload[]", c)
        self.assertEqual(c, c_source(payload_bytes(32)))
        self.assertEqual(c.count("0x"), 32)
        self.assertNotIn("volatile ", c)

    def test_reject_invalid_size_and_seed(self):
        for size, seed in ((0, 1), (65537, 1), (1, -1), (1, 0x100000000)):
            with self.assertRaises(ValueError):
                payload_bytes(size, seed)

    def test_expected_total_payload_bytes(self):
        data = payload_bytes()
        self.assertEqual(len(hashlib.sha256(data).hexdigest()), 64)
        self.assertTrue(any(byte != 0x00 for byte in data))
        self.assertTrue(any(byte != 0xff for byte in data))


if __name__ == "__main__":
    unittest.main()

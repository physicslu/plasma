from __future__ import annotations

import hashlib
import random
import tempfile
import unittest
from pathlib import Path

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_flash import MockFlashState
from plasma_core.mock_image_store import SharedImageStore
from plasma_core.mock_profile import (
    DEFAULT_MOCK_PROFILE,
    MockOperationProfile,
    MockProfile,
    calculate_duration_ms,
    derive_job_seed,
    should_fail,
)


class MockProfileTests(unittest.TestCase):
    def test_default_profile_is_valid(self) -> None:
        DEFAULT_MOCK_PROFILE.validate()

    def test_image_size_must_follow_64_kib_steps(self) -> None:
        profile = MockProfile(
            profile_id="invalid-size",
            revision=1,
            enabled=True,
            default_image_size_bytes=65 * 1024,
            erase=DEFAULT_MOCK_PROFILE.erase,
            program=DEFAULT_MOCK_PROFILE.program,
            verify=DEFAULT_MOCK_PROFILE.verify,
            read=DEFAULT_MOCK_PROFILE.read,
        )
        with self.assertRaises(PlasmaError) as caught:
            profile.validate()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_failure_boundaries_are_exact(self) -> None:
        rng = random.Random(7)
        self.assertFalse(any(should_fail(rng, 0) for _ in range(100)))
        self.assertTrue(all(should_fail(rng, 1000) for _ in range(100)))

    def test_job_seed_is_deterministic_and_attempt_specific(self) -> None:
        fields = dict(
            batch_seed=1234,
            batch_id="batch-001",
            facility_id="facility-01",
            ppu_id="ppu-01",
            site_id=3,
            round_index=17,
            operation="program",
            profile_revision=4,
        )
        first = derive_job_seed(**fields, attempt=1)
        repeated = derive_job_seed(**fields, attempt=1)
        retry = derive_job_seed(**fields, attempt=2)
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, retry)

    def test_duration_uses_base_transfer_and_one_jitter_draw(self) -> None:
        operation = MockOperationProfile(
            error_rate_per_mille=0,
            base_time_ms=500,
            throughput_bytes_per_second=512 * 1024,
            jitter_ms=0,
        )
        self.assertEqual(
            calculate_duration_ms(profile=operation, data_size_bytes=256 * 1024, rng=random.Random(1)),
            1000,
        )


class SharedImageStoreTests(unittest.TestCase):
    def test_same_content_resolves_to_one_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            data = bytes(range(256)) * 1024
            first = store.put(data)
            second = store.put(data)
            self.assertEqual(first.sha256, second.sha256)
            self.assertEqual(first.path, second.path)
            self.assertEqual(len(list(Path(directory).glob("*.bin"))), 1)

    def test_content_address_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            data = b"plasma" * 1024
            ref = store.put(data)
            self.assertEqual(ref.sha256, hashlib.sha256(data).hexdigest())
            with store.open_mmap(ref.sha256) as mapped:
                self.assertEqual(mapped[: len(data)], data)

    def test_oversized_blob_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory, max_blob_bytes=8)
            with self.assertRaises(PlasmaError) as caught:
                store.put(b"123456789")
            self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)


class MockFlashStateTests(unittest.TestCase):
    def test_sixty_sites_reference_one_4_mib_blob_without_flash_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            image = bytes(range(256)) * (4 * 1024 * 1024 // 256)
            ref = store.put(image)
            sites = [MockFlashState(4 * 1024 * 1024) for _ in range(60)]
            for site in sites:
                site.program_shared(image_sha256=ref.sha256, image_size_bytes=ref.size_bytes)
            self.assertEqual(ref.size_bytes, 4 * 1024 * 1024)
            self.assertEqual(len(list(Path(directory).glob("*.bin"))), 1)
            self.assertTrue(all(site.backing_regions[0].image_sha256 == ref.sha256 for site in sites))
            self.assertTrue(all(not hasattr(site, "memory") for site in sites))

    def test_site_states_are_independent_over_one_shared_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            image = bytes(range(256)) * 16
            ref = store.put(image)
            first = MockFlashState(64 * 1024)
            second = MockFlashState(64 * 1024)
            first.program_shared(image_sha256=ref.sha256, image_size_bytes=ref.size_bytes)
            second.program_shared(image_sha256=ref.sha256, image_size_bytes=ref.size_bytes)
            first.overlay.write(0x120, b"\x00\x00")
            self.assertNotEqual(first.read(store, 0x120, 2), second.read(store, 0x120, 2))
            self.assertEqual(second.read(store, 0, len(image)), image)

    def test_full_erase_drops_backing_without_touching_other_site(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            image = b"\x55" * 4096
            ref = store.put(image)
            first = MockFlashState(64 * 1024)
            second = MockFlashState(64 * 1024)
            for site in (first, second):
                site.program_shared(image_sha256=ref.sha256, image_size_bytes=ref.size_bytes)
            first.erase()
            self.assertEqual(first.read(store, 0, 16), b"\xff" * 16)
            self.assertEqual(second.read(store, 0, 16), b"\x55" * 16)

    def test_partial_erase_and_reprogram_preserve_unrelated_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            base = store.put(b"abcdefgh")
            replacement = store.put(b"XY")
            state = MockFlashState(64)
            state.program_shared(image_sha256=base.sha256, image_size_bytes=base.size_bytes)
            state.erase(address=2, length=2)
            self.assertEqual(state.read(store, 0, 8), b"ab\xff\xffefgh")
            state.program_shared(image_sha256=replacement.sha256, image_size_bytes=2, address=2)
            self.assertEqual(state.read(store, 0, 8), b"abXYefgh")

    def test_verify_reports_first_absolute_mismatch_address(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SharedImageStore(directory)
            image = b"abcdef"
            ref = store.put(image)
            state = MockFlashState(64 * 1024)
            state.program_shared(image_sha256=ref.sha256, image_size_bytes=ref.size_bytes, address=10)
            state.overlay.write(12, b"X")
            self.assertEqual(state.verify(store, image, address=10), 12)


if __name__ == "__main__":
    unittest.main()

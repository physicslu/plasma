from __future__ import annotations

import unittest
from types import SimpleNamespace

from plasma_core.enums import Operation
from plasma_core.errors import PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.kl25_openocd_plan import KL25OpenOCDPlanCompiler, KL25_TARGET_CONFIG


def support():
    programming = SimpleNamespace(profile_id="nxp-kl25-ftfa-programming-v0", data={"program_granularity_bytes": 4})
    geometry = SimpleNamespace(profile_id="nxp-mkl25z128-128k-v0", data={"main_flash_start": "0x0", "main_flash_size_bytes": 131072, "main_flash_end": "0x1FFFF", "page_size_bytes": 1024, "page_count": 128, "erase_granularity_bytes": 1024, "program_granularity_bytes": 4})
    return SimpleNamespace(icpn="MKL25Z128VLK4", programming_profile=programming, memory_geometry_profile=geometry, openocd_target_config=KL25_TARGET_CONFIG)


def request(operation, *, image=b"", map_data=None):
    return JobRequest(job_id="job", site_id=1, target="MKL25Z128VLK4", operation=operation, image=image, map_data=map_data)


class KL25PlanTests(unittest.TestCase):
    def setUp(self):
        self.compiler = KL25OpenOCDPlanCompiler()
        self.support = support()

    def compile(self, req):
        return self.compiler.compile(self.support, req, configured_target_config=KL25_TARGET_CONFIG)

    def test_program_is_write_only_and_backend_may_pad_tail(self):
        plan = self.compile(request(Operation.PROGRAM, image=b"abc"))
        self.assertIn("flash write_image", " ".join(plan.commands))
        self.assertNotIn("erase", " ".join(plan.commands).lower())
        self.assertEqual(plan.program_granularity_bytes, 4)

    def test_flash_configuration_field_program_is_rejected(self):
        with self.assertRaisesRegex(PlasmaError, "Flash Configuration Field"):
            self.compile(request(Operation.PROGRAM, image=b"x" * 0x401))

    def test_program_rejects_entire_fcf_sector_even_when_not_touching_fcf_bytes(self):
        # OpenOCD kinetis_write() can synthesize FCF when any part of
        # the 1 KiB sector containing 0x400-0x40F is programmed.
        for address, size in (
            (0x400, 4),      # Direct FCF
            (0x410, 4),      # After FCF, still inside the same sector
            (0x7FC, 4),      # Last longword in FCF-containing sector
            (0x3FC, 8),      # Image straddles 0x400 boundary
            (0x3FC, 0x405),  # Image spans across the entire FCF sector
            (0, 0x401),      # Image from flash base overlaps FCF sector
        ):
            with self.subTest(address=hex(address), size=size):
                with self.assertRaisesRegex(PlasmaError, "Flash Configuration Field sector"):
                    self.compile(request(Operation.PROGRAM, image=b"x" * size,
                                         map_data={"address": address}))

    def test_program_boundary_0x400_is_exclusive_and_0x800_is_allowed(self):
        # A write ending just before the sector must be allowed; touching
        # even its first byte must not. The next sector starts at 0x800.
        first = self.compile(request(Operation.PROGRAM, image=b"x" * 0x400))
        self.assertTrue(any(cmd.startswith("flash write_image") for cmd in first.commands))
        second = self.compile(request(Operation.PROGRAM, image=b"abcd",
                                      map_data={"address": 0x800}))
        self.assertIn("flash write_image ${PLASMA_IMAGE_BIN} 0x00000800 bin", second.commands)

    def test_invalid_fcf_sector_geometry_fails_closed(self):
        lock = {
            "flash_configuration_field_start": "0x00000400",
            "flash_configuration_field_size_bytes": 16,
            "flash_configuration_field_sector_start": "0x00000800",
            "flash_configuration_field_sector_size_bytes": 1024,
        }
        with self.assertRaisesRegex(PlasmaError, "sector geometry is invalid"):
            self.compiler._reject_fcf_intersection(0, 4, lock)

    def test_aligned_program_segment_after_fcf_is_admitted(self):
        plan = self.compile(request(Operation.PROGRAM, image=b"abc", map_data={"address": 0x800}))
        self.assertIn("flash write_image ${PLASMA_IMAGE_BIN} 0x00000800 bin", plan.commands)

    def test_unaligned_program_segment_is_rejected(self):
        with self.assertRaisesRegex(PlasmaError, "alignment"):
            self.compile(request(Operation.PROGRAM, image=b"abc", map_data={"address": 0x801}))

    def test_program_segment_cannot_run_past_main_flash(self):
        with self.assertRaisesRegex(PlasmaError, "exceeds KL25 main Flash"):
            self.compile(request(Operation.PROGRAM, image=b"ab", map_data={"address": 0x1FFFF}))

    def test_exact_sector_erase_is_admitted(self):
        plan = self.compile(request(Operation.ERASE, map_data={"address": 0x800, "length": 1024}))
        self.assertIn("flash erase_address 0x00000800 0x00000400", plan.commands)
        self.assertNotIn(" pad ", " ".join(plan.commands))

    def test_flash_configuration_field_sector_erase_is_rejected(self):
        with self.assertRaisesRegex(PlasmaError, "Configuration Field sector"):
            self.compile(request(Operation.ERASE, map_data={"address": 0x400, "length": 1024}))

    def test_mass_erase_shape_is_rejected(self):
        with self.assertRaisesRegex(PlasmaError, "one exact aligned sector"):
            self.compile(request(Operation.ERASE, map_data={"address": 0, "length": 131072}))

if __name__ == "__main__":
    unittest.main()

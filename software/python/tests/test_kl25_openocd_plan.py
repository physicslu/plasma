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

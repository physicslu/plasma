from __future__ import annotations

import hashlib
import unittest

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_core.models import ExecutionImageRef, JobRequest
from plasma_interfaces.openocd import OpenOCDInterface
from plasma_interfaces.openocd_plan import IMAGE_ARTIFACT_TOKEN, OpenOCDPlanCompiler


TARGET_CFG = "target/stm32f1x.cfg"


class OpenOCDPlanCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        resolver = get_default_ic_support_resolver()
        self.c8 = resolver.require_exact("STM32F103C8T6")
        self.cb = resolver.require_exact("STM32F103CBT6")
        self.compiler = OpenOCDPlanCompiler()

    def compile(self, support, request: JobRequest):
        return self.compiler.compile(
            support,
            request,
            configured_target_config=TARGET_CFG,
        )

    def test_c8_and_cb_share_programming_profile_but_compile_different_erase_geometry(self) -> None:
        c8 = self.compile(
            self.c8,
            JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F103C8T6"),
        )
        cb = self.compile(
            self.cb,
            JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F103CBT6"),
        )

        self.assertEqual(c8.programming_profile_id, "stm32f1-medium-density-flash-v0")
        self.assertEqual(cb.programming_profile_id, c8.programming_profile_id)
        self.assertEqual(c8.memory_geometry_profile_id, "stm32f103c8-64k-v0")
        self.assertEqual(cb.memory_geometry_profile_id, "stm32f103cb-128k-v0")
        self.assertEqual(c8.main_flash_size_bytes, 64 * 1024)
        self.assertEqual(cb.main_flash_size_bytes, 128 * 1024)
        self.assertEqual(
            c8.commands,
            (
                "init",
                "reset init",
                "flash erase_address 0x08000000 0x00010000",
                "shutdown",
            ),
        )
        self.assertEqual(
            cb.commands,
            (
                "init",
                "reset init",
                "flash erase_address 0x08000000 0x00020000",
                "shutdown",
            ),
        )
        self.assertFalse(c8.to_dict()["hardware_runtime_ready"])
        self.assertTrue(c8.to_dict()["plan_only"])

    def test_program_plan_uses_profile_flash_base_and_content_bound_artifact(self) -> None:
        image = bytes(range(256)) * 4
        request = JobRequest(
            site_id=1,
            operation=Operation.PROGRAM,
            target="STM32F103C8T6",
            image=image,
        )
        plan = self.compile(self.c8, request)

        self.assertEqual(
            plan.commands,
            (
                "init",
                "reset init",
                f"flash write_image {IMAGE_ARTIFACT_TOKEN} 0x08000000 bin",
                "shutdown",
            ),
        )
        self.assertEqual(len(plan.artifacts), 1)
        self.assertEqual(plan.artifacts[0].size_bytes, len(image))
        self.assertEqual(plan.artifacts[0].sha256, hashlib.sha256(image).hexdigest())
        self.assertEqual(plan.artifacts[0].direction, "input")

    def test_verify_plan_is_separate_from_program_and_does_not_erase(self) -> None:
        plan = self.compile(
            self.c8,
            JobRequest(
                site_id=1,
                operation=Operation.VERIFY,
                target="STM32F103C8T6",
                image=b"verification-image",
            ),
        )
        self.assertEqual(
            plan.commands[2],
            f"flash verify_image {IMAGE_ARTIFACT_TOKEN} 0x08000000 bin",
        )
        self.assertFalse(any("erase" in command for command in plan.commands))

    def test_read_plan_defaults_to_first_256_bytes_of_resolved_main_flash(self) -> None:
        plan = self.compile(
            self.c8,
            JobRequest(site_id=1, operation=Operation.READ, target="STM32F103C8T6"),
        )
        self.assertEqual(
            plan.commands,
            (
                "init",
                "reset init",
                "dump_image ${PLASMA_READ_000_BIN} 0x08000000 0x00000100",
                "shutdown",
            ),
        )
        self.assertEqual(plan.artifacts[0].direction, "output")
        self.assertEqual(plan.artifacts[0].section_name, "main_flash_head")
        self.assertEqual(plan.artifacts[0].size_bytes, 256)

    def test_read_sections_must_stay_inside_resolved_main_flash(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            self.compile(
                self.c8,
                JobRequest(
                    site_id=1,
                    operation=Operation.READ,
                    target="STM32F103C8T6",
                    map_data={
                        "sections": [
                            {"name": "past-end", "address": 0x0800FF00, "length": 512}
                        ]
                    },
                ),
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertIn("exceeds resolved main Flash", caught.exception.message)

    def test_image_cannot_exceed_resolved_main_flash_capacity(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            self.compile(
                self.c8,
                JobRequest(
                    site_id=1,
                    operation=Operation.PROGRAM,
                    target="STM32F103C8T6",
                    image=b"x" * (64 * 1024 + 1),
                ),
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(caught.exception.context["main_flash_size_bytes"], 64 * 1024)

    def test_openocd_execution_image_reference_is_not_silently_treated_as_a_path(self) -> None:
        image_ref = ExecutionImageRef(
            scheme="local_mock_blob",
            sha256="0" * 64,
            size_bytes=1024,
        )
        with self.assertRaises(PlasmaError) as caught:
            self.compile(
                self.c8,
                JobRequest(
                    site_id=1,
                    operation=Operation.PROGRAM,
                    target="STM32F103C8T6",
                    image_ref=image_ref,
                ),
            )
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)

    def test_target_cfg_conflict_fails_closed_in_compiler(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            self.compiler.compile(
                self.c8,
                JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F103C8T6"),
                configured_target_config="target/stm32f4x.cfg",
            )
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
        self.assertEqual(caught.exception.context["expected_target_config"], TARGET_CFG)

    def test_resolved_support_and_job_target_must_match(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            self.compile(
                self.c8,
                JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F103CBT6"),
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)


class OpenOCDDirectExecutionGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_interface_erase_is_closed_until_plan_executor_exists(self) -> None:
        interface = OpenOCDInterface(
            {
                "interface_cfg": "interface/cmsis-dap.cfg",
                "target_cfg": TARGET_CFG,
            }
        )
        with self.assertRaises(PlasmaError) as caught:
            await interface.erase()
        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_NOT_CONFIGURED)
        self.assertIn("compiled-plan executor", caught.exception.message)


if __name__ == "__main__":
    unittest.main()

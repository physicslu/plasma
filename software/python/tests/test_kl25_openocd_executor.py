from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from plasma_core.enums import Operation
from plasma_core.models import JobRequest
from plasma_interfaces.kl25_openocd_plan import KL25OpenOCDPlanCompiler, KL25_TARGET_CONFIG
from plasma_interfaces.openocd_executor import OpenOCDPlanExecutor


FAKE_OPENOCD = r'''
import json
import os
import sys

args = sys.argv[1:]
commands = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "-c"]
with open(os.environ["FAKE_OPENOCD_LOG"], "w", encoding="utf-8") as stream:
    json.dump({"argv": args, "commands": commands}, stream)
print("fake-kl25-openocd")
'''


def support():
    return SimpleNamespace(
        icpn="MKL25Z128VLK4",
        programming_profile=SimpleNamespace(
            profile_id="nxp-kl25-ftfa-programming-v0",
            data={"program_granularity_bytes": 4},
        ),
        memory_geometry_profile=SimpleNamespace(
            profile_id="nxp-mkl25z128-128k-v0",
            data={
                "main_flash_start": "0x0",
                "main_flash_size_bytes": 131072,
                "main_flash_end": "0x1FFFF",
                "page_size_bytes": 1024,
                "page_count": 128,
                "erase_granularity_bytes": 1024,
                "program_granularity_bytes": 4,
            },
        ),
        openocd_target_config=KL25_TARGET_CONFIG,
    )


class KL25OpenOCDExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_program_plan_crosses_only_the_fake_process_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            script = root_path / "fake_openocd.py"
            script.write_text(textwrap.dedent(FAKE_OPENOCD), encoding="utf-8")
            log = root_path / "fake-openocd.json"
            request = JobRequest(
                job_id="kl25-software-executor",
                site_id=1,
                target="MKL25Z128VLK4",
                operation=Operation.PROGRAM,
                image=b"safe-segment",
                map_data={"address": 0x800},
            )
            resolved = support()
            compiler = KL25OpenOCDPlanCompiler()
            plan = compiler.compile(resolved, request, configured_target_config=KL25_TARGET_CONFIG)
            launched = []

            async def launcher(*arguments, **kwargs):
                launched.append(tuple(str(value) for value in arguments))
                return await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(script),
                    *arguments[1:],
                    **kwargs,
                )

            executor = OpenOCDPlanExecutor(
                {
                    "executable": "fake-openocd",
                    "interface_cfg": "interface/cmsis-dap.cfg",
                    "target_cfg": KL25_TARGET_CONFIG,
                    "work_dir": str(root_path),
                    "command_timeout_s": 2,
                },
                process_launcher=launcher,
                compiler=compiler,
            )
            with patch.dict(os.environ, {"FAKE_OPENOCD_LOG": str(log)}):
                result = await executor.execute(plan, resolved, request)

            record = json.loads(log.read_text(encoding="utf-8"))
            self.assertEqual(result.stdout.strip(), "fake-kl25-openocd")
            self.assertEqual(launched[0][0], "fake-openocd")
            self.assertIn("target/kl25.cfg", record["argv"])
            self.assertTrue(any(command.startswith("flash write_image ") for command in record["commands"]))
            self.assertFalse(any(" erase" in command for command in record["commands"]))


if __name__ == "__main__":
    unittest.main()

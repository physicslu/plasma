from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_core.models import JobRequest
from plasma_interfaces.openocd import OpenOCDInterface
from plasma_interfaces.openocd_executor import OpenOCDPlanExecutor
from plasma_interfaces.openocd_plan import OpenOCDPlanCompiler


TARGET_CFG = "target/stm32f1x.cfg"
INTERFACE_CFG = "interface/cmsis-dap.cfg"


FAKE_OPENOCD = r'''
import hashlib
import json
import os
import re
import sys
import time

args = sys.argv[1:]
commands = []
for index, value in enumerate(args[:-1]):
    if value == "-c":
        commands.append(args[index + 1])

record = {"argv": args, "commands": commands, "inputs": [], "outputs": [], "workspace": None}
path_pattern = re.compile(r"\{([^{}]+)\}")

for command in commands:
    match = path_pattern.search(command)
    if match is None:
        continue
    path = match.group(1)
    record["workspace"] = os.path.dirname(path)
    if command.startswith("flash write_image ") or command.startswith("flash verify_image "):
        payload = open(path, "rb").read()
        record["inputs"].append(
            {
                "path": path,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    elif command.startswith("dump_image "):
        parts = command.split()
        size = int(parts[-1], 0)
        record["outputs"].append({"path": path, "size": size})
        if os.environ.get("FAKE_OPENOCD_SKIP_OUTPUT") != "1":
            with open(path, "wb") as handle:
                if os.environ.get("FAKE_OPENOCD_WRONG_OUTPUT_SIZE") == "1":
                    handle.write(b"x")
                else:
                    handle.write(bytes(index % 251 for index in range(size)))

with open(os.environ["FAKE_OPENOCD_LOG"], "w", encoding="utf-8") as handle:
    json.dump(record, handle)

print(os.environ.get("FAKE_OPENOCD_STDOUT", "fake-openocd-stdout"))
print(os.environ.get("FAKE_OPENOCD_STDERR", "fake-openocd-stderr"), file=sys.stderr)

sleep_s = float(os.environ.get("FAKE_OPENOCD_SLEEP_S", "0"))
if sleep_s:
    time.sleep(sleep_s)
raise SystemExit(int(os.environ.get("FAKE_OPENOCD_EXIT_CODE", "0")))
'''


class OpenOCDExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        resolver = get_default_ic_support_resolver()
        self.support = resolver.require_exact("STM32F103C8T6")
        self.compiler = OpenOCDPlanCompiler()

    @staticmethod
    def _request(operation: Operation, *, image: bytes = b"", map_data=None) -> JobRequest:
        return JobRequest(
            site_id=1,
            operation=operation,
            target="STM32F103C8T6",
            image=image,
            map_data=map_data,
        )

    def _plan(self, request: JobRequest):
        return self.compiler.compile(
            self.support,
            request,
            configured_target_config=TARGET_CFG,
        )

    async def _execute(
        self,
        root: Path,
        request: JobRequest,
        *,
        plan=None,
        timeout_s: float = 2.0,
        env: dict[str, str] | None = None,
    ):
        script = root / "fake_openocd.py"
        script.write_text(textwrap.dedent(FAKE_OPENOCD), encoding="utf-8")
        log = root / "fake-openocd-log.json"
        launched: list[tuple[str, ...]] = []

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
                "interface_cfg": INTERFACE_CFG,
                "target_cfg": TARGET_CFG,
                "work_dir": str(root),
                "command_timeout_s": timeout_s,
            },
            process_launcher=launcher,
        )
        selected_plan = plan or self._plan(request)
        process_env = {"FAKE_OPENOCD_LOG": str(log), **(env or {})}
        with patch.dict(os.environ, process_env):
            result = await executor.execute(selected_plan, self.support, request)
        return result, launched, json.loads(log.read_text(encoding="utf-8"))

    async def test_program_materializes_sha_bound_image_and_cleans_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            image = bytes(range(256)) * 4
            request = self._request(Operation.PROGRAM, image=image)
            result, launched, record = await self._execute(root_path, request)

            self.assertEqual(result.stdout.strip(), "fake-openocd-stdout")
            self.assertEqual(result.stderr.strip(), "fake-openocd-stderr")
            self.assertEqual(result.read_sections, {})
            self.assertEqual(len(launched), 1)
            argv = launched[0]
            self.assertEqual(argv[0], "fake-openocd")
            self.assertEqual(argv[1:5], ("-f", INTERFACE_CFG, "-f", TARGET_CFG))
            self.assertIn("flash write_image", " ".join(record["commands"]))
            self.assertNotIn("${PLASMA_IMAGE_BIN}", " ".join(record["commands"]))
            self.assertEqual(record["inputs"][0]["size"], len(image))
            self.assertEqual(record["inputs"][0]["sha256"], hashlib.sha256(image).hexdigest())
            self.assertIsNotNone(record["workspace"])
            self.assertFalse(Path(record["workspace"]).exists())

    async def test_read_collects_exact_section_payload_then_cleans_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            request = self._request(
                Operation.READ,
                map_data={
                    "sections": [
                        {"name": "header", "address": 0x08000000, "length": 16},
                        {"name": "tail", "address": 0x08000040, "length": 8},
                    ]
                },
            )
            result, _launched, record = await self._execute(root_path, request)

            self.assertEqual(result.read_sections["header"], bytes(index % 251 for index in range(16)))
            self.assertEqual(result.read_sections["tail"], bytes(index % 251 for index in range(8)))
            self.assertEqual([item["size"] for item in record["outputs"]], [16, 8])
            self.assertFalse(Path(record["workspace"]).exists())

    async def test_executor_without_injected_launcher_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self._request(Operation.ERASE)
            plan = self._plan(request)
            executor = OpenOCDPlanExecutor(
                {
                    "interface_cfg": INTERFACE_CFG,
                    "target_cfg": TARGET_CFG,
                    "work_dir": root,
                }
            )
            with self.assertRaises(PlasmaError) as caught:
                await executor.execute(plan, self.support, request)
            self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_NOT_CONFIGURED)
            self.assertFalse(caught.exception.context["hardware_runtime_ready"])

    async def test_tampered_plan_is_rejected_before_process_launch(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            request = self._request(Operation.ERASE)
            canonical = self._plan(request)
            tampered = replace(canonical, main_flash_size_bytes=128 * 1024)
            launched = False

            async def launcher(*_arguments, **_kwargs):
                nonlocal launched
                launched = True
                raise AssertionError("tampered plan must not launch a process")

            executor = OpenOCDPlanExecutor(
                {
                    "interface_cfg": INTERFACE_CFG,
                    "target_cfg": TARGET_CFG,
                    "work_dir": str(root_path),
                },
                process_launcher=launcher,
            )
            with self.assertRaises(PlasmaError) as caught:
                await executor.execute(tampered, self.support, request)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
            self.assertFalse(launched)

    async def test_nonzero_exit_surfaces_bounded_process_evidence_and_cleans_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            request = self._request(Operation.PROGRAM, image=b"program-image")
            log = root_path / "fake-openocd-log.json"
            with self.assertRaises(PlasmaError) as caught:
                await self._execute(
                    root_path,
                    request,
                    env={
                        "FAKE_OPENOCD_EXIT_CODE": "7",
                        "FAKE_OPENOCD_STDOUT": "out-evidence",
                        "FAKE_OPENOCD_STDERR": "err-evidence",
                    },
                )
            self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_FAILURE)
            self.assertEqual(caught.exception.context["return_code"], 7)
            self.assertIn("out-evidence", caught.exception.context["stdout"])
            self.assertIn("err-evidence", caught.exception.context["stderr"])
            record = json.loads(log.read_text(encoding="utf-8"))
            self.assertFalse(Path(record["workspace"]).exists())

    async def test_timeout_kills_fake_process_and_cleans_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            request = self._request(Operation.PROGRAM, image=b"timeout-image")
            log = root_path / "fake-openocd-log.json"
            with self.assertRaises(PlasmaError) as caught:
                await self._execute(
                    root_path,
                    request,
                    timeout_s=0.05,
                    env={"FAKE_OPENOCD_SLEEP_S": "2"},
                )
            self.assertEqual(caught.exception.code, ErrorCode.OPERATION_TIMEOUT)
            record = json.loads(log.read_text(encoding="utf-8"))
            self.assertFalse(Path(record["workspace"]).exists())

    async def test_missing_read_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self._request(Operation.READ)
            with self.assertRaises(PlasmaError) as caught:
                await self._execute(
                    Path(root),
                    request,
                    env={"FAKE_OPENOCD_SKIP_OUTPUT": "1"},
                )
            self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_FAILURE)
            self.assertIn("expected read artifact", caught.exception.message)

    async def test_wrong_read_artifact_size_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            request = self._request(Operation.READ)
            with self.assertRaises(PlasmaError) as caught:
                await self._execute(
                    Path(root),
                    request,
                    env={"FAKE_OPENOCD_WRONG_OUTPUT_SIZE": "1"},
                )
            self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_FAILURE)
            self.assertEqual(caught.exception.context["actual_size_bytes"], 1)

    async def test_direct_interface_safe_shutdown_cannot_spawn_openocd(self) -> None:
        interface = OpenOCDInterface(
            {
                "executable": "definitely-not-a-real-openocd-binary",
                "interface_cfg": INTERFACE_CFG,
                "target_cfg": TARGET_CFG,
            }
        )
        await interface.safe_shutdown()


if __name__ == "__main__":
    unittest.main()

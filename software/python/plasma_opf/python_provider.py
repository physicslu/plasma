"""Host-independent Python Provider proof, not a PPU Package executor.

The Host supplies a trusted local script path. The OS subprocess primitive is
used directly; there is no Job router, package loader, lease or hardware grant.
This only observes process execution; Flash qualification belongs to a
separately verified Provider/Host evidence contract (not implemented here).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Literal

from .contract import OpfContractError, ProgrammingSelection

_PROCESS_OUTPUT_LIMIT = 4096


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    provider: str
    profile: str
    image_sha256: str
    process_status: Literal["SUCCEEDED", "FAILED", "TIMED_OUT"]
    exit_code: int | None
    stdout: str
    stderr: str
    # Intentionally no path from "process exit 0" to verified Flash PASS.
    programming_status: Literal["NOT_QUALIFIED"] = "NOT_QUALIFIED"


@dataclass(frozen=True, slots=True)
class PythonProvider:
    """Invoke an explicitly trusted Host-installed Python script.

    Not a secure sandbox for arbitrary untrusted code. A real Host must enforce
    its own OS permissions, isolation and hardware access policy.
    """

    name: str
    script: Path
    option_keys: frozenset[str] = field(default_factory=frozenset)

    async def flash_cycle(
        self, selection: ProgrammingSelection, image: bytes,
    ) -> ProcessObservation:
        if not isinstance(selection, ProgrammingSelection) or selection.provider != self.name:
            raise OpfContractError("PROVIDER_SELECTION_MISMATCH")
        if not isinstance(image, bytes) or not image:
            raise OpfContractError("PROVIDER_IMAGE_INVALID")
        if set(selection.options) - self.option_keys:
            raise OpfContractError("PROVIDER_OPTIONS_UNSUPPORTED")
        if type(selection.timeout_ms) is not int or selection.timeout_ms <= 0:
            raise OpfContractError("PROVIDER_TIMEOUT_INVALID")
        script = Path(self.script)
        if script.is_symlink() or not script.is_file():
            raise OpfContractError("PROVIDER_ENTRYPOINT_INVALID")
        # The caller explicitly selects the local entrypoint, never Job options.
        script = script.resolve(strict=True)
        options_json = json.dumps(selection.options, sort_keys=True, allow_nan=False)

        with tempfile.TemporaryDirectory(prefix="opf-python-") as directory:
            work = Path(directory)
            image_path = work / "image.bin"
            image_path.write_bytes(image)
            image_path.chmod(0o600)
            stdout_path, stderr_path = work / "stdout", work / "stderr"
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                try:
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, "-I", "-B", "-S", str(script),
                        "flash_cycle", str(image_path),
                        stdout=stdout, stderr=stderr, stdin=asyncio.subprocess.DEVNULL,
                        cwd=work, start_new_session=True,
                        env={
                            "PATH": os.defpath, "LANG": "C", "HOME": str(work),
                            "OPF_PROFILE": selection.profile,
                            "OPF_OPTIONS_JSON": options_json,
                        },
                    )
                except OSError as exc:
                    raise OpfContractError("PROVIDER_LAUNCH_FAILED") from exc
                status = "FAILED"
                try:
                    try:
                        await asyncio.wait_for(
                            process.wait(), timeout=selection.timeout_ms / 1000
                        )
                        status = "SUCCEEDED" if process.returncode == 0 else "FAILED"
                    except TimeoutError:
                        status = "TIMED_OUT"
                finally:
                    # Reap the process group on normal exit, timeout and cancellation.
                    # A successful parent must not leave background children running.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await asyncio.shield(process.wait())

            return ProcessObservation(
                provider=self.name,
                profile=selection.profile,
                image_sha256=hashlib.sha256(image).hexdigest(),
                process_status=status,
                exit_code=process.returncode,
                stdout=stdout_path.read_bytes()[:_PROCESS_OUTPUT_LIMIT].decode("utf-8", "replace"),
                stderr=stderr_path.read_bytes()[:_PROCESS_OUTPUT_LIMIT].decode("utf-8", "replace"),
            )

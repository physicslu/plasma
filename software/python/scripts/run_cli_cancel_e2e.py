#!/usr/bin/env python3
"""Real-process Ctrl+C cancellation test for the Plasma CLI."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run_cli(*arguments: str, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, "-m", "plasma_client.cli", *arguments],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        image_asset = Path(temporary) / "cancel-demo.bin"
        image_asset.write_bytes(bytes(range(256)) * 4)
        server = subprocess.Popen(
            [
                PYTHON,
                "-m",
                "plasma_server.server",
                "--config",
                "config/plasma.yaml",
            ],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            for _ in range(100):
                status = run_cli("status", timeout=2.0)
                if status.returncode == 0:
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("Server did not become ready")

            client = subprocess.Popen(
                [
                    PYTHON,
                    "-m",
                    "plasma_client.cli",
                    "program",
                    "--site",
                    "1",
                    "--bin",
                    os.fspath(image_asset),
                    "--timeout",
                    "15",
                    "--poll-interval",
                    "0.05",
                ],
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(2.0)
            client.send_signal(signal.SIGINT)
            stdout, stderr = client.communicate(timeout=10.0)
            if client.returncode != 0:
                raise AssertionError(
                    f"CLI exited with {client.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
                )
            result = json.loads(stdout)
            assert result["result"]["state"] == "cancelled", result
            assert "Cancellation requested" in stderr, stderr
            assert "PROGRAM" in stderr, stderr
            assert "ERASE" not in stderr, stderr
            assert "VERIFY" not in stderr, stderr

            follow_up = run_cli(
                "erase",
                "--site",
                "1",
                "--timeout",
                "5",
                "--no-progress",
                timeout=8.0,
            )
            if follow_up.returncode != 0:
                raise AssertionError(follow_up.stderr)
            assert json.loads(follow_up.stdout)["result"]["state"] == "success"
            print("CLI Ctrl+C E2E: remote cancel and Site recovery passed")
            return 0
        finally:
            server.terminate()
            try:
                server.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5.0)


if __name__ == "__main__":
    raise SystemExit(main())

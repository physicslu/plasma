"""S1-B: a real Linux Python fake Provider without any PPU deployment stack.

The child deliberately claims Flash PASS. OPF records only process completion;
without independent Erase/Program/Verify/Readback evidence it cannot qualify Flash.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from plasma_opf import (
    OPF_PROGRAMMING_SCHEMA, OpfContractError, TimeoutPolicy,
    parse_programming_selection, PythonProvider,
)

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux subprocess/process-group Host-only acceptance"
)

IMAGE = b"\x31\x02\x59\xff"
POLICY = TimeoutPolicy(default_timeout_ms=1500, maximum_timeout_ms=5000)


def selected(*, provider="host-fake", timeout_ms=None, options=None):
    request = {
        "schema": OPF_PROGRAMMING_SCHEMA,
        "provider": provider,
        "profile": "synthetic-target",
        "options": {} if options is None else options,
    }
    if timeout_ms is not None:
        request["timeout_ms"] = timeout_ms
    return parse_programming_selection(request, policy=POLICY)


def script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "provider.py"
    path.write_text(body, encoding="utf-8")
    return path


def run(provider: PythonProvider, *, selection=None, image=IMAGE):
    return asyncio.run(provider.flash_cycle(selection or selected(), image))


def test_standalone_import_does_not_load_any_ppu_bundle_openocd_or_hardware_modules():
    source = str(Path(__file__).resolve().parents[1])
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from plasma_opf import PythonProvider, parse_programming_selection
for prefix in ('plasma_server', 'plasma_interfaces', 'plasma_core',
               'ppu_', 'plasma_web', 'plasma_manager'):
    assert not any(key == prefix or key.startswith(prefix + '.') for key in sys.modules), prefix
print('STANDALONE_OPF_IMPORT_PASS')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, source], capture_output=True,
        text=True, check=True, timeout=8,
    )
    assert result.stdout.strip() == "STANDALONE_OPF_IMPORT_PASS"


def test_real_child_exits_zero_and_claims_flash_pass_but_result_is_not_qualified(tmp_path):
    fake = script(tmp_path, """
import hashlib
import json
import os
from pathlib import Path
import sys
assert sys.argv[1] == 'flash_cycle'
raw = Path(sys.argv[2]).read_bytes()
assert raw == bytes.fromhex('310259ff')
assert os.environ['OPF_PROFILE'] == 'synthetic-target'
assert json.loads(os.environ['OPF_OPTIONS_JSON']) == {'mode': 'fake'}
print('FAKE_SAYS_FLASH_PASS', flush=True)
""")
    observation = run(
        PythonProvider("host-fake", fake, frozenset({"mode"})),
        selection=selected(options={"mode": "fake"}),
    )
    assert observation.provider == "host-fake"
    assert observation.profile == "synthetic-target"
    assert observation.image_sha256 == hashlib.sha256(IMAGE).hexdigest()
    assert observation.process_status == "SUCCEEDED"
    assert observation.exit_code == 0
    assert "FAKE_SAYS_FLASH_PASS" in observation.stdout
    assert observation.programming_status == "NOT_QUALIFIED"
    assert not hasattr(observation, "flash_pass") and not hasattr(observation, "safe_off_verified")


def test_nonzero_exit_is_process_failure_not_flash_failure_proof(tmp_path):
    fake = script(tmp_path, "import sys; print('FLASH_PASS'); sys.exit(7)\n")
    observation = run(PythonProvider("host-fake", fake))
    assert observation.process_status == "FAILED"
    assert observation.exit_code == 7
    assert observation.programming_status == "NOT_QUALIFIED"


@pytest.mark.parametrize(("selection", "image", "expected"), [
    (selected(provider="wrong"), IMAGE, "PROVIDER_SELECTION_MISMATCH"),
    (selected(options={"arbitrary_device": "/dev/mem"}), IMAGE, "PROVIDER_OPTIONS_UNSUPPORTED"),
    (selected(), b"", "PROVIDER_IMAGE_INVALID"),
])
def test_untrusted_selection_or_options_cannot_launch(tmp_path, selection, image, expected):
    marker = tmp_path / "executed"
    fake = script(tmp_path, f"from pathlib import Path; Path({str(marker)!r}).touch()\n")
    with pytest.raises(OpfContractError, match=expected):
        run(PythonProvider("host-fake", fake), selection=selection, image=image)
    assert not marker.exists()


def test_missing_script_fails_closed(tmp_path):
    with pytest.raises(OpfContractError, match="PROVIDER_ENTRYPOINT_INVALID"):
        run(PythonProvider("host-fake", tmp_path / "missing.py"))


def test_child_timeout_is_reaped_and_not_flash_pass(tmp_path):
    fake = script(tmp_path, "import time; time.sleep(10)\n")
    observation = run(PythonProvider("host-fake", fake), selection=selected(timeout_ms=200))
    assert observation.process_status == "TIMED_OUT"
    assert observation.exit_code != 0
    assert observation.programming_status == "NOT_QUALIFIED"


def test_cancel_kills_child_process_group(tmp_path):
    pidfile = tmp_path / "pid"
    fake = script(tmp_path, f"""
from pathlib import Path
import os
import time
Path({str(pidfile)!r}).write_text(str(os.getpid()))
time.sleep(30)
""")
    async def scenario():
        task = asyncio.create_task(
            PythonProvider("host-fake", fake).flash_cycle(selected(), IMAGE)
        )
        for _ in range(100):
            if pidfile.exists():
                break
            await asyncio.sleep(0.02)
        assert pidfile.exists(), "fake script never started"
        pid = int(pidfile.read_text())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    asyncio.run(scenario())


def test_output_observation_is_bounded(tmp_path):
    fake = script(tmp_path, "print('x' * 15000)\n")
    observation = run(PythonProvider("host-fake", fake))
    assert observation.process_status == "SUCCEEDED"
    assert len(observation.stdout) <= 4096
    assert observation.programming_status == "NOT_QUALIFIED"

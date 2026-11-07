"""Host-only REST -> Runtime Active Set reference -> C3 fake OpenOCD.

This deliberately injects a bounded resolver to test the transport/Job lease.
The real B3 Active Set resolver has its own filesystem SHA/negative tests.
No SWPC, Z2, PL, DUT, network device or real OpenOCD is accessed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from .test_c3_rest_flash_cycle import Stack, TERMINAL, run, short_tmp

PROVIDER = "openocd-reference"
PROFILE = "stm32f103-c8"
ASSET_ID = "hostonly-cdc-v01"
IMAGE = b"TEST-ONLY-IMAGE-NOT-A-REAL-FIRMWARE"


def body(stack, *, sha=None):
    return {
        "site_id": 2, "operation": "flash_cycle",
        "target": "STM32F103C8T6",
        "provider": PROVIDER, "profile": PROFILE,
        "asset_set_sha256": stack.opf["asset_set_sha256"] if sha is None else sha,
        "asset_package_id": ASSET_ID,
        "bundle_asset_sha256": hashlib.sha256(IMAGE).hexdigest(),
    }


async def terminal(stack, job_id):
    for _ in range(500):
        _, result = await stack.api("GET", "/api/status?job=" + job_id)
        job = result["job"]
        if job["state"] in TERMINAL:
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("Host-only C3 Job not terminal")


def test_bundle_reference_reaches_existing_c3_with_one_flash_and_readback():
    async def scenario():
        with short_tmp() as folder:
            async with Stack(Path(folder), in_process=True) as stack:
                calls = []

                def resolve(**selection):
                    calls.append(dict(selection))
                    assert selection == {
                        "asset_set_sha256": stack.opf["asset_set_sha256"],
                        "asset_package_id": ASSET_ID,
                        "profile_package_id": PROFILE,
                        "asset_sha256": hashlib.sha256(IMAGE).hexdigest(),
                    }
                    return {
                        "image": IMAGE,
                        "image_name": "v01.bin",
                        "image_sha256": selection["asset_sha256"],
                        "asset_set_sha256": selection["asset_set_sha256"],
                        "asset_package_id": ASSET_ID,
                        "profile_package_id": PROFILE,
                    }

                stack.manager._bundle_firmware_resolver = resolve
                status, received = await stack.api("POST", "/api/jobs", body(stack))
                assert status == 202, received
                job_id = received["job"]["job_id"]
                job = await terminal(stack, job_id)
                assert job["state"] == "success", json.dumps(job)
                cycle = job["result"]["details"]["flash_cycle"]
                assert cycle["result"] == "PASS" and cycle["safe_off"] is True
                assert cycle["readback_sha256"] == hashlib.sha256(IMAGE).hexdigest()
                assert cycle["bytes_verified"] == len(IMAGE)
                assert bytes(stack.sim.memory[:len(IMAGE)]) == IMAGE
                assert len(stack.sim.argvs) == 1
                assert len(calls) == 1
    run(scenario())


def test_bundle_reference_wrong_active_set_never_opens_c3():
    async def scenario():
        with short_tmp() as folder:
            async with Stack(Path(folder), in_process=True) as stack:
                calls = []
                stack.manager._bundle_firmware_resolver = lambda **kw: calls.append(kw)
                status, received = await stack.api(
                    "POST", "/api/jobs", body(stack, sha="b" * 64))
                assert status in (400, 422), received
                assert "ACTIVE_SET_MISMATCH" in json.dumps(received)
                assert calls == []
                assert stack.sim.argvs == []
    run(scenario())

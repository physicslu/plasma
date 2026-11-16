"""Host-only: retired unbound Bundle references cannot open a C-3 session."""
from pathlib import Path
from .test_c3_rest_flash_cycle import Stack, run, short_tmp


def test_retired_bundle_reference_is_refused_before_execution():
    async def scenario():
        with short_tmp() as folder:
            async with Stack(Path(folder), in_process=True) as stack:
                status, reply = await stack.api("POST", "/api/jobs", {
                    "site_id": 2, "operation": "flash_cycle", "target": "STM32F103C8T6",
                    "asset_set_sha256": stack.opf["asset_set_sha256"],
                    "asset_package_id": "firmware", "bundle_asset_sha256": "a" * 64})
                assert status != 202, reply
                assert not stack.sim.argvs and not stack.core._sessions
    run(scenario())

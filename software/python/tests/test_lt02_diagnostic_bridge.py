"""LT02-06 phase 1: host-only real Protocol-v3.3 PL diagnostic bridge tests.

The register fixture is synthetic: these tests DO NOT load FPGA, access /dev/mem,
qualify a hardware source, or authorize browser UI PL enablement.
"""
from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.diagnostics import PL_LOOPBACK_ENDPOINT, crc32_hex
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.mmio_loop_test import (
    ABI_VERSION, CAPABILITIES, CAPACITY, MAGIC, REG_ABI, REG_CAPABILITIES,
    REG_CAPACITY, REG_MAGIC, REG_READS, REG_STATUS, REG_WRITES,
    WINDOW_START, LoopTestDriver,
)
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager
from plasma_web.diagnostics import execute_ps_loopback
from tests.helpers import make_config

BASE = 0x40004000


class WordRegisterFixture:
    """Fake AXI word port, only for host contract tests."""

    def __init__(self) -> None:
        self.registers = {
            REG_MAGIC: MAGIC, REG_ABI: ABI_VERSION,
            REG_CAPABILITIES: CAPABILITIES, REG_CAPACITY: CAPACITY,
            REG_STATUS: 1, REG_READS: 0, REG_WRITES: 0,
        }
        self.data: dict[int, int] = {}
        self.fail_on_write = False
        self.data_writes = 0

    def read32(self, address: int) -> int:
        off = address - BASE
        if WINDOW_START <= off < WINDOW_START + CAPACITY:
            self.registers[REG_READS] += 1
            return self.data.get(off, 0)
        return self.registers[off]

    def write32(self, address: int, value: int) -> None:
        off = address - BASE
        if not WINDOW_START <= off < WINDOW_START + CAPACITY:
            raise AssertionError("unexpected word write")
        if self.fail_on_write:
            raise OSError("synthetic data MMIO fault")
        self.data[off] = value
        self.data_writes += 1
        self.registers[REG_WRITES] += 1


class LT02RealTCPBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server: PlasmaServer | None = None
        self.port = WordRegisterFixture()

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def start_server(self, *, enable_pl: bool) -> PlasmaClient:
        config = make_config(self.root, enabled_sites=1)
        self.server = PlasmaServer(
            config, SiteManager(config),
            lt02_driver=LoopTestDriver(self.port, base=BASE) if enable_pl else None,
        )
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=3.0)

    @staticmethod
    def body(payload: bytes, *, endpoint: str = "pl") -> dict:
        return {
            "endpoint": endpoint,
            "test_id": "lt02-bridge-tcp",
            "sequence": 11,
            "pattern": "increment",
            "seed": "",
            "payload_length": len(payload),
            "payload_base64": base64.b64encode(payload).decode("ascii"),
            "tx_crc32": crc32_hex(payload),
            "timeout_ms": 3000,
        }

    async def test_default_does_not_activate_pl_or_fake_hardware(self) -> None:
        client = await self.start_server(enable_pl=False)
        with self.assertRaises(PlasmaError) as caught:
            await client.diagnostic_loopback(
                b"not-real-pl", test_id="blocked", sequence=0, endpoint="pl"
            )
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)
        self.assertEqual(self.port.data_writes, 0)
        meta, echoed = await client.diagnostic_loopback(
            b"PS unaffected", test_id="ps-still-working", sequence=1
        )
        self.assertEqual(meta["source"], "ps")
        self.assertEqual(echoed, b"PS unaffected")

    async def test_requires_a_real_production_driver_instance(self) -> None:
        config = make_config(self.root, enabled_sites=1)
        with self.assertRaises(TypeError):
            PlasmaServer(config, SiteManager(config), lt02_driver=lambda p: p)  # type: ignore[arg-type]

    async def test_injected_production_driver_roundtrip_over_real_tcp_and_gateway(self) -> None:
        client = await self.start_server(enable_pl=True)
        assert self.server is not None
        self.server.manager.enqueue = lambda *args, **kwargs: (1 / 0)  # type: ignore[method-assign]
        for size in (1, 4, 5, 1023, 1024, 1025, 2048, 2049, 4097, 8193):
            data = bytes(i % 256 for i in range(size))
            result = await execute_ps_loopback(
                self.body(data), lambda: client,
            )
            detail = result["loopback"]
            self.assertTrue(result["ok"])
            self.assertEqual(detail["endpoint"], PL_LOOPBACK_ENDPOINT)
            self.assertEqual(detail["source"], PL_LOOPBACK_ENDPOINT)
            self.assertEqual(detail["tx_crc32"], crc32_hex(data))
            self.assertEqual(detail["rx_crc32"], crc32_hex(data))
            self.assertEqual(base64.b64decode(result["payload_base64"]), data)
            words = sum(
                (min(2048, size - origin) + 3) // 4
                for origin in range(0, size, 2048)
            )
            self.assertEqual(detail["lt02"]["site_id"], 1)
            self.assertEqual(detail["lt02"]["data_word_writes"], words)
            self.assertEqual(detail["lt02"]["data_word_reads"], words)
            self.assertEqual(detail["lt02"]["chunks"], (size + 2047) // 2048)
            self.assertGreaterEqual(detail["lt02"]["fpga_driver_elapsed_ns"], 0)
        self.assertGreater(self.port.data_writes, 0)

    async def test_pl_size_cap_applied_before_driver_access(self) -> None:
        client = await self.start_server(enable_pl=True)
        data = b"x" * (1024 * 1024 + 1)
        with self.assertRaises(PlasmaError) as caught:
            await execute_ps_loopback(self.body(data), lambda: client)
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE)
        self.assertEqual(self.port.data_writes, 0)

    async def test_fault_quarantines_pl_but_does_not_break_ps(self) -> None:
        client = await self.start_server(enable_pl=True)
        self.port.fail_on_write = True
        with self.assertRaises(PlasmaError) as caught:
            await client.diagnostic_loopback(
                b"err", test_id="pl-error", sequence=0, endpoint="pl"
            )
        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_FAILURE)
        self.port.fail_on_write = False
        with self.assertRaises(PlasmaError) as retry:
            await client.diagnostic_loopback(
                b"err", test_id="no-retry", sequence=1, endpoint="pl"
            )
        self.assertEqual(retry.exception.code, ErrorCode.OPERATION_UNSUPPORTED)
        self.assertEqual(self.port.data_writes, 0)
        meta, data = await client.diagnostic_loopback(
            b"safe ps", test_id="ps-only", sequence=2
        )
        self.assertEqual(meta["source"], "ps")
        self.assertEqual(data, b"safe ps")

    async def test_broken_word_count_is_never_reported_as_hardware_pass(self) -> None:
        client = await self.start_server(enable_pl=True)
        assert self.server is not None
        driver = self.server.lt02_driver
        assert driver is not None
        original = driver.echo

        def dishonest_result(payload: bytes):
            from dataclasses import replace
            return replace(original(payload), data_word_reads=0)

        driver.echo = dishonest_result  # type: ignore[method-assign]
        with self.assertRaises(PlasmaError) as caught:
            await execute_ps_loopback(self.body(b"xyz"), lambda: client)
        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_FAILURE)
        self.assertTrue(self.server._lt02_poisoned)


if __name__ == "__main__":
    unittest.main()

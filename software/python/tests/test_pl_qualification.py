from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.diagnostics import (
    DIAGNOSTIC_PROTOCOL_VERSION,
    DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
    ECHO_TRANSFORM,
    LOOPBACK_DIAGNOSTIC_TYPE,
    PL_LOOPBACK_ENDPOINT,
    PS_LOOPBACK_ENDPOINT,
    crc32_hex,
)
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_server.pl_qualification import PLQualificationServer
from plasma_server.site_manager import SiteManager
from plasma_web.gateway_pl_qualification import PLQualificationWebHandler

from tests.helpers import make_config


class FakePLDevice:
    max_payload_bytes = 64

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, int]] = []
        self.failure: PlasmaError | None = None

    def exchange(self, payload: bytes, *, sequence: int) -> bytes:
        self.calls.append((payload, sequence))
        if self.failure is not None:
            raise self.failure
        return payload


class PLQualificationServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.server: PLQualificationServer | None = None

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def start_server(self, device: FakePLDevice) -> PlasmaClient:
        config = make_config(self.root, enabled_sites=1)
        manager = SiteManager(config)
        self.server = PLQualificationServer(config, manager, pl_loopback=device)  # type: ignore[arg-type]
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=1.0)

    async def test_pl_endpoint_crosses_injected_hardware_boundary_not_site_manager(self) -> None:
        device = FakePLDevice()
        client = await self.start_server(device)
        assert self.server is not None

        def programming_job_must_not_be_enqueued(*_args, **_kwargs):
            raise AssertionError("PL diagnostics must not enter SiteManager programming execution")

        self.server.manager.enqueue = programming_job_must_not_be_enqueued  # type: ignore[method-assign]
        payload = bytes(range(64))
        metadata, returned = await client.diagnostic_loopback(
            payload,
            test_id="pl-real-path-1",
            sequence=0x1234,
            endpoint=PL_LOOPBACK_ENDPOINT,
            pattern="increment",
            seed="",
        )

        self.assertEqual(device.calls, [(payload, 0x1234)])
        self.assertEqual(returned, payload)
        self.assertEqual(metadata["message_type"], DIAGNOSTIC_RESPONSE_MESSAGE_TYPE)
        self.assertEqual(metadata["diagnostic_type"], LOOPBACK_DIAGNOSTIC_TYPE)
        self.assertEqual(metadata["diagnostic_version"], DIAGNOSTIC_PROTOCOL_VERSION)
        self.assertEqual(metadata["endpoint"], PL_LOOPBACK_ENDPOINT)
        self.assertEqual(metadata["source"], PL_LOOPBACK_ENDPOINT)
        self.assertEqual(metadata["test_id"], "pl-real-path-1")
        self.assertEqual(metadata["sequence"], 0x1234)
        self.assertEqual(metadata["tx_crc32"], crc32_hex(payload))
        self.assertEqual(metadata["rx_crc32"], crc32_hex(payload))

    async def test_hardware_timeout_propagates_as_typed_error(self) -> None:
        device = FakePLDevice()
        device.failure = PlasmaError(
            ErrorCode.OPERATION_TIMEOUT,
            "PL hardware timeout",
            recoverable=True,
        )
        client = await self.start_server(device)
        with self.assertRaises(PlasmaError) as caught:
            await client.diagnostic_loopback(
                b"timeout",
                test_id="pl-timeout",
                sequence=1,
                endpoint=PL_LOOPBACK_ENDPOINT,
            )
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_TIMEOUT)
        self.assertTrue(caught.exception.recoverable)

    async def test_pl_payload_above_hardware_limit_fails_before_device_exchange(self) -> None:
        device = FakePLDevice()
        client = await self.start_server(device)
        with self.assertRaises(PlasmaError) as caught:
            await client.diagnostic_loopback(
                bytes(65),
                test_id="pl-too-large",
                sequence=1,
                endpoint=PL_LOOPBACK_ENDPOINT,
            )
        self.assertEqual(caught.exception.code, ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE)
        self.assertEqual(device.calls, [])


class FakeDiagnosticClient:
    calls: list[dict[str, object]] = []

    async def diagnostic_loopback(
        self,
        payload: bytes,
        *,
        test_id: str,
        sequence: int,
        endpoint: str,
        pattern: str | None,
        seed: str | None,
        response_timeout_s: float | None,
    ):
        self.__class__.calls.append(
            {
                "payload": payload,
                "test_id": test_id,
                "sequence": sequence,
                "endpoint": endpoint,
                "response_timeout_s": response_timeout_s,
            }
        )
        crc = crc32_hex(payload)
        return (
            {
                "ok": True,
                "message_type": DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
                "diagnostic_type": LOOPBACK_DIAGNOSTIC_TYPE,
                "diagnostic_version": DIAGNOSTIC_PROTOCOL_VERSION,
                "endpoint": endpoint,
                "source": endpoint,
                "test_id": test_id,
                "sequence": sequence,
                "transform": ECHO_TRANSFORM,
                "payload_length": len(payload),
                "tx_crc32": crc,
                "rx_crc32": crc,
                "pattern": pattern,
                "seed": seed,
            },
            payload,
        )


class PLQualificationGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original_factory = PLQualificationWebHandler.client_factory
        PLQualificationWebHandler.client_factory = staticmethod(FakeDiagnosticClient)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PLQualificationWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        PLQualificationWebHandler.client_factory = cls.original_factory

    def setUp(self) -> None:
        FakeDiagnosticClient.calls.clear()

    def request(self, endpoint: str, payload: bytes) -> tuple[int, dict[str, object]]:
        body = {
            "endpoint": endpoint,
            "test_id": "browser-pl-test",
            "sequence": 5,
            "pattern": "increment",
            "seed": "",
            "payload_length": len(payload),
            "payload_base64": base64.b64encode(payload).decode("ascii"),
            "tx_crc32": crc32_hex(payload),
            "timeout_ms": 1500,
        }
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(
            "POST",
            "/api/engineering/diagnostics/loopback",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        decoded = json.loads(response.read())
        conn.close()
        return response.status, decoded

    def test_gateway_accepts_real_pl_endpoint_and_preserves_source_proof(self) -> None:
        payload = b"pl-gateway"
        status, response = self.request(PL_LOOPBACK_ENDPOINT, payload)
        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        loopback = response["loopback"]
        assert isinstance(loopback, dict)
        self.assertEqual(loopback["endpoint"], "pl")
        self.assertEqual(loopback["source"], "pl")
        self.assertEqual(base64.b64decode(response["payload_base64"]), payload)
        self.assertEqual(FakeDiagnosticClient.calls[0]["endpoint"], "pl")

    def test_gateway_keeps_existing_ps_endpoint_working(self) -> None:
        status, response = self.request(PS_LOOPBACK_ENDPOINT, b"ps-unchanged")
        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        loopback = response["loopback"]
        assert isinstance(loopback, dict)
        self.assertEqual(loopback["endpoint"], "ps")
        self.assertEqual(loopback["source"], "ps")

    def test_gateway_rejects_pl_payload_above_hardware_boundary(self) -> None:
        status, response = self.request(PL_LOOPBACK_ENDPOINT, bytes(65))
        self.assertEqual(status, 400)
        self.assertFalse(response["ok"])
        error = response["error"]
        assert isinstance(error, dict)
        self.assertEqual(error["error_code"], ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE.value)
        self.assertEqual(FakeDiagnosticClient.calls, [])


if __name__ == "__main__":
    unittest.main()

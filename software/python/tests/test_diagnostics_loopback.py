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
    PS_LOOPBACK_ENDPOINT,
    crc32_hex,
)
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager
from plasma_web.gateway import PlasmaWebHandler

from tests.helpers import make_config


class ClientServerDiagnosticLoopbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.server: PlasmaServer | None = None

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def start_server(self) -> PlasmaClient:
        config = make_config(
            self.root,
            enabled_sites=1,
            site_options={
                1: {
                    "mock": {
                        "failures": {"erase": 99, "program": 99, "verify": 99, "read": 99},
                        "failure_recoverable": False,
                    }
                }
            },
        )
        manager = SiteManager(config)
        self.server = PlasmaServer(config, manager)
        await self.server.start()
        return PlasmaClient(*self.server.address, response_timeout_s=2.0)

    async def test_ps_loopback_round_trips_binary_over_real_tcp_server_path(self) -> None:
        client = await self.start_server()
        assert self.server is not None

        def programming_job_must_not_be_enqueued(*_args, **_kwargs):
            raise AssertionError("PS diagnostics must not enter the programming Site/MockInterface path")

        self.server.manager.enqueue = programming_job_must_not_be_enqueued  # type: ignore[method-assign]
        payload = bytes(range(256)) * 8
        metadata, returned = await client.diagnostic_loopback(
            payload,
            test_id="ps-real-path-1",
            sequence=7,
            pattern="increment",
            seed="",
        )

        self.assertEqual(returned, payload)
        self.assertEqual(metadata["message_type"], DIAGNOSTIC_RESPONSE_MESSAGE_TYPE)
        self.assertEqual(metadata["diagnostic_type"], LOOPBACK_DIAGNOSTIC_TYPE)
        self.assertEqual(metadata["diagnostic_version"], DIAGNOSTIC_PROTOCOL_VERSION)
        self.assertEqual(metadata["endpoint"], PS_LOOPBACK_ENDPOINT)
        self.assertEqual(metadata["source"], PS_LOOPBACK_ENDPOINT)
        self.assertEqual(metadata["test_id"], "ps-real-path-1")
        self.assertEqual(metadata["sequence"], 7)
        self.assertEqual(metadata["transform"], ECHO_TRANSFORM)
        self.assertEqual(metadata["payload_length"], len(payload))
        self.assertEqual(metadata["tx_crc32"], crc32_hex(payload))
        self.assertEqual(metadata["rx_crc32"], crc32_hex(payload))

    async def test_unimplemented_pl_endpoint_fails_closed(self) -> None:
        client = await self.start_server()
        with self.assertRaises(PlasmaError) as caught:
            await client.diagnostic_loopback(
                b"pl-not-ready",
                test_id="pl-not-ready",
                sequence=0,
                endpoint="pl",
            )
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)


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
                "pattern": pattern,
                "seed": seed,
                "response_timeout_s": response_timeout_s,
            }
        )
        crc32 = crc32_hex(payload)
        return (
            {
                "ok": True,
                "message_type": DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
                "diagnostic_type": LOOPBACK_DIAGNOSTIC_TYPE,
                "diagnostic_version": DIAGNOSTIC_PROTOCOL_VERSION,
                "endpoint": PS_LOOPBACK_ENDPOINT,
                "source": PS_LOOPBACK_ENDPOINT,
                "test_id": test_id,
                "sequence": sequence,
                "transform": ECHO_TRANSFORM,
                "payload_length": len(payload),
                "tx_crc32": crc32,
                "rx_crc32": crc32,
                "pattern": pattern,
                "seed": seed,
            },
            payload,
        )


class DiagnosticLoopbackGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.addClassCleanup(setattr, PlasmaWebHandler, "client_factory", PlasmaWebHandler.client_factory)
        PlasmaWebHandler.client_factory = staticmethod(FakeDiagnosticClient)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlasmaWebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self) -> None:
        FakeDiagnosticClient.calls.clear()

    def request(self, body: dict[str, object]):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        raw = json.dumps(body).encode()
        conn.request(
            "POST",
            "/api/engineering/diagnostics/loopback",
            raw,
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        conn.close()
        return response.status, payload

    @staticmethod
    def body(payload: bytes, *, endpoint: str = "ps") -> dict[str, object]:
        return {
            "endpoint": endpoint,
            "test_id": "browser-test-1",
            "sequence": 3,
            "pattern": "increment",
            "seed": "",
            "payload_length": len(payload),
            "payload_base64": base64.b64encode(payload).decode("ascii"),
            "tx_crc32": crc32_hex(payload),
            "timeout_ms": 1500,
        }

    def test_rest_route_bridges_payload_to_ps_client_and_back(self) -> None:
        source = b"browser-gateway-server-real-path"
        status, payload = self.request(self.body(source))

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["rest_contract_version"], "3")
        self.assertEqual(payload["diagnostic_protocol_version"], DIAGNOSTIC_PROTOCOL_VERSION)
        self.assertEqual(payload["loopback"]["source"], "ps")
        self.assertEqual(payload["loopback"]["tx_crc32"], crc32_hex(source))
        self.assertEqual(payload["loopback"]["rx_crc32"], crc32_hex(source))
        self.assertEqual(base64.b64decode(payload["payload_base64"]), source)
        self.assertEqual(len(FakeDiagnosticClient.calls), 1)
        self.assertEqual(FakeDiagnosticClient.calls[0]["payload"], source)
        self.assertEqual(FakeDiagnosticClient.calls[0]["response_timeout_s"], 1.5)

    def test_rest_route_rejects_pl_without_fallback(self) -> None:
        status, payload = self.request(self.body(b"no-pl-fallback", endpoint="pl"))
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["error_code"], ErrorCode.OPERATION_UNSUPPORTED.value)
        self.assertEqual(FakeDiagnosticClient.calls, [])

    def test_rest_route_rejects_browser_crc_mismatch_before_ps_request(self) -> None:
        body = self.body(b"crc-guard")
        body["tx_crc32"] = "00000000"
        status, payload = self.request(body)
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["error_code"], ErrorCode.PROTOCOL_CHECKSUM_MISMATCH.value)
        self.assertEqual(FakeDiagnosticClient.calls, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from plasma_core.config import load_config
from plasma_core.diagnostics import (
    DIAGNOSTIC_PROTOCOL_VERSION,
    DIAGNOSTIC_REQUEST_MESSAGE_TYPE,
    DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
    ECHO_TRANSFORM,
    LOOPBACK_DIAGNOSTIC_TYPE,
    PL_LOOPBACK_ENDPOINT,
    crc32_hex,
    require_crc32,
    require_nonnegative_int,
    require_positive_int,
    require_test_id,
)
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.protocol import PROTOCOL_VERSION, Frame
from plasma_hw.pl_loopback import PLLoopbackDevice, UIORegisterIO

from .server import PlasmaServer


class PLQualificationServer(PlasmaServer):
    """Plasma Server variant that opens only the approved PL diagnostic endpoint.

    Normal Programming Job/Site behavior is inherited unchanged. The added path
    is PPU-wide diagnostics only and never enters SiteManager/MockInterface.
    """

    def __init__(self, *args: Any, pl_loopback: PLLoopbackDevice, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pl_loopback = pl_loopback

    async def _dispatch(self, frame: Frame, peer: Any) -> Frame:
        metadata = frame.metadata
        if (
            metadata.get("message_type") == DIAGNOSTIC_REQUEST_MESSAGE_TYPE
            and metadata.get("endpoint") == PL_LOOPBACK_ENDPOINT
        ):
            return await self._dispatch_pl_diagnostic(frame, peer)
        return await super()._dispatch(frame, peer)

    async def _dispatch_pl_diagnostic(self, frame: Frame, peer: Any) -> Frame:
        metadata = frame.metadata
        allowed = {
            "protocol_version",
            "message_type",
            "diagnostic_type",
            "diagnostic_version",
            "endpoint",
            "test_id",
            "sequence",
            "transform",
            "payload_length",
            "tx_crc32",
            "pattern",
            "seed",
        }
        unknown = sorted(set(metadata) - allowed)
        if unknown:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"diagnostic request contains unexpected fields: {', '.join(unknown)}",
            )
        if metadata.get("protocol_version") != PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {metadata.get('protocol_version')!r}",
            )
        if metadata.get("diagnostic_type") != LOOPBACK_DIAGNOSTIC_TYPE:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "unsupported diagnostic_type")
        if metadata.get("diagnostic_version") != DIAGNOSTIC_PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported diagnostic version: {metadata.get('diagnostic_version')!r}",
            )
        if metadata.get("transform") != ECHO_TRANSFORM:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PL loopback requires echo transform")

        test_id = require_test_id(metadata.get("test_id"))
        sequence = require_nonnegative_int(metadata.get("sequence"), "sequence")
        if sequence > 0xFFFFFFFF:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PL loopback sequence must fit uint32")
        payload_length = require_positive_int(metadata.get("payload_length"), "payload_length")
        if payload_length != len(frame.binary):
            raise PlasmaError(
                ErrorCode.PROTOCOL_INCOMPLETE,
                "payload_length does not match diagnostic binary payload",
                context={"declared": payload_length, "actual": len(frame.binary)},
            )
        if payload_length > self.pl_loopback.max_payload_bytes:
            raise PlasmaError(
                ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE,
                f"PL loopback payload exceeds hardware limit of {self.pl_loopback.max_payload_bytes} bytes",
            )

        tx_crc32 = require_crc32(metadata.get("tx_crc32"), "tx_crc32")
        actual_crc32 = crc32_hex(frame.binary)
        if tx_crc32 != actual_crc32:
            raise PlasmaError(
                ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                "tx_crc32 does not match diagnostic binary payload",
                context={"expected": tx_crc32, "actual": actual_crc32},
            )

        for field in ("pattern", "seed"):
            value = metadata.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 128):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"{field} must be a string of at most 128 characters")

        returned = await asyncio.to_thread(
            self.pl_loopback.exchange,
            frame.binary,
            sequence=sequence,
        )
        rx_crc32 = crc32_hex(returned)
        if returned != frame.binary or rx_crc32 != actual_crc32:
            raise PlasmaError(
                ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                "PL loopback returned data does not match the PS request",
            )

        self.manager.server_log.event(
            "INFO",
            "diagnostic_loopback_pl",
            peer=peer,
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            test_id=test_id,
            sequence=sequence,
            payload_length=payload_length,
            crc32=actual_crc32,
        )
        return Frame(
            metadata={
                "protocol_version": PROTOCOL_VERSION,
                "message_type": DIAGNOSTIC_RESPONSE_MESSAGE_TYPE,
                "ok": True,
                "diagnostic_type": LOOPBACK_DIAGNOSTIC_TYPE,
                "diagnostic_version": DIAGNOSTIC_PROTOCOL_VERSION,
                "endpoint": PL_LOOPBACK_ENDPOINT,
                "source": PL_LOOPBACK_ENDPOINT,
                "test_id": test_id,
                "sequence": sequence,
                "transform": ECHO_TRANSFORM,
                "payload_length": payload_length,
                "tx_crc32": actual_crc32,
                "rx_crc32": rx_crc32,
                **({"pattern": metadata["pattern"]} if "pattern" in metadata else {}),
                **({"seed": metadata["seed"]} if "seed" in metadata else {}),
            },
            binary=returned,
        )


async def _run_server(
    config_path: Path,
    *,
    uio_path: Path,
    map_size: int,
    transaction_timeout_s: float,
) -> None:
    registers = UIORegisterIO(uio_path, map_size=map_size)
    device: PLLoopbackDevice | None = None
    server: PLQualificationServer | None = None
    try:
        device = PLLoopbackDevice(registers, transaction_timeout_s=transaction_timeout_s)
        server = PLQualificationServer(load_config(config_path), pl_loopback=device)
        await server.start()
        print(
            f"Plasma PL Qualification Server v{PROTOCOL_VERSION} listening on "
            f"{server.address[0]}:{server.address[1]}"
        )
        await server.serve_forever()
    finally:
        if server is not None:
            await server.close()
        if device is not None:
            device.close()
        else:
            registers.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plasma Server with formal PYNQ-Z2 PS<->PL Loopback qualification endpoint"
    )
    parser.add_argument("--config", type=Path, default=Path("config/plasma.yaml"))
    parser.add_argument("--uio-path", type=Path, default=Path("/dev/uio0"))
    parser.add_argument("--map-size", type=int, default=4096)
    parser.add_argument("--transaction-timeout-s", type=float, default=0.25)
    args = parser.parse_args()
    try:
        asyncio.run(
            _run_server(
                args.config,
                uio_path=args.uio_path,
                map_size=args.map_size,
                transaction_timeout_s=args.transaction_timeout_s,
            )
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

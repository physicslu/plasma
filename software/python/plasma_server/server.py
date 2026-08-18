from __future__ import annotations

import argparse
import asyncio
import contextlib
import math
from pathlib import Path
from typing import Any

from plasma_core.config import PlasmaConfig, load_config
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import ErrorDetail, JobRequest, new_job_id, site_id_from_legacy_channel
from plasma_core.protocol import (
    LEGACY_PROTOCOL_VERSION,
    PROTOCOL_VERSION,
    Frame,
    ProtocolLimits,
    encode_frame,
    read_frame,
)

from .site_manager import SiteManager


class PlasmaServer:
    def __init__(self, config: PlasmaConfig, manager: SiteManager | None = None) -> None:
        self.config = config
        self.manager = manager or SiteManager(config)
        self._server: asyncio.Server | None = None
        self.limits = ProtocolLimits(
            metadata=config.server.max_metadata_bytes,
            map_data=config.server.max_map_bytes,
            binary=config.server.max_binary_bytes,
        )

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("server is not started")
        host, port = self._server.sockets[0].getsockname()[:2]
        return str(host), int(port)

    async def start(self) -> None:
        await self.manager.start()
        self._server = await asyncio.start_server(
            self._handle_connection,
            host=self.config.server.host,
            port=self.config.server.port,
        )
        self.manager.server_log.event(
            "INFO",
            "server_started",
            ppu_id=self.config.ppu.id,
            facility_id=self.config.ppu.facility_id,
            protocol_version=PROTOCOL_VERSION,
            host=self.address[0],
            port=self.address[1],
        )

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        await self.manager.shutdown()

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    @staticmethod
    def _site_id_from_wire(metadata: dict[str, Any], *, required: bool) -> int | None:
        version = metadata.get("protocol_version")
        if version == PROTOCOL_VERSION:
            if "channel_id" in metadata:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "protocol v3.2 uses site_id; channel_id is a v3.1 field",
                )
            raw = metadata.get("site_id")
            label = "site_id"
            if raw is None and not required:
                return None
            if isinstance(raw, bool):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "site_id must be an integer")
            try:
                site_id = int(raw)
            except (TypeError, ValueError, OverflowError) as exc:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "site_id must be an integer",
                    original_exception=exc,
                ) from exc
            if site_id < 1:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "site_id must start at 1")
            return site_id
        if version == LEGACY_PROTOCOL_VERSION:
            if "site_id" in metadata:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "protocol v3.1 uses channel_id; site_id requires v3.2",
                )
            raw = metadata.get("channel_id")
            label = "channel_id"
            if raw is None and not required:
                return None
            if isinstance(raw, bool):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "channel_id must be an integer")
            try:
                channel_id = int(raw)
            except (TypeError, ValueError, OverflowError) as exc:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "channel_id must be an integer",
                    original_exception=exc,
                ) from exc
            try:
                return site_id_from_legacy_channel(channel_id)
            except PlasmaError as exc:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, f"invalid {label}") from exc
        raise PlasmaError(
            ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
            f"unsupported protocol version: {version!r}",
        )

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        job_id: str | None = None
        site_id: int | None = None
        operation: str | None = None
        response_version = PROTOCOL_VERSION
        try:
            frame = await read_frame(reader, self.limits)
            response_version = str(frame.metadata.get("protocol_version", PROTOCOL_VERSION))
            job_id = frame.metadata.get("job_id")
            site_id = self._site_id_from_wire(frame.metadata, required=False)
            operation = frame.metadata.get("operation")
            response = await self._dispatch(frame, peer)
        except PlasmaError as exc:
            detail = ErrorDetail.from_exception(
                exc,
                site_id=site_id,
                job_id=job_id,
                operation=operation,
            )
            response = Frame(
                metadata={
                    "protocol_version": response_version,
                    "message_type": "response",
                    "ok": False,
                    "error": detail.to_dict(response_version),
                }
            )
            self.manager.server_log.event(
                "ERROR",
                "request_failed",
                peer=peer,
                job_id=job_id,
                site_id=site_id,
                operation=operation,
                error_code=exc.code.value,
                message=exc.message,
            )
        except Exception as exc:  # final network/plugin safety boundary
            error = PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "unexpected server error",
                original_exception=exc,
            )
            response = Frame(
                metadata={
                    "protocol_version": response_version,
                    "message_type": "response",
                    "ok": False,
                    "error": ErrorDetail.from_exception(error).to_dict(response_version),
                }
            )
            self.manager.server_log.event("ERROR", "server_exception", peer=peer, error=str(exc))

        try:
            writer.write(encode_frame(response, self.limits))
            await writer.drain()
        except (ConnectionError, BrokenPipeError):
            self.manager.server_log.event("WARNING", "response_connection_lost", peer=peer, job_id=job_id)
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    async def _dispatch(self, frame: Frame, peer: Any) -> Frame:
        metadata = frame.metadata
        protocol_version = str(metadata["protocol_version"])
        try:
            operation = Operation(str(metadata["operation"]))
        except (KeyError, ValueError) as exc:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"invalid operation: {metadata.get('operation')!r}",
                original_exception=exc,
            ) from exc

        if operation is Operation.STATUS:
            site_id = self._site_id_from_wire(metadata, required=False)
            result = self.manager.status(
                site_id=site_id,
                job_id=metadata.get("target_job_id"),
                protocol_version=protocol_version,
            )
            return self._success(result, protocol_version)

        if operation is Operation.CANCEL:
            target_job_id = metadata.get("target_job_id")
            if not target_job_id:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "cancel requires target_job_id")
            return self._success(self.manager.cancel(str(target_job_id)), protocol_version)

        site_id = self._site_id_from_wire(metadata, required=True)
        assert site_id is not None
        site_config = self.manager._site_configs.get(site_id)
        try:
            timeout_raw = metadata.get(
                "timeout_s", site_config.operation_timeout_s if site_config else 30.0
            )
            retries_raw = metadata.get(
                "max_retries", site_config.max_retries if site_config else 0
            )
            backoff_raw = metadata.get(
                "retry_backoff_s", site_config.retry_backoff_s if site_config else 0.05
            )
            if any(isinstance(value, bool) for value in (timeout_raw, retries_raw, backoff_raw)):
                raise ValueError("boolean is not a numeric retry setting")
            timeout_s = float(timeout_raw)
            max_retries = int(retries_raw)
            retry_backoff_s = float(backoff_raw)
            if float(max_retries) != float(retries_raw):
                raise ValueError("max_retries must be an integer")
        except (TypeError, ValueError, OverflowError) as exc:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "invalid timeout or retry settings",
                original_exception=exc,
            ) from exc
        if (
            not math.isfinite(timeout_s)
            or not math.isfinite(retry_backoff_s)
            or timeout_s <= 0
            or max_retries < 0
            or retry_backoff_s < 0
        ):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid timeout or retry settings")
        expected_size = metadata.get("firmware_size")
        if expected_size is not None:
            if isinstance(expected_size, bool):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "firmware_size must be an integer")
            try:
                parsed_size = int(expected_size)
            except (TypeError, ValueError, OverflowError) as exc:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "firmware_size must be an integer",
                    original_exception=exc,
                ) from exc
            if parsed_size != len(frame.binary):
                raise PlasmaError(
                    ErrorCode.PROTOCOL_INCOMPLETE,
                    "firmware_size does not match BINLEN",
                    context={"firmware_size": expected_size, "binlen": len(frame.binary)},
                )

        known = {
            "protocol_version",
            "message_type",
            "job_id",
            "site_id",
            "channel_id",
            "operation",
            "timeout_s",
            "max_retries",
            "retry_backoff_s",
            "client_id",
            "target",
            "firmware_size",
            "firmware_sha256",
            "wait_for_completion",
        }
        job_id_raw = metadata.get("job_id")
        if job_id_raw is not None and not isinstance(job_id_raw, str):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "job_id must be a string")
        wait_for_completion = metadata.get("wait_for_completion", True)
        if not isinstance(wait_for_completion, bool):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "wait_for_completion must be boolean")
        request = JobRequest(
            site_id=site_id,
            operation=operation,
            firmware=frame.binary,
            map_data=frame.map_data,
            job_id=job_id_raw or new_job_id(),
            timeout_s=timeout_s,
            max_retries=max_retries,
            retry_backoff_s=retry_backoff_s,
            client_id=str(metadata.get("client_id") or peer),
            target=str(metadata.get("target", "STM32F103C8T6")),
            metadata={key: value for key, value in metadata.items() if key not in known},
        )
        future = self.manager.enqueue(request)
        if not wait_for_completion:
            runtime = self.manager.registry.get(request.job_id)
            return self._success(
                {"accepted": True, "job": runtime.snapshot(protocol_version)},
                protocol_version,
            )
        result = await future
        return self._success({"result": result.to_dict(protocol_version)}, protocol_version)

    @staticmethod
    def _success(payload: dict[str, Any], protocol_version: str = PROTOCOL_VERSION) -> Frame:
        return Frame(
            metadata={
                "protocol_version": protocol_version,
                "message_type": "response",
                "ok": True,
                **payload,
            }
        )


async def _run_server(config_path: Path) -> None:
    server = PlasmaServer(load_config(config_path))
    await server.start()
    print(
        f"Plasma Server v{PROTOCOL_VERSION} listening on "
        f"{server.address[0]}:{server.address[1]}"
    )
    try:
        await server.serve_forever()
    finally:
        await server.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plasma multi-site programming server")
    parser.add_argument("--config", type=Path, default=Path("config/plasma.yaml"))
    args = parser.parse_args()
    try:
        asyncio.run(_run_server(args.config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import math
from pathlib import Path
from typing import Any

from plasma_core.config import PlasmaConfig, load_config
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_image_store import default_mock_image_store
from plasma_core.models import (
    LOCAL_MOCK_BLOB_SCHEME,
    ErrorDetail,
    ExecutionImageRef,
    JobRequest,
    new_job_id,
)
from plasma_core.protocol import (
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
        if version != PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {version!r}",
            )
        raw = metadata.get("site_id")
        if raw is None and not required:
            return None
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "site_id must be a JSON integer")
        if raw < 1:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "site_id must start at 1")
        return raw

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        job_id: str | None = None
        site_id: int | None = None
        operation: str | None = None
        try:
            frame = await read_frame(reader, self.limits)
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
                    "protocol_version": PROTOCOL_VERSION,
                    "message_type": "response",
                    "ok": False,
                    "error": detail.to_dict(),
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
        except Exception as exc:
            error = PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "unexpected server error",
                original_exception=exc,
            )
            response = Frame(
                metadata={
                    "protocol_version": PROTOCOL_VERSION,
                    "message_type": "response",
                    "ok": False,
                    "error": ErrorDetail.from_exception(error).to_dict(),
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
        if protocol_version != PROTOCOL_VERSION:
            raise PlasmaError(
                ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                f"unsupported protocol version: {protocol_version!r}",
            )
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
            return self._success(result)

        if operation is Operation.CANCEL:
            target_job_id = metadata.get("target_job_id")
            if not target_job_id:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "cancel requires target_job_id")
            return self._success(self.manager.cancel(str(target_job_id)))

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

        image_ref_raw = metadata.get("execution_image_ref")
        image_ref = ExecutionImageRef.from_dict(image_ref_raw) if image_ref_raw is not None else None
        if image_ref is not None:
            if operation not in {Operation.PROGRAM, Operation.VERIFY}:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "execution image reference is only valid for program or verify",
                )
            if frame.binary:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "execution image reference cannot be combined with inline binary",
                )
            if site_config is None or site_config.interface != "mock":
                raise PlasmaError(
                    ErrorCode.OPERATION_UNSUPPORTED,
                    "execution image references are only supported by the local Mock interface",
                )

        expected_size = metadata.get("image_size")
        if expected_size is not None:
            if isinstance(expected_size, bool):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "image_size must be an integer")
            try:
                parsed_size = int(expected_size)
            except (TypeError, ValueError, OverflowError) as exc:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "image_size must be an integer",
                    original_exception=exc,
                ) from exc
            actual_size = image_ref.size_bytes if image_ref is not None else len(frame.binary)
            if parsed_size != actual_size:
                raise PlasmaError(
                    ErrorCode.PROTOCOL_INCOMPLETE,
                    "image_size does not match execution image payload",
                    context={"image_size": expected_size, "actual_size": actual_size},
                )

        expected_sha256 = metadata.get("image_sha256")
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str):
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "image_sha256 must be a string")
            actual_sha256 = (
                image_ref.sha256
                if image_ref is not None
                else hashlib.sha256(frame.binary).hexdigest()
            )
            if expected_sha256 != actual_sha256:
                raise PlasmaError(
                    ErrorCode.PROTOCOL_CHECKSUM_MISMATCH,
                    "image_sha256 does not match execution image payload",
                    context={"expected": expected_sha256, "actual": actual_sha256},
                )

        inline_image = frame.binary
        if (
            image_ref is None
            and frame.binary
            and operation in {Operation.PROGRAM, Operation.VERIFY}
            and site_config is not None
            and site_config.interface == "mock"
        ):
            shared = default_mock_image_store().put(frame.binary)
            image_ref = ExecutionImageRef(
                scheme=LOCAL_MOCK_BLOB_SCHEME,
                sha256=shared.sha256,
                size_bytes=shared.size_bytes,
            )
            inline_image = b""

        known = {
            "protocol_version",
            "message_type",
            "job_id",
            "site_id",
            "operation",
            "timeout_s",
            "max_retries",
            "retry_backoff_s",
            "client_id",
            "target",
            "image_size",
            "image_sha256",
            "execution_image_ref",
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
            image=inline_image,
            image_ref=image_ref,
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
            return self._success({"accepted": True, "job": runtime.snapshot(protocol_version)})
        result = await future
        return self._success({"result": result.to_dict(protocol_version)})

    @staticmethod
    def _success(payload: dict[str, Any]) -> Frame:
        return Frame(
            metadata={
                "protocol_version": PROTOCOL_VERSION,
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

from __future__ import annotations

import copy
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.mock_image_store import default_mock_image_store
from plasma_core.models import LOCAL_MOCK_BLOB_SCHEME, ExecutionImageRef, JobRequest

from .engineering_targets import MockEngineeringPPUProvider
from .mock_runtime_settings import MockRuntimeSettingsController
from .mock_synthetic_image import synthetic_mock_asset_from_context


class SharedImageMockEngineeringPPUProvider(MockEngineeringPPUProvider):
    """Mock multi-PPU provider with shared Images and immutable runtime settings.

    Programming/Verify Images remain content-addressed. In addition, every Job
    receives a Mock execution context. Server-side Batches freeze that context
    by Batch ID so a later settings edit cannot change an already-running Batch.
    Direct Engineering Jobs freeze the current settings at submission time.
    """

    def __init__(
        self,
        root: Path,
        *,
        flash_size_bytes: int = 4 * 1024 * 1024,
        mock_profile_path: str | Path | None = None,
    ) -> None:
        super().__init__(root, flash_size_bytes=flash_size_bytes)
        self.mock_runtime = MockRuntimeSettingsController(mock_profile_path)
        self._mock_context_lock = threading.RLock()
        self._batch_mock_contexts: dict[str, dict[str, Any]] = {}

    def close(self, timeout_s: float = 10.0) -> None:
        try:
            super().close(timeout_s=timeout_s)
        finally:
            with self._mock_context_lock:
                self._batch_mock_contexts.clear()

    def mock_runtime_settings(self) -> dict[str, Any]:
        return self.mock_runtime.current()

    def update_mock_runtime_settings(self, raw: dict[str, Any]) -> dict[str, Any]:
        return self.mock_runtime.update(raw)

    def freeze_batch_context(self, batch_id: str) -> dict[str, Any]:
        if not isinstance(batch_id, str) or not batch_id:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Mock Batch ID is required")
        with self._mock_context_lock:
            existing = self._batch_mock_contexts.get(batch_id)
            if existing is None:
                existing = self.mock_runtime.execution_snapshot(batch_id)
                self._batch_mock_contexts[batch_id] = existing
            return copy.deepcopy(existing)

    def release_batch_context(self, batch_id: str) -> None:
        with self._mock_context_lock:
            self._batch_mock_contexts.pop(batch_id, None)

    def batch_context(self, batch_id: str) -> dict[str, Any] | None:
        with self._mock_context_lock:
            context = self._batch_mock_contexts.get(batch_id)
            return copy.deepcopy(context) if context is not None else None

    def _execution_context_for_request(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
    ) -> dict[str, Any]:
        raw_batch_id = request.metadata.get("batch_id")
        if isinstance(raw_batch_id, str) and raw_batch_id:
            context = self.freeze_batch_context(raw_batch_id)
        else:
            context = self.mock_runtime.execution_snapshot(f"engineering-{request.job_id}")
        raw_round = request.metadata.get("batch_round", 1)
        if isinstance(raw_round, bool) or not isinstance(raw_round, int) or raw_round < 1:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Mock round index must be a positive integer")
        return {
            **context,
            "facility_id": facility_id,
            "ppu_id": ppu_id,
            "site_id": request.site_id,
            "round_index": raw_round,
        }

    def _decorate_mock_request(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
    ) -> JobRequest:
        return replace(
            request,
            metadata={
                **request.metadata,
                "mock_runtime": self._execution_context_for_request(facility_id, ppu_id, request),
            },
        )

    def cache_asset(
        self,
        session_id: str,
        facility_id: str,
        ppu_id: str,
        asset_name: str,
        asset_type: str,
        asset_format: str,
        asset_sha256: str,
        data: bytes,
    ) -> dict[str, object]:
        result = super().cache_asset(
            session_id,
            facility_id,
            ppu_id,
            asset_name,
            asset_type,
            asset_format,
            asset_sha256,
            data,
        )
        asset = self._cached_asset(session_id, facility_id, ppu_id, asset_sha256)
        image = asset.normalize_image()
        default_mock_image_store().put(image.data)
        return result

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
        *,
        session_id: str | None = None,
        asset_sha256: str | None = None,
    ) -> dict[str, object]:
        request = self._decorate_mock_request(facility_id, ppu_id, request)
        lease_key: tuple[str, str] | None = None
        if request.operation in {Operation.PROGRAM, Operation.VERIFY}:
            if request.image or request.image_ref is not None:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Engineering program/verify must use a session-cached or Mock Synthetic Programming Asset",
                )
            if not session_id:
                raise PlasmaError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Engineering program/verify requires session_id",
                )
            if asset_sha256:
                asset = self._cached_asset(session_id, facility_id, ppu_id, asset_sha256)
                asset_origin = "user"
            else:
                context = request.metadata.get("mock_runtime")
                if not isinstance(context, dict):
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "Mock execution context is unavailable")
                asset = synthetic_mock_asset_from_context(context)
                asset_origin = "mock_synthetic"
            image = asset.normalize_image()
            shared = default_mock_image_store().put(image.data)
            lease_key = self._key(facility_id, ppu_id)
            self._reserve_ppu_image(lease_key, image.sha256, request.job_id)
            request = replace(
                request,
                image_ref=ExecutionImageRef(
                    scheme=LOCAL_MOCK_BLOB_SCHEME,
                    sha256=shared.sha256,
                    size_bytes=shared.size_bytes,
                ),
                metadata={
                    **request.metadata,
                    "image_name": image.name,
                    "source_asset_name": asset.name,
                    "source_asset_sha256": asset.sha256,
                    "source_asset_type": asset.asset_type.value,
                    "source_asset_format": asset.asset_format.value,
                    "source_asset_origin": asset_origin,
                },
            )
        elif session_id is not None or asset_sha256 is not None:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "session Programming Asset reference is only valid for program or verify",
            )

        request = replace(request, timeout_s=self.job_timeout_s(facility_id, ppu_id))
        try:
            accepted = await self._client(facility_id, ppu_id).start(request)
        except Exception:
            if lease_key is not None:
                self._release_ppu_image(lease_key, request.job_id)
            raise
        if lease_key is not None:
            self._schedule_image_watch(lease_key, request.job_id)
        return accepted

from __future__ import annotations

import threading
from typing import Any

from plasma_core.batch import normalize_batch_operations
from plasma_core.enums import Operation

from .batch_runtime import BatchRuntimeManager
from .mock_synthetic_image import synthetic_mock_asset_from_context
from .shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class MockAwareBatchRuntimeManager(BatchRuntimeManager):
    """BatchRuntime adapter that freezes and exposes Mock execution provenance.

    Generic BatchRuntime stays unaware of MockProfile. This adapter reserves a
    provider-side immutable Mock context as soon as the Batch ID is allocated,
    before any Site thread can submit a Job. Program/Verify Batches without a
    user Programming Image receive one deterministic Synthetic Image derived
    from that same frozen profile snapshot.
    """

    provider: SharedImageMockEngineeringPPUProvider

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._creation_local = threading.local()

    @staticmethod
    def _mock_payload(snapshot: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
        if context is None:
            return snapshot
        return {**snapshot, "mock_runtime": context}

    def _new_batch_id(self) -> str:
        pending = getattr(self._creation_local, "batch_id", None)
        if isinstance(pending, str) and pending:
            self._creation_local.batch_id = None
            return pending
        batch_id = super()._new_batch_id()
        self.provider.freeze_batch_context(batch_id)
        return batch_id

    def create_batch(self, **kwargs: Any) -> dict[str, Any]:
        ordered_operations = normalize_batch_operations(kwargs.get("operations", ()))
        requires_asset = any(operation in {Operation.PROGRAM, Operation.VERIFY} for operation in ordered_operations)
        preallocated_batch_id: str | None = None

        if requires_asset and kwargs.get("asset") is None:
            preallocated_batch_id = super()._new_batch_id()
            context = self.provider.freeze_batch_context(preallocated_batch_id)
            kwargs["asset"] = synthetic_mock_asset_from_context(context)
            self._creation_local.batch_id = preallocated_batch_id

        try:
            snapshot = super().create_batch(**kwargs)
        except Exception:
            if preallocated_batch_id is not None:
                self.provider.release_batch_context(preallocated_batch_id)
            raise
        finally:
            if preallocated_batch_id is not None:
                self._creation_local.batch_id = None

        batch_id = str(snapshot["batch_id"])
        return self._mock_payload(snapshot, self.provider.batch_context(batch_id))

    def get(self, batch_id: str) -> dict[str, Any]:
        return self._mock_payload(super().get(batch_id), self.provider.batch_context(batch_id))

    def cancel(self, batch_id: str) -> dict[str, Any]:
        return self._mock_payload(super().cancel(batch_id), self.provider.batch_context(batch_id))

    def cancel_ppu(self, batch_id: str, facility_id: str, ppu_id: str) -> dict[str, Any]:
        return self._mock_payload(
            super().cancel_ppu(batch_id, facility_id, ppu_id),
            self.provider.batch_context(batch_id),
        )

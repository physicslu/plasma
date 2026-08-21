from __future__ import annotations

from typing import Any

from .batch_runtime import BatchRuntimeManager
from .shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class MockAwareBatchRuntimeManager(BatchRuntimeManager):
    """BatchRuntime adapter that freezes and exposes Mock execution provenance.

    Generic BatchRuntime stays unaware of MockProfile. This adapter reserves a
    provider-side immutable Mock context as soon as the Batch ID is allocated,
    before any Site thread can submit a Job.
    """

    provider: SharedImageMockEngineeringPPUProvider

    @staticmethod
    def _mock_payload(snapshot: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
        if context is None:
            return snapshot
        return {**snapshot, "mock_runtime": context}

    def _new_batch_id(self) -> str:
        batch_id = super()._new_batch_id()
        self.provider.freeze_batch_context(batch_id)
        return batch_id

    def create_batch(self, **kwargs: Any) -> dict[str, Any]:
        snapshot = super().create_batch(**kwargs)
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

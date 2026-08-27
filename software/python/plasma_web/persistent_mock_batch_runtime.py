from __future__ import annotations

from pathlib import Path
from typing import Any

from plasma_core.batch import BatchExecutionPolicy, BatchTarget, normalize_batch_operations
from plasma_core.enums import Operation
from plasma_core.models import iso_now

from .batch_runtime import BatchRuntimeManager, BatchTargetDeviceSnapshot
from .mock_synthetic_image import synthetic_mock_asset_from_context
from .persistent_batch_runtime import BATCH_RECOVERY_ERROR, PersistentBatchRuntimeManager
from .shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class PersistentMockAwareBatchRuntimeManager(PersistentBatchRuntimeManager):
    """Persistent Batch runtime for the process-coupled Engineering Mock provider.

    The Mock PPU servers are children of the Gateway process, so a Gateway
    restart also destroys their authoritative Job registries. Non-terminal Mock
    Batches therefore recover as an infrastructure error instead of pretending
    that physical Job reconciliation was possible.
    """

    provider: SharedImageMockEngineeringPPUProvider

    @staticmethod
    def _mock_payload(snapshot: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
        normalized = dict(snapshot)
        if Operation.READ.value in normalized.get("operations", []):
            normalized["read"] = {"scope": "main_flash"}
        if context is not None:
            normalized["mock_runtime"] = context
        return normalized

    def _restore_nonterminal_batches(self) -> None:
        for stored in self._state_store.load_recoverable():
            snapshot = dict(stored.snapshot)
            snapshot.update(
                {
                    "batch_id": stored.batch_id,
                    "state": "error",
                    "finished_at": iso_now(),
                    "stop_reason": "mock_ppu_restart",
                    "error": {
                        "error_code": BATCH_RECOVERY_ERROR,
                        "message": (
                            "Gateway restart also restarted the process-coupled Mock PPU; "
                            "accepted Mock Jobs cannot be authoritatively reconciled"
                        ),
                    },
                }
            )
            self._state_store.save_snapshot(stored.batch_id, snapshot)

    def create_batch(
        self,
        *,
        targets: tuple[BatchTarget, ...],
        operations: list[str] | tuple[str, ...],
        policy: BatchExecutionPolicy,
        session_id: str | None = None,
        target_device: BatchTargetDeviceSnapshot | None = None,
        asset=None,
        read_offset: int = 0,
        read_length: int = 256,
    ) -> dict[str, Any]:
        ordered_operations = normalize_batch_operations(operations)
        requires_asset = any(operation in {Operation.PROGRAM, Operation.VERIFY} for operation in ordered_operations)
        batch_id = BatchRuntimeManager._new_batch_id()
        context = self.provider.freeze_batch_context(batch_id)
        if requires_asset and asset is None:
            asset = synthetic_mock_asset_from_context(context)

        spec = self._spec_from_create(
            targets=targets,
            operations=operations,
            policy=policy,
            gateway_policy=self.gateway_settings.snapshot(),
            session_id=session_id,
            target_device=target_device,
            asset=asset,
            read_offset=read_offset,
            read_length=read_length,
        )
        spec["mock_runtime"] = context
        self._state_store.prepare_batch(
            batch_id,
            spec=spec,
            asset_data=asset.data if asset is not None else None,
        )
        self._creation_local.batch_id = batch_id
        try:
            snapshot = BatchRuntimeManager.create_batch(
                self,
                targets=targets,
                operations=operations,
                policy=policy,
                session_id=session_id,
                target_device=target_device,
                asset=asset,
                read_offset=read_offset,
                read_length=read_length,
            )
        except BaseException:
            self._state_store.discard_batch(batch_id)
            self.provider.release_batch_context(batch_id)
            raise
        finally:
            self._creation_local.batch_id = None
        self._checkpoint_id(batch_id)
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

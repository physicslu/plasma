from .persistent_mock_batch_runtime import PersistentMockAwareBatchRuntimeManager


# Keep the public runtime name stable while moving its implementation onto the
# durable Batch recovery boundary. Existing Gateway wiring and tests continue
# importing MockAwareBatchRuntimeManager.
MockAwareBatchRuntimeManager = PersistentMockAwareBatchRuntimeManager

__all__ = ["MockAwareBatchRuntimeManager"]

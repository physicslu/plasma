from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_web.durable_batch_runtime import DurableBatchRuntimeManager
from plasma_web.gateway import _build_batch_runtime
from plasma_web.gateway_settings import GatewaySettingsController
from plasma_web.persistent_mock_batch_runtime import PersistentMockAwareBatchRuntimeManager
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class GatewayDurableBatchWiringTests(unittest.TestCase):
    def test_no_engineering_provider_has_no_batch_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = _build_batch_runtime(
                None,
                settings=GatewaySettingsController(),
                output_root=Path(directory),
            )
            self.assertIsNone(runtime)

    def test_non_mock_provider_uses_durable_runtime_and_gateway_output_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "gateway-output"
            runtime = _build_batch_runtime(
                object(),  # Construction does not consume Provider methods until a Batch executes.
                settings=GatewaySettingsController(),
                output_root=output_root,
            )
            self.assertIsInstance(runtime, DurableBatchRuntimeManager)
            self.assertEqual(
                runtime._state_store.path,
                (output_root / "batch-state.sqlite3").resolve(),
            )
            runtime.close()

    def test_process_coupled_mock_uses_persistent_mock_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SharedImageMockEngineeringPPUProvider(
                Path(directory) / "engineering-mock",
                flash_size_bytes=1024,
            )
            runtime = _build_batch_runtime(
                provider,
                settings=GatewaySettingsController(),
                output_root=Path(directory) / "gateway-output",
            )
            self.assertIsInstance(runtime, PersistentMockAwareBatchRuntimeManager)
            self.assertEqual(
                runtime._state_store.path,
                (provider.root / "batch-state.sqlite3").resolve(),
            )
            runtime.close()


if __name__ == "__main__":
    unittest.main()

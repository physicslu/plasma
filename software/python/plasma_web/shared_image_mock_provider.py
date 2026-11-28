from __future__ import annotations

from pathlib import Path
from typing import Any

from .engineering_targets import MockEngineeringPPUProvider
from .mock_runtime_settings import MockRuntimeSettingsController


class SharedImageMockEngineeringPPUProvider(MockEngineeringPPUProvider):
    """Mock multi-PPU provider with editable Mock runtime settings.

    Programming runs through the Manager-owned Batch (U7: every Job needs an
    ACTIVE Resource Reservation), never through this Gateway provider. The
    provider only exposes the catalog, Site status, Job output files and the
    Mock runtime settings.
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

    def mock_runtime_settings(self) -> dict[str, Any]:
        return self.mock_runtime.current()

    def update_mock_runtime_settings(self, raw: dict[str, Any]) -> dict[str, Any]:
        return self.mock_runtime.update(raw)

    def catalog(self) -> dict[str, Any]:
        catalog = super().catalog()
        catalog["programming_capabilities"] = {
            "synthetic_programming_image": True,
            "target_device_required": False,
        }
        return catalog

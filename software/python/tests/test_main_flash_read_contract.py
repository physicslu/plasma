from __future__ import annotations

from plasma_core.enums import Operation
from plasma_core.models import JobRequest
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


def _provider_with_flash_size(size: int) -> SharedImageMockEngineeringPPUProvider:
    provider = object.__new__(SharedImageMockEngineeringPPUProvider)
    provider.flash_size_bytes = size
    return provider


def test_mock_provider_overrides_legacy_read_range_with_complete_main_flash() -> None:
    provider = _provider_with_flash_size(4096)
    request = JobRequest(
        site_id=1,
        operation=Operation.READ,
        map_data={
            "sections": [
                {"name": "legacy", "address": 128, "length": 256},
            ]
        },
    )

    resolved = provider._resolve_main_flash_read(request)

    assert resolved.map_data == {
        "scope": "main_flash",
        "sections": [
            {"name": "main_flash", "address": 0, "length": 4096},
        ],
    }
    assert resolved.metadata["read_scope"] == "main_flash"
    assert resolved.metadata["read_size_bytes"] == 4096


def test_non_read_request_keeps_existing_memory_map() -> None:
    provider = _provider_with_flash_size(4096)
    request = JobRequest(site_id=1, operation=Operation.ERASE, map_data={"sentinel": True})

    assert provider._resolve_main_flash_read(request) is request

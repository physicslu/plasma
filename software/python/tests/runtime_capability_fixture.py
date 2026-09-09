from __future__ import annotations

import json
from pathlib import Path

from plasma_core.ic_support import ICSupportResolver, ResolvedICSupport, ResolvedProfile


PROGRAMMING_PROFILE_ID = "stm32f1-medium-density-flash-v0"
C8_GEOMETRY_ID = "stm32f103c8-64k-v0"
CB_GEOMETRY_ID = "stm32f103cb-128k-v0"
PACKAGE_PROFILE_ID = "stm32f103-lqfp48-debug-v0"
OPTION_PROFILE_ID = "stm32f1-option-bytes-v0"
SECURITY_PROFILE_ID = "stm32f1-medium-density-security-v0"
BINDING_SET_ID = "software-test-runtime-capability-v0"


def _profile(profile_id: str, kind: str, data: dict[str, object]) -> ResolvedProfile:
    return ResolvedProfile(
        profile_id=profile_id,
        kind=kind,
        status="test_fixture",
        scope={"fixture": True},
        data=dict(data),
        evidence=({"source_id": "software-test-fixture"},),
    )


def build_test_resolver() -> ICSupportResolver:
    programming = _profile(
        PROGRAMMING_PROFILE_ID,
        "programming",
        {"program_granularity_bytes": 2},
    )
    c8_geometry = _profile(
        C8_GEOMETRY_ID,
        "memory_geometry",
        {
            "main_flash_start": "0x08000000",
            "main_flash_size_bytes": 64 * 1024,
            "main_flash_end": "0x0800FFFF",
            "page_size_bytes": 1024,
            "page_count": 64,
            "erase_granularity_bytes": 1024,
            "program_granularity_bytes": 2,
        },
    )
    cb_geometry = _profile(
        CB_GEOMETRY_ID,
        "memory_geometry",
        {
            "main_flash_start": "0x08000000",
            "main_flash_size_bytes": 128 * 1024,
            "main_flash_end": "0x0801FFFF",
            "page_size_bytes": 1024,
            "page_count": 128,
            "erase_granularity_bytes": 1024,
            "program_granularity_bytes": 2,
        },
    )
    package = _profile(PACKAGE_PROFILE_ID, "package_hardware", {"package": "LQFP48"})
    option = _profile(OPTION_PROFILE_ID, "option", {"implemented": False})
    security = _profile(SECURITY_PROFILE_ID, "security", {"implemented": False})

    def record(icpn: str, base_device: str, flash_size: str, geometry: ResolvedProfile) -> ResolvedICSupport:
        return ResolvedICSupport(
            icpn=icpn,
            binding_set_id=BINDING_SET_ID,
            binding_status="test_fixture",
            expected_catalog={
                "manufacturer": "STMicroelectronics",
                "base_device": base_device,
                "package": "LQFP",
                "pin_count": 48,
                "flash_size": flash_size,
                "openocd_target_config": "tcl/target/stm32f1x.cfg",
            },
            profiles={
                "programming": programming,
                "memory_geometry": geometry,
                "package_hardware": package,
                "option": option,
                "security": security,
            },
            revision_overrides=(),
        )

    records = {
        "stm32f103c8t6": record("STM32F103C8T6", "STM32F103C8", "64 KiB", c8_geometry),
        "stm32f103cbt6": record("STM32F103CBT6", "STM32F103CB", "128 KiB", cb_geometry),
    }
    return ICSupportResolver(records, root=Path("<software-test-fixture>"))


def materialize_test_root(root: Path) -> Path:
    """Create a self-contained SW-owned fixture for loader integrity tests."""
    profiles = {
        "programming": {
            PROGRAMMING_PROFILE_ID: ("programming", {"program_granularity_bytes": 2}),
        },
        "memory-geometry": {
            C8_GEOMETRY_ID: (
                "memory_geometry",
                {
                    "main_flash_start": "0x08000000",
                    "main_flash_size_bytes": 64 * 1024,
                    "main_flash_end": "0x0800FFFF",
                    "page_size_bytes": 1024,
                    "page_count": 64,
                    "erase_granularity_bytes": 1024,
                    "program_granularity_bytes": 2,
                },
            ),
            CB_GEOMETRY_ID: (
                "memory_geometry",
                {
                    "main_flash_start": "0x08000000",
                    "main_flash_size_bytes": 128 * 1024,
                    "main_flash_end": "0x0801FFFF",
                    "page_size_bytes": 1024,
                    "page_count": 128,
                    "erase_granularity_bytes": 1024,
                    "program_granularity_bytes": 2,
                },
            ),
        },
        "package-hardware": {PACKAGE_PROFILE_ID: ("package_hardware", {"package": "LQFP48"})},
        "option": {OPTION_PROFILE_ID: ("option", {"implemented": False})},
        "security": {SECURITY_PROFILE_ID: ("security", {"implemented": False})},
    }
    profiles_root = root / "profiles"
    for dirname, items in profiles.items():
        directory = profiles_root / dirname
        directory.mkdir(parents=True, exist_ok=True)
        for profile_id, (kind, data) in items.items():
            (directory / f"{profile_id}.json").write_text(
                json.dumps(
                    {
                        "profile_id": profile_id,
                        "kind": kind,
                        "status": "test_fixture",
                        "scope": {"fixture": True},
                        "data": data,
                        "evidence": [{"source_id": "software-test-fixture"}],
                    }
                ),
                encoding="utf-8",
            )

    bindings_root = root / "bindings"
    bindings_root.mkdir(parents=True, exist_ok=True)
    bindings = []
    for icpn, base_device, flash_size, geometry_id in (
        ("STM32F103C8T6", "STM32F103C8", "64 KiB", C8_GEOMETRY_ID),
        ("STM32F103CBT6", "STM32F103CB", "128 KiB", CB_GEOMETRY_ID),
    ):
        bindings.append(
            {
                "icpn": icpn,
                "expected_catalog": {
                    "manufacturer": "STMicroelectronics",
                    "base_device": base_device,
                    "package": "LQFP",
                    "pin_count": 48,
                    "flash_size": flash_size,
                    "openocd_target_config": "tcl/target/stm32f1x.cfg",
                },
                "profiles": {
                    "programming": PROGRAMMING_PROFILE_ID,
                    "memory_geometry": geometry_id,
                    "package_hardware": PACKAGE_PROFILE_ID,
                    "option": OPTION_PROFILE_ID,
                    "security": SECURITY_PROFILE_ID,
                },
                "revision_overrides": [],
            }
        )
    (bindings_root / "software-test-runtime-capability-v0.json").write_text(
        json.dumps(
            {
                "binding_set_id": BINDING_SET_ID,
                "status": "test_fixture",
                "bindings": bindings,
            }
        ),
        encoding="utf-8",
    )
    return root

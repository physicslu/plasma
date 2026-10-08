from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32f7_publication_preserves_legacy_route_and_adds_unbound_layer1_rows() -> None:
    catalog = get_default_device_catalog()

    legacy = catalog.search("STM32F722ICK6", limit=1)[0]
    assert legacy.identifier == "STM32F722ICK6"
    assert legacy.family == "STM32F7"
    assert legacy.mapping_status == "mapped"
    assert legacy.mapping_method == "deterministic_ordering_pattern"
    assert legacy.target_config == "tcl/target/stm32f7x.cfg"
    assert legacy.production_admitted is True

    added = catalog.search("STM32F723ZCI6", limit=1)[0]
    assert added.identifier == "STM32F723ZCI6"
    assert added.family == "STM32F7"
    assert added.package == "UFBGA"
    assert added.pin_count == "144"
    assert added.flash_size == "256 KiB"
    assert added.mapping_status == "mapped"
    assert added.mapping_method == "deterministic_ordering_pattern"
    assert added.target_config == "tcl/target/stm32f7x.cfg"
    assert added.production_admitted is True

    payload = added.to_payload()
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["backend"]["mapping_status"] == "no_mapping"
    assert payload["backend"]["target_config"] == ""
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_stm32f7_package_specific_metadata_and_f750_override() -> None:
    catalog = get_default_device_catalog()

    wlcsp143 = catalog.search("STM32F746ZEY6TR", limit=1)[0]
    assert wlcsp143.package == "WLCSP"
    assert wlcsp143.pin_count == "143"
    assert wlcsp143.option_suffix == "TR"
    assert wlcsp143.mapping_status == "no_mapping"

    ufbga176 = catalog.search("STM32F765IIK6", limit=1)[0]
    assert ufbga176.package == "UFBGA"
    assert ufbga176.pin_count == "176"
    assert ufbga176.flash_size == "2048 KiB"
    assert ufbga176.mapping_status == "no_mapping"

    override = catalog.search("STM32F750V8T7", limit=1)[0]
    assert override.base_device == "STM32F750V8"
    assert override.package == "LQFP"
    assert override.pin_count == "100"
    assert override.flash_size == "64 KiB"
    assert override.temperature_grade == "-40 to 105 C"
    assert override.mapping_status == "no_mapping"

from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32f2_publication_preserves_legacy_route_and_adds_unbound_layer1_rows() -> None:
    catalog = get_default_device_catalog()

    legacy = catalog.search("STM32F205RBT6", limit=1)[0]
    assert legacy.identifier == "STM32F205RBT6"
    assert legacy.family == "STM32F2"
    assert legacy.mapping_status == "mapped"
    assert legacy.mapping_method == "deterministic_ordering_pattern"
    assert legacy.target_config == "tcl/target/stm32f2x.cfg"
    assert legacy.production_admitted is True

    added = catalog.search("STM32F207ZGT7", limit=1)[0]
    assert added.identifier == "STM32F207ZGT7"
    assert added.family == "STM32F2"
    assert added.package == "LQFP"
    assert added.pin_count == "144"
    assert added.flash_size == "1024 KiB"
    assert added.temperature_grade == "-40 to 105 C"
    assert added.mapping_status == "mapped"
    assert added.mapping_method == "deterministic_ordering_pattern"
    assert added.target_config == "tcl/target/stm32f2x.cfg"
    assert added.production_admitted is True

    payload = added.to_payload()
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["backend"]["mapping_status"] == "mapped"
    assert payload["backend"]["target_config"] == "tcl/target/stm32f2x.cfg"
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_stm32f2_package_specific_metadata_and_tr_identity() -> None:
    catalog = get_default_device_catalog()

    wlcsp66 = catalog.search("STM32F205RGY6TR", limit=1)[0]
    assert wlcsp66.package == "WLCSP"
    assert wlcsp66.pin_count == "66"
    assert wlcsp66.flash_size == "1024 KiB"
    assert wlcsp66.option_suffix == "TR"
    assert wlcsp66.mapping_status == "mapped"
    assert wlcsp66.mapping_method == "deterministic_ordering_pattern"
    assert wlcsp66.target_config == "tcl/target/stm32f2x.cfg"

    ufbga176 = catalog.search("STM32F207IGH7", limit=1)[0]
    assert ufbga176.package == "UFBGA"
    assert ufbga176.pin_count == "176"
    assert ufbga176.flash_size == "1024 KiB"
    assert ufbga176.mapping_status == "mapped"
    assert ufbga176.mapping_method == "deterministic_ordering_pattern"
    assert ufbga176.target_config == "tcl/target/stm32f2x.cfg"

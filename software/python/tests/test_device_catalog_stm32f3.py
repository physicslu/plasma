from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32f3_publication_preserves_legacy_route_and_adds_unbound_layer1_rows() -> None:
    catalog = get_default_device_catalog()

    legacy = catalog.search("STM32F301C6T6", limit=1)[0]
    assert legacy.identifier == "STM32F301C6T6"
    assert legacy.family == "STM32F3"
    assert legacy.mapping_status == "deterministic_ordering_pattern"
    assert legacy.target_config == "tcl/target/stm32f3x.cfg"
    assert legacy.production_admitted is True

    added = catalog.search("STM32F302VDH6", limit=1)[0]
    assert added.identifier == "STM32F302VDH6"
    assert added.family == "STM32F3"
    assert added.package == "UFBGA"
    assert added.pin_count == "100"
    assert added.flash_size == "384 KiB"
    assert added.mapping_status == "no_mapping"
    assert added.mapping_method == "no_mapping"
    assert added.target_config == ""
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


def test_stm32f3_package_specific_metadata_and_tr_identity() -> None:
    catalog = get_default_device_catalog()

    wlcsp49 = catalog.search("STM32F301C8Y6TR", limit=1)[0]
    assert wlcsp49.package == "WLCSP"
    assert wlcsp49.pin_count == "49"
    assert wlcsp49.option_suffix == "TR"
    assert wlcsp49.mapping_status == "no_mapping"

    wlcsp66 = catalog.search("STM32F378RCY6TR", limit=1)[0]
    assert wlcsp66.package == "WLCSP"
    assert wlcsp66.pin_count == "66"
    assert wlcsp66.option_suffix == "TR"
    assert wlcsp66.mapping_status == "no_mapping"

    f398 = catalog.search("STM32F398VET6", limit=1)[0]
    assert f398.base_device == "STM32F398VE"
    assert f398.flash_size == "512 KiB"
    assert f398.mapping_status == "no_mapping"

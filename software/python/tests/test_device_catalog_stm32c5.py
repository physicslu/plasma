from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32c5_publication_is_catalog_only_and_unbound() -> None:
    catalog = get_default_device_catalog()

    c531 = catalog.search("STM32C531CBT6", limit=1)[0]
    assert c531.identifier == "STM32C531CBT6"
    assert c531.family == "STM32C5"
    assert c531.base_device == "STM32C531CB"
    assert c531.package == "LQFP"
    assert c531.pin_count == "48"
    assert c531.flash_size == "128 KiB"
    assert c531.mapping_status == "no_mapping"
    assert c531.mapping_method == "no_mapping"
    assert c531.target_config == ""
    assert c531.production_admitted is True

    payload = c531.to_payload()
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["backend"]["mapping_status"] == "no_mapping"
    assert payload["backend"]["target_config"] == ""
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_stm32c5_metadata_and_exact_temperature_exception() -> None:
    catalog = get_default_device_catalog()

    c5a3 = catalog.search("STM32C5A3KGU3TR", limit=1)[0]
    assert c5a3.package == "UFQFPN"
    assert c5a3.pin_count == "32"
    assert c5a3.flash_size == "1024 KiB"
    assert c5a3.temperature_grade == "-40 to 125 C"
    assert c5a3.option_suffix == "TR"
    assert c5a3.mapping_status == "no_mapping"

    temp7 = catalog.search("STM32C551CCT7", limit=1)[0]
    assert temp7.package == "LQFP"
    assert temp7.pin_count == "48"
    assert temp7.flash_size == "256 KiB"
    assert temp7.temperature_grade == "-40 to 105 C"
    assert temp7.mapping_status == "no_mapping"

    temp7_tr = catalog.search("STM32C551CCT7TR", limit=1)[0]
    assert temp7_tr.temperature_grade == "-40 to 105 C"
    assert temp7_tr.option_suffix == "TR"
    assert temp7_tr.mapping_status == "no_mapping"

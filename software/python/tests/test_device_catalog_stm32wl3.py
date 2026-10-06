from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32wl3_publication_is_catalog_only_and_unbound() -> None:
    catalog = get_default_device_catalog()

    wl30 = catalog.search("STM32WL30K8V6", limit=1)[0]
    assert wl30.identifier == "STM32WL30K8V6"
    assert wl30.family == "STM32WL3"
    assert wl30.base_device == "STM32WL30K8"
    assert wl30.package == "VFQFPN"
    assert wl30.pin_count == "32"
    assert wl30.flash_size == "64 KiB"
    assert wl30.mapping_status == "no_mapping"
    assert wl30.mapping_method == "no_mapping"
    assert wl30.target_config == ""
    assert wl30.production_admitted is True

    payload = wl30.to_payload()
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["backend"]["mapping_status"] == "no_mapping"
    assert payload["backend"]["target_config"] == ""
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_stm32wl3_metadata_frequency_options_and_pin_exception() -> None:
    catalog = get_default_device_catalog()

    wl33 = catalog.search("STM32WL33CCV7ATR", limit=1)[0]
    assert wl33.package == "VFQFPN"
    assert wl33.pin_count == "48"
    assert wl33.flash_size == "256 KiB"
    assert wl33.temperature_grade == "-40 to 105 C"
    assert wl33.option_suffix == "ATR"
    assert wl33.mapping_status == "no_mapping"

    wl3r = catalog.search("STM32WL3RKBV6X", limit=1)[0]
    assert wl3r.pin_count == "32"
    assert wl3r.flash_size == "128 KiB"
    assert wl3r.option_suffix == "X"
    assert wl3r.mapping_status == "no_mapping"

    exception = catalog.search("STM32WL31C8V6", limit=1)[0]
    assert exception.pin_count == "48"
    assert exception.package == "VFQFPN"
    assert exception.flash_size == "64 KiB"
    assert exception.mapping_status == "no_mapping"

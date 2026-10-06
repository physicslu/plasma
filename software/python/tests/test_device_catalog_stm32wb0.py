from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32wb0_publication_is_catalog_only_and_unbound() -> None:
    catalog = get_default_device_catalog()

    network = catalog.search("STM32WB05KNV6TR", limit=1)[0]
    assert network.identifier == "STM32WB05KNV6TR"
    assert network.family == "STM32WB0"
    assert network.base_device == "STM32WB05KN"
    assert network.package == "VFQFPN"
    assert network.pin_count == "32"
    assert network.flash_size == "N/A (network coprocessor)"
    assert network.temperature_grade == "-40 to 85 C"
    assert network.option_suffix == "TR"
    assert network.mapping_status == "no_mapping"
    assert network.mapping_method == "no_mapping"
    assert network.target_config == ""
    assert network.production_admitted is True

    payload = network.to_payload()
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["backend"]["mapping_status"] == "no_mapping"
    assert payload["backend"]["target_config"] == ""
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_stm32wb0_metadata_semantics_are_preserved() -> None:
    catalog = get_default_device_catalog()

    z = catalog.search("STM32WB05TZF7TR", limit=1)[0]
    assert z.package == "WLCSP"
    assert z.pin_count == "36"
    assert z.flash_size == "192 KiB"
    assert z.temperature_grade == "-40 to 105 C"
    assert z.mapping_status == "no_mapping"

    ccf = catalog.search("STM32WB06CCF6TR", limit=1)[0]
    assert ccf.package == "WLCSP"
    assert ccf.pin_count == "49"
    assert ccf.flash_size == "256 KiB"
    assert ccf.mapping_status == "no_mapping"

    ccv = catalog.search("STM32WB07CCV7TR", limit=1)[0]
    assert ccv.package == "VFQFPN"
    assert ccv.pin_count == "48"
    assert ccv.flash_size == "256 KiB"
    assert ccv.mapping_status == "no_mapping"

    e = catalog.search("STM32WB09TEF6TR", limit=1)[0]
    assert e.package == "WLCSP"
    assert e.pin_count == "36"
    assert e.flash_size == "512 KiB"
    assert e.mapping_status == "no_mapping"

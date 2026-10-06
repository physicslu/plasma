from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32n6_publication_is_catalog_only_and_unbound() -> None:
    catalog = get_default_device_catalog()

    n645 = catalog.search("STM32N645A0H3Q", limit=1)[0]
    assert n645.identifier == "STM32N645A0H3Q"
    assert n645.family == "STM32N6"
    assert n645.base_device == "STM32N645A0"
    assert n645.package == "VFBGA"
    assert n645.pin_count == "169"
    assert n645.flash_size == "0-1 KiB"
    assert n645.temperature_grade == "-40 to 125 C"
    assert n645.option_suffix == "Q"
    assert n645.mapping_status == "no_mapping"
    assert n645.mapping_method == "no_mapping"
    assert n645.target_config == ""
    assert n645.production_admitted is True

    payload = n645.to_payload()
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["backend"]["mapping_status"] == "no_mapping"
    assert payload["backend"]["target_config"] == ""
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_stm32n6_ordering_metadata_and_external_memory_boundary() -> None:
    catalog = get_default_device_catalog()

    qg = catalog.search("STM32N657A0H3QG", limit=1)[0]
    assert qg.package == "VFBGA"
    assert qg.pin_count == "169"
    assert qg.flash_size == "0-1 KiB"
    assert qg.temperature_grade == "-40 to 125 C"
    assert qg.option_suffix == "QG"
    assert qg.mapping_status == "no_mapping"
    assert qg.target_config == ""

    tr = catalog.search("STM32N657I0H3QTR", limit=1)[0]
    assert tr.pin_count == "178"
    assert tr.option_suffix == "QTR"
    assert tr.mapping_status == "no_mapping"
    assert tr.target_config == ""

    x = catalog.search("STM32N657X0H3Q", limit=1)[0]
    assert x.pin_count == "264"
    assert x.flash_size == "0-1 KiB"
    assert x.mapping_status == "no_mapping"

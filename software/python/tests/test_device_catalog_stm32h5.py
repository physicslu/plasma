from __future__ import annotations

from plasma_web.device_catalog import get_default_device_catalog


def test_stm32h5_layer1_publication_is_visible_without_backend_route() -> None:
    catalog = get_default_device_catalog()

    h503 = catalog.search("STM32H503CBT6", limit=1)[0]
    assert h503.identifier == "STM32H503CBT6"
    assert h503.family == "STM32H5"
    assert h503.package == "LQFP"
    assert h503.pin_count == "48"
    assert h503.flash_size == "128 KiB"
    assert h503.mapping_status == "no_mapping"
    assert h503.mapping_method == "no_mapping"
    assert h503.target_config == ""
    assert h503.production_admitted is True

    exception = catalog.search("STM32H5E4ZJJ6", limit=1)[0]
    assert exception.identifier == "STM32H5E4ZJJ6"
    assert exception.family == "STM32H5"
    assert exception.package == "UFBGA 144 10x10x0.6 P 0.8 mm"
    assert exception.mapping_status == "no_mapping"
    assert exception.target_config == ""

    smps = catalog.search("STM32H5E4ZJJ7Q", limit=1)[0]
    assert smps.identifier == "STM32H5E4ZJJ7Q"
    assert smps.option_suffix == "Q"
    assert smps.mapping_status == "no_mapping"

    payload = smps.to_payload()
    assert payload["catalog"]["scope"] == "production_admitted"
    assert payload["backend"]["mapping_status"] == "no_mapping"
    assert payload["backend"]["target_config"] == ""
    assert payload["physical_validation"] == {
        "engineering_status": "no_evidence",
        "ppu_status": "no_evidence",
        "socket_status": "no_evidence",
    }


def test_stm32h5_tr_identity_remains_exact_and_unmapped() -> None:
    record = get_default_device_catalog().search("STM32H503CBT7TR", limit=1)[0]
    assert record.identifier == "STM32H503CBT7TR"
    assert record.option_suffix == "TR"
    assert record.base_device == "STM32H503CB"
    assert record.mapping_status == "no_mapping"
    assert record.target_config == ""

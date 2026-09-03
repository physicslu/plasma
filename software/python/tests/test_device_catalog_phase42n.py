from plasma_web.device_catalog import get_default_device_catalog

def test_phase42n_runtime_exact_icpn():
    catalog=get_default_device_catalog(); assert catalog.size==340
    row=catalog.search('stm32f479iih7tr',limit=5)[0]
    assert row.icpn=='STM32F479IIH7TR' and row.package=='UFBGA' and row.pin_count=='176'
    assert row.flash_size=='2048 KiB' and row.target_config=='tcl/target/stm32f4x.cfg' and row.production_admitted

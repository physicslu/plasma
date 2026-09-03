from __future__ import annotations
import json, threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import PlasmaWebHandler
EXPECTED_MIN_PRODUCTION_CATALOG_SIZE=379
UFBGA_ICPN='STM32F412VEH3TR'; LQFP_ICPN='STM32F413VGT6TR'
def test_phase42q_exact_icpns_are_resolved_by_runtime_catalog() -> None:
    catalog=get_default_device_catalog(); assert catalog.size>=EXPECTED_MIN_PRODUCTION_CATALOG_SIZE
    for icpn,package,flash_size in ((UFBGA_ICPN,'UFBGA','512 KiB'),(LQFP_ICPN,'LQFP','1024 KiB')):
        matches=catalog.search(icpn.lower(),limit=5); assert {r.icpn for r in matches}=={icpn}
        row=matches[0]; assert row.package==package and row.pin_count=='100' and row.flash_size==flash_size and row.target_config=='tcl/target/stm32f4x.cfg' and row.production_admitted
def test_phase42q_exact_icpn_is_exposed_by_rest_catalog() -> None:
    server=ThreadingHTTPServer(('127.0.0.1',0),PlasmaWebHandler); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        connection=HTTPConnection('127.0.0.1',server.server_port); connection.request('GET',f'/api/devices/search?q={UFBGA_ICPN}&limit=5'); response=connection.getresponse(); payload=json.loads(response.read()); connection.close()
        assert response.status==200 and payload['rest_contract_version']=='3' and payload['catalog_size']>=EXPECTED_MIN_PRODUCTION_CATALOG_SIZE and payload['count']==1
        result=payload['results'][0]; assert result['icpn']==UFBGA_ICPN and result['package']=='UFBGA' and result['pin_count']=='100' and result['flash_size']=='512 KiB' and result['backend']['target_config']=='tcl/target/stm32f4x.cfg' and result['catalog']['scope']=='production_admitted'
    finally:
        server.shutdown(); server.server_close(); thread.join()

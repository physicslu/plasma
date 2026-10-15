"""Synthetic handoff fault injection; no hardware or Vivado claim."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

PL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('loopback_artifact', PL/'projects/z2-control-waveform/artifact.py')
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


def handoff():
    root = ET.Element('SYSTEM')
    for instance, base in artifact.MAP.items():
        module = ET.SubElement(root, 'MODULE', INSTANCE=instance)
        ET.SubElement(module, 'PARAMETER', NAME='AXI_BASE_ADDRESS', VALUE=hex(base))
        if instance == 'identity_0':
            for name, value in [('CAPABILITY_FLAGS','0'),('STRICT_ADDRESS','1')]:
                ET.SubElement(module, 'PARAMETER', NAME=name, VALUE=value)
        for name, signal in [('s_axi_aclk','ps7_0_FCLK_CLK0'),('s_axi_aresetn','rst_ps7_0_100M_peripheral_aresetn')]:
            ET.SubElement(module,'PORT',NAME=name,SIGNAME=signal)
        ET.SubElement(root,'MEMRANGE',INSTANCE=instance,BASEVALUE=hex(base),HIGHVALUE=hex(base+4095),MASTERBUSINTERFACE='M_AXI_GP0')
    ps = ET.SubElement(root,'MODULE',INSTANCE='ps7_0')
    for name, value in [('PCW_GPIO_EMIO_GPIO_ENABLE','0'),('PCW_USE_M_AXI_GP0','1'),('PCW_CRYSTAL_PERIPHERAL_FREQMHZ','50'),('PCW_FPGA0_PERIPHERAL_FREQMHZ','100')]:
        ET.SubElement(ps,'PARAMETER',NAME=name,VALUE=value)
    ET.SubElement(ps,'PORT',NAME='M_AXI_GP0_ACLK',CLKFREQUENCY='100000000',SIGNAME='ps7_0_FCLK_CLK0')
    reset = ET.SubElement(root,'MODULE',INSTANCE='rst_ps7_0_100M')
    ET.SubElement(reset,'PARAMETER',NAME='C_EXT_RESET_HIGH',VALUE='0')
    ET.SubElement(reset,'PORT',NAME='ext_reset_in',SIGNAME='ps7_0_FCLK_RESET0_N')
    return root


def test_valid_handoff(tmp_path):
    path = tmp_path/'system.hwh'
    ET.ElementTree(handoff()).write(path)
    assert set(artifact.verify_hwh(path)) == set(artifact.MAP)


@pytest.mark.parametrize('fault', ['decode','range','master','duplicate','flags','clock','reset','emio','external'])
def test_reject_inconsistent_handoff(tmp_path, fault):
    root = handoff()
    if fault == 'decode': root.find("./MODULE[@INSTANCE='swd_0']/PARAMETER").set('VALUE','0x40001000')
    elif fault == 'range': root.find("./MEMRANGE[@INSTANCE='control_0']").set('HIGHVALUE','0x7FFFFFFF')
    elif fault == 'master': root.find('./MEMRANGE').set('MASTERBUSINTERFACE','M_AXI_GP1')
    elif fault == 'duplicate': ET.SubElement(root,'MEMRANGE',INSTANCE='swd_0')
    elif fault == 'flags': root.find(".//PARAMETER[@NAME='CAPABILITY_FLAGS']").set('VALUE','1')
    elif fault == 'clock': root.find(".//PORT[@NAME='M_AXI_GP0_ACLK']").set('CLKFREQUENCY','10000000')
    elif fault == 'reset': root.find(".//PORT[@NAME='ext_reset_in']").set('SIGNAME','wrong_reset')
    elif fault == 'emio': root.find(".//PARAMETER[@NAME='PCW_GPIO_EMIO_GPIO_ENABLE']").set('VALUE','1')
    elif fault == 'external': ET.SubElement(ET.SubElement(root,'EXTERNALPORTS'),'PORT',NAME='SWDIO')
    path = tmp_path/'system.hwh'
    ET.ElementTree(root).write(path)
    with pytest.raises(ValueError): artifact.verify_hwh(path)

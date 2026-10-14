"""Fail-closed artifact validation, using fabricated HWH (no hardware claim)."""
import importlib.util
from pathlib import Path
import pytest

PL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("identity_artifact", PL / "projects/z2-identity/artifact.py")
artifact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifact)


def hwh():
    return '''<SYSTEM><MODULE INSTANCE="identity_0"><PARAMETERS>
<PARAMETER NAME="CAPABILITY_FLAGS" VALUE="0"/>
<PARAMETER NAME="STRICT_ADDRESS" VALUE="1"/>
<PARAMETER NAME="AXI_BASE_ADDRESS" VALUE="0x40000000"/>
</PARAMETERS></MODULE><MODULE INSTANCE="ps7_0"><PARAMETERS>
<PARAMETER NAME="PCW_GPIO_EMIO_GPIO_ENABLE" VALUE="0"/>
<PARAMETER NAME="PCW_USE_M_AXI_GP0" VALUE="1"/>
<PARAMETER NAME="PCW_CRYSTAL_PERIPHERAL_FREQMHZ" VALUE="50"/>
<PARAMETER NAME="PCW_M_AXI_GP0_FREQMHZ" VALUE="100"/>
<PARAMETER NAME="PCW_FPGA0_PERIPHERAL_FREQMHZ" VALUE="100"/>
</PARAMETERS></MODULE><MEMRANGE INSTANCE="identity_0" BASEVALUE="0x40000000" HIGHVALUE="0x40000FFF"/></SYSTEM>'''


def test_hwh_identity_only_contract(tmp_path):
    path = tmp_path / "system.hwh"
    path.write_text(hwh())
    artifact.verify_hwh(path, 0x40000000)


@pytest.mark.parametrize("old,new", [
    ('NAME="CAPABILITY_FLAGS" VALUE="0"', 'NAME="CAPABILITY_FLAGS" VALUE="1"'),
    ('NAME="STRICT_ADDRESS" VALUE="1"', 'NAME="STRICT_ADDRESS" VALUE="0"'),
    ('HIGHVALUE="0x40000FFF"', 'HIGHVALUE="0x7FFFFFFF"'),
    ('NAME="PCW_GPIO_EMIO_GPIO_ENABLE" VALUE="0"', 'NAME="PCW_GPIO_EMIO_GPIO_ENABLE" VALUE="1"'),
    ('NAME="PCW_FPGA0_PERIPHERAL_FREQMHZ" VALUE="100"', 'NAME="PCW_FPGA0_PERIPHERAL_FREQMHZ" VALUE="50"'),
    ('</SYSTEM>', '<MODULE INSTANCE="swd_emio_0"/></SYSTEM>'),
])
def test_hwh_rejects_unsafe_or_inconsistent_handoff(tmp_path, old, new):
    path = tmp_path / "system.hwh"
    path.write_text(hwh().replace(old, new))
    with pytest.raises(ValueError):
        artifact.verify_hwh(path, 0x40000000)

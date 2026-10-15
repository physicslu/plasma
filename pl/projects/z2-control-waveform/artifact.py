#!/usr/bin/env python3
"""Host-only PL loopback baseline metadata; never programs FPGA or runs PS7 init."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

PL = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('identity_metadata', PL / 'projects/z2-swd-gpio/artifact.py')
assert spec and spec.loader
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
MAP = {'identity_0': 0x40000000, 'control_0': 0x40001000, 'swd_0': 0x40002000}


def prepare(build: Path, version: str) -> None:
    shared.prepare(build / 'generated', version)
    path = build / 'generated/build-identity.json'
    metadata = json.loads(path.read_text())
    metadata.update(design_variant='control_waveform_loopback',
                    capabilities=['axi_control_loopback', 'swd_waveform_digital', 'internal_pattern_responder'],
                    capability_flags=0, external_pl_io=False,
                    swd_command_abi_version=1, loopback_responder_modes=['tx_echo_or_pull_high', 'independent_rx_pattern'])
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n')


def number(value: str) -> int:
    # Vivado emits logic-vector module parameters as 32 binary digits.
    if len(value) == 32 and set(value) <= {'0', '1'}:
        return int(value, 2)
    return int(value, 0)


def verify_hwh(path: Path) -> dict:
    root = ET.parse(path).getroot()
    modules = {m.get('INSTANCE'): m for m in root.iter('MODULE')}
    result = {}
    for instance, base in MAP.items():
        module = modules[instance]
        params = {p.get('NAME'): p.get('VALUE') for p in module.iter('PARAMETER')}
        if number(params['AXI_BASE_ADDRESS']) != base:
            raise ValueError('RTL decoder base differs from assigned segment: ' + instance)
        if instance == 'identity_0' and (number(params['CAPABILITY_FLAGS']) != 0 or number(params['STRICT_ADDRESS']) != 1):
            raise ValueError('Identity ABI/strict flags mismatch')
        ranges = [m for m in root.iter('MEMRANGE') if m.get('INSTANCE') == instance]
        if len(ranges) != 1:
            raise ValueError('Ambiguous address range: ' + instance)
        segment = ranges[0]
        if number(segment.get('BASEVALUE')) != base or number(segment.get('HIGHVALUE')) != base + 4095:
            raise ValueError('Expected disjoint 4 KiB segment: ' + instance)
        if segment.get('MASTERBUSINTERFACE') != 'M_AXI_GP0':
            raise ValueError('Unexpected AXI master: ' + instance)
        result[instance] = {'base_address': f'0x{base:08X}', 'segment_size_bytes': 4096}
        ports = {p.get('NAME'): p for p in module.iter('PORT')}
        if ports['s_axi_aclk'].get('SIGNAME') != 'ps7_0_FCLK_CLK0':
            raise ValueError('Peripheral not on FCLK0: ' + instance)
        if ports['s_axi_aresetn'].get('SIGNAME') != 'rst_ps7_0_100M_peripheral_aresetn':
            raise ValueError('Peripheral reset mismatch: ' + instance)
    ps = {p.get('NAME'): p.get('VALUE') for p in modules['ps7_0'].iter('PARAMETER')}
    for key, expected in {'PCW_GPIO_EMIO_GPIO_ENABLE': 0, 'PCW_USE_M_AXI_GP0': 1,
                          'PCW_CRYSTAL_PERIPHERAL_FREQMHZ': 50, 'PCW_FPGA0_PERIPHERAL_FREQMHZ': 100}.items():
        actual = ps[key].lower()
        actual = int(actual == 'true') if actual in {'true', 'false'} else float(actual)
        if actual != expected:
            raise ValueError('PS7 preset mismatch: ' + key)
    psports = {p.get('NAME'): p for p in modules['ps7_0'].iter('PORT')}
    if psports['M_AXI_GP0_ACLK'].get('CLKFREQUENCY') != '100000000' or psports['M_AXI_GP0_ACLK'].get('SIGNAME') != 'ps7_0_FCLK_CLK0':
        raise ValueError('GP0 must use actual 100 MHz FCLK0 connection')
    reset = {p.get('NAME'): p.get('VALUE') for p in modules['rst_ps7_0_100M'].iter('PARAMETER')}
    if number(reset['C_EXT_RESET_HIGH']) != 0:
        raise ValueError('Expected active-low PS FCLK reset')
    resetports = {p.get('NAME'): p for p in modules['rst_ps7_0_100M'].iter('PORT')}
    if resetports['ext_reset_in'].get('SIGNAME') != 'ps7_0_FCLK_RESET0_N':
        raise ValueError('PS reset not connected to reset synchronizer')
    for port in root.findall('./EXTERNALPORTS/PORT'):
        if not port.get('NAME', '').startswith(('DDR_', 'FIXED_IO_')):
            raise ValueError('External PL port forbidden: ' + port.get('NAME', ''))
    if any('swd_emio' in str(m.attrib).lower() for m in modules.values()):
        raise ValueError('External SWD bridge is forbidden')
    return result


def finalize(build: Path, version: str) -> None:
    metadata = json.loads((build / 'generated/build-identity.json').read_text())
    if metadata['source_git_sha'] != shared._commit():
        raise ValueError('Source changed since prepare')
    logs = build / 'logs'
    host = (logs / 'host-regression.log').read_text()
    if '3 passed' not in host or 'failed' in host.lower():
        raise ValueError('Mandatory three-runner host loopback gate did not pass')
    vivado = (logs / 'vivado-console.log').read_text()
    if 'BITSTREAM_BUILD_PASS\n' not in vivado or 'IMPLEMENTED_TIMING_PASS setup=' not in vivado:
        raise ValueError('Missing implemented Vivado/timing success evidence')
    # Critical warnings cannot be waived automatically to claim LB-HOST PASS.
    if 'CRITICAL WARNING:' in vivado or 'ERROR:' in vivado:
        raise ValueError('Vivado critical warnings/errors require resolution, not suppression')
    project = build / 'project'
    bit = project / 'z2_control_waveform.runs/impl_1/system_wrapper.bit'
    hwh = project / 'z2_control_waveform.gen/sources_1/bd/system/hw_handoff/system.hwh'
    metadata['axi_address_map'] = verify_hwh(hwh)
    exported = (build / 'generated/axi-address-map.txt').read_text().splitlines()
    if len(exported) != 3:
        raise ValueError('Incomplete Tcl address evidence')
    for line in exported:
        instance, base, size = line.split()
        if MAP[instance] != int(base, 0) or int(size, 0) != 4096:
            raise ValueError('Tcl and HWH address maps disagree')
    artifacts = build / 'artifacts'
    artifacts.mkdir()
    stem = f"plasma-z2-control-waveform-{metadata['bitstream_version']}"
    for key, source, suffix in [('bitstream', bit, 'bit'), ('hwh', hwh, 'hwh')]:
        target = artifacts / f'{stem}.{suffix}'
        shutil.copyfile(source, target)
        digest = shared._digest(target)
        metadata[key+'_file'], metadata[key+'_sha256'] = target.name, digest
        (artifacts / (target.name+'.sha256')).write_text(f'{digest}  {target.name}\n')
    evidence = {}
    for path in [logs/'host-regression.log', logs/'vivado-console.log', build/'reports/timing_summary.rpt', build/'reports/drc.rpt', build/'reports/methodology.rpt']:
        evidence[str(path.relative_to(build))] = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata.update(toolchain={'name':'Vivado','version':version},
                    acceptance={'LB-HOST':'PASS','LB-Z2':'NOT_RUN','real_swd_target':'NOT_RUN'},
                    evidence_sha256=evidence, loading_safety='NOT_QUALIFIED',
                    waveform_transfer_limit_bits=32, waveform_half_period_cycles=[2,65535],
                    physical_programming_qualified=False, hardware_runtime_ready=False,
                    baseline_retention='Preserve this entire uniquely named build directory; never overwrite a known-good baseline')
    (artifacts/'manifest.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
    print('LOOPBACK_ARTIFACT_PASS',artifacts)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','finalize'])
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--version',required=True)
    args=parser.parse_args()
    (prepare if args.command=='prepare' else finalize)(args.build,args.version)

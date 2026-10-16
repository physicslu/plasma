"""Targeted development guards; all fixtures are ordinary host files."""
import json
from pathlib import Path

import pytest

from pl.hil.swd04 import contract as c
from pl.hil.swd04 import development as d


def receipt():
    return dict(boot_id='boot', load_line='load',
                candidate_bin_sha256=c.CANDIDATE_BIN_SHA256,
                build_id=c.SOURCE_SHA[:32], axi_address_map=dict(c.AXI_BASES),
                abis={'identity': 1, 'waveform': 1, 'transaction': 1},
                external_pl_io=False)


def test_receipt_needs_no_manual_attestation():
    d.verify_receipt(receipt(), boot_id='boot', load_line='load')


@pytest.mark.parametrize('key,value', [
    ('boot_id', 'previous-boot'), ('load_line', 'previous-load'),
    ('candidate_bin_sha256', 'wrong'), ('build_id', 'wrong'),
    ('axi_address_map', {}), ('abis', {}), ('external_pl_io', True),
])
def test_stale_or_wrong_fixture_rejected(key, value):
    record = receipt(); record[key] = value
    with pytest.raises(c.SafetyError):
        d.verify_receipt(record, boot_id='boot', load_line='load')


def test_last_load_does_not_accept_older_candidate():
    log = '[1] fpga_manager fpga0: writing candidate.bin to manager\n'
    log += '[2] fpga_manager fpga0: writing base.bin to manager'
    assert d.last_load(log).startswith('[2]')
    with pytest.raises(c.SafetyError): d.last_load('')


@pytest.fixture
def trees(tmp_path):
    sys, proc = tmp_path/'sys', tmp_path/'proc'
    (sys/'bus/platform/devices').mkdir(parents=True)
    (proc/'123/fd').mkdir(parents=True)
    (proc/'123/maps').write_text('')
    return sys, proc


def test_targeted_fd_scan_ignores_unrelated_devices(trees):
    sys, proc = trees
    (proc/'123/fd/3').symlink_to('/dev/dri/card0')
    d.check_ownership(sys=sys, proc=proc)
    (proc/'123/fd/4').symlink_to('/dev/mem')
    with pytest.raises(c.SafetyError, match='device fd'):
        d.check_ownership(sys=sys, proc=proc)


@pytest.mark.parametrize('offset,reject', [('40001000', True), ('10000000', False)])
def test_retained_mapping_after_fd_closed(trees, offset, reject):
    sys, proc = trees
    (proc/'123/maps').write_text(f'1000-2000 rw-s {offset} 00:01 1 /dev/mem\n')
    if reject:
        with pytest.raises(c.SafetyError, match='retained'):
            d.check_ownership(sys=sys, proc=proc)
    else:
        d.check_ownership(sys=sys, proc=proc)


def test_overlapping_kernel_resource_not_just_device_name(trees):
    sys, proc = trees
    device = sys/'bus/platform/devices/custom'
    device.mkdir(); (device/'driver').mkdir()
    (device/'resource').write_text('0x3ffff000 0x40000fff 0x200\n')
    with pytest.raises(c.SafetyError, match='platform driver'):
        d.check_ownership(sys=sys, proc=proc)


def test_uio_mapping_conflict(trees):
    sys, proc = trees
    uio = sys/'class/uio/uio7'
    mapping = uio/'maps/map0'; mapping.mkdir(parents=True)
    (mapping/'addr').write_text('0x40003000')
    (mapping/'size').write_text('0x1000')
    (uio/'device/driver').mkdir(parents=True)
    with pytest.raises(c.SafetyError, match='UIO driver'):
        d.check_ownership(sys=sys, proc=proc)


def test_unbound_uio_retained_mapping_is_not_missed(trees):
    sys, proc = trees
    # Device disappeared from sysfs during unbind; retained maps still conflict.
    (proc/'123/maps').write_text('1000-2000 rw-s 00000000 00:01 1 /dev/uio0\n')
    with pytest.raises(c.SafetyError, match='retained'):
        d.check_ownership(sys=sys, proc=proc)


def test_no_root_means_no_live_inspection(monkeypatch, tmp_path):
    monkeypatch.setattr(d.os, 'geteuid', lambda: 1234)
    with pytest.raises(c.SafetyError, match='authorized root'):
        d.preflight(tmp_path/'missing-receipt', tmp_path/'missing-bin')
    with pytest.raises(c.SafetyError, match='authorized root'):
        d.record_loaded_image(tmp_path/'missing-bin', tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_inaccessible_mapping_audit_fails_closed(trees, monkeypatch):
    sys, proc = trees
    original = Path.read_text
    def read(path, *args, **kwargs):
        if path.name == 'maps': raise PermissionError('unreadable mapping audit')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    with pytest.raises(PermissionError): d.check_ownership(sys=sys, proc=proc)


def test_capture_real_loading_facts_and_reject_wrong_last_load(tmp_path, monkeypatch):
    from types import SimpleNamespace
    firmware = tmp_path/'candidate.bin'; firmware.write_bytes(b'verified-test-firmware')
    monkeypatch.setattr(c, 'CANDIDATE_BIN_SHA256', c.sha256_file(firmware))
    monkeypatch.setattr(d.os, 'geteuid', lambda: 0)
    original_stat, original_read = Path.stat, Path.read_text
    def stat(path, *args, **kwargs):
        if path in (firmware, tmp_path): return SimpleNamespace(st_uid=0, st_mode=0o100600)
        return original_stat(path, *args, **kwargs)
    def read(path, *args, **kwargs):
        if str(path) == '/sys/class/fpga_manager/fpga0/state': return 'operating\n'
        if str(path) == '/proc/sys/kernel/random/boot_id': return 'boot\n'
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat); monkeypatch.setattr(Path, 'read_text', read)
    line = '[123] fpga_manager fpga0: writing candidate.bin to Xilinx Zynq FPGA Manager'
    monkeypatch.setattr(d.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=line))
    output = tmp_path/'loaded.json'
    record = d.record_loaded_image(firmware, output)
    d.verify_receipt(record, boot_id='boot', load_line=line)
    assert json.loads(output.read_text()) == record
    with pytest.raises(FileExistsError): d.record_loaded_image(firmware, output)
    monkeypatch.setattr(d.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=line.replace('candidate.bin', 'base.bin')))
    with pytest.raises(c.SafetyError, match='Last FPGA Manager load'):
        d.record_loaded_image(firmware, tmp_path/'wrong.json')
    assert not (tmp_path/'wrong.json').exists()


def test_known_unrelated_uio_does_not_block_internal_fixture(trees):
    sys, proc = trees
    mapping = sys/'class/uio/uio7/maps/map0'; mapping.mkdir(parents=True)
    (mapping/'addr').write_text('0x43c00000'); (mapping/'size').write_text('0x10000')
    (proc/'123/fd/3').symlink_to('/dev/uio7')
    (proc/'123/maps').write_text('1000-2000 rw-s 00000000 00:01 1 /dev/uio7\n')
    d.check_ownership(sys=sys, proc=proc)

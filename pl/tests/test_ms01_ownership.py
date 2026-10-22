"""Synthetic sys/proc ownership fault injection. Never opens physical MMIO."""
from pathlib import Path
import os
import shutil

import pytest
from pl.hil.ms01 import native as ms
from pl.hil.lt02 import native as lt


@pytest.fixture
def trees(tmp_path):
    sys, proc = tmp_path / 'sys', tmp_path / 'proc'
    (sys / 'class/uio').mkdir(parents=True)
    (sys / 'bus/platform/devices').mkdir(parents=True)
    (proc / '123/fd').mkdir(parents=True)
    (proc / '123/maps').write_text('')
    return sys, proc


def guard(trees, **kw):
    ms.check_ownership(sysroot=trees[0], procroot=trees[1], **kw)


def mapping(trees, offset, size=4096, device='/dev/mem', virtual=0x10000000):
    (trees[1] / '123/maps').write_text(
        f'{virtual:x}-{virtual+size:x} rw-s {offset:08x} 00:01 1 {device}\n')


@pytest.mark.parametrize('offset', [0x40000000+i*4096 for i in range(6)])
def test_all_six_retained_maps_without_any_fd(trees, offset):
    mapping(trees, offset)
    with pytest.raises(lt.LT02SafetyError, match='retained'):
        guard(trees)


@pytest.mark.parametrize('offset,size,conflict', [
    (0x3ffff000,4096,False), (0x3ffff000,8192,True),
    (0x40006000,4096,False), (0x40005000,4096,True),
    (0x3ffff000,0x8000,True),
])
def test_actual_physical_offset_and_exclusive_boundaries(trees, offset, size, conflict):
    mapping(trees, offset, size, virtual=0x40005000)
    if conflict:
        with pytest.raises(lt.LT02SafetyError): guard(trees)
    else:
        guard(trees)


def test_existing_five_aperture_default_preserved(trees):
    mapping(trees,0x40005000)
    lt.check_ownership(sysroot=trees[0],procroot=trees[1])
    with pytest.raises(lt.LT02SafetyError): guard(trees)


def uio(trees, address, size='0x1000'):
    u=trees[0]/'class/uio/uio7';m=u/'maps/map0';m.mkdir(parents=True)
    (m/'addr').write_text(hex(address));(m/'size').write_text(size)
    return u


@pytest.mark.parametrize('address', [0x40004000,0x40005000])
def test_uio_retained_mapping_uses_sysfs_physical_address(trees,address):
    uio(trees,address);mapping(trees,0,device='/dev/uio7')
    with pytest.raises(lt.LT02SafetyError,match='retained'): guard(trees)


def test_proven_unrelated_uio_preserved_but_reload_requires_no_users(trees):
    uio(trees,0x43c00000);mapping(trees,0,device='/dev/uio7')
    guard(trees)
    with pytest.raises(lt.LT02SafetyError): guard(trees,full_reconfiguration=True)


@pytest.mark.parametrize('size', ['0','bad','-1'])
def test_unknown_or_malformed_uio_fails_closed(trees,size):
    uio(trees,0x40005000,size)
    with pytest.raises(lt.LT02SafetyError): guard(trees)


def test_missing_uio_inventory_does_not_mean_unowned(trees):
    (trees[0]/'class/uio/uio9').mkdir()
    with pytest.raises(lt.LT02SafetyError): guard(trees)


@pytest.mark.parametrize('device', ['/dev/mem (deleted)','/dev/uio99','/dev/uio99 (deleted)'])
def test_deleted_and_unknown_device_maps(trees,device):
    mapping(trees,0x40005000,device=device)
    with pytest.raises(lt.LT02SafetyError): guard(trees)


def test_close_race_does_not_skip_maps(trees,monkeypatch):
    fd=trees[1]/'123/fd/4';fd.symlink_to('/dev/mem');mapping(trees,0x40005000)
    original=os.readlink
    def close_race(path):
        if path==fd:
            fd.unlink();raise FileNotFoundError()
        return original(path)
    monkeypatch.setattr(os,'readlink',close_race)
    with pytest.raises(lt.LT02SafetyError,match='retained'): guard(trees)


def test_permission_denied_maps_fails_closed(trees,monkeypatch):
    original=Path.read_text;target=trees[1]/'123/maps'
    def denied(path,*a,**k):
        if path==target: raise PermissionError('injected proc denial')
        return original(path,*a,**k)
    monkeypatch.setattr(Path,'read_text',denied)
    with pytest.raises(lt.LT02SafetyError,match='Cannot establish'): guard(trees)


def test_missing_maps_only_ignorable_if_process_really_exited(trees):
    (trees[1]/'123/maps').unlink()
    with pytest.raises(lt.LT02SafetyError,match='incompletely'): guard(trees)
    shutil.rmtree(trees[1]/'123');guard(trees)


@pytest.mark.parametrize('row', ['garbage','1000-2000 rw-s nothex 00:01 1 /dev/mem',
                                 '2000-1000 rw-s 40005000 00:01 1 /dev/mem'])
def test_malformed_proc_maps_fails_closed(trees,row):
    (trees[1]/'123/maps').write_text(row+'\n')
    with pytest.raises(lt.LT02SafetyError): guard(trees)


def test_sixth_kernel_owner_without_resource_file(trees):
    (trees[0]/'bus/platform/devices/40005000.lt02/driver').mkdir(parents=True)
    with pytest.raises(lt.LT02SafetyError,match='kernel PL'): guard(trees)


def test_missing_sys_or_proc_inventory(trees):
    with pytest.raises(lt.LT02SafetyError):
        ms.check_ownership(sysroot=trees[0]/'missing',procroot=trees[1])


def test_broken_kernel_driver_link_fails_closed(trees):
    driver=trees[0]/'bus/platform/devices/40005000.lt02/driver'
    driver.parent.mkdir();driver.symlink_to(driver.parent/'missing')
    with pytest.raises(lt.LT02SafetyError):guard(trees)


@pytest.mark.parametrize('retained', ['maps','fd'])
def test_deleted_uio_cannot_use_reused_number_as_proof_of_unrelated_range(trees,retained):
    uio(trees,0x43c00000)  # Current uio7 does not prove the old inode's physical range.
    if retained=='maps':mapping(trees,0,device='/dev/uio7 (deleted)')
    else:(trees[1]/'123/fd/4').symlink_to('/dev/uio7 (deleted)')
    with pytest.raises(lt.LT02SafetyError):guard(trees)

"""Offline kit/conversion negative tests; no devices or recovery claims."""
from pathlib import Path
import json
import struct
import tarfile

import pytest

from pl.hil.swd04 import contract as c
from pl.hil.swd04 import staging as s
from pl.tests.test_swd04_hil_contract import candidate_files


def bit_fixture(payload):
    data = struct.pack('>H', 9) + bytes.fromhex('0ff00ff00ff00ff000') + b'\0\1'
    for tag, value in [(b'a', b'fixture\0'), (b'b', b'7z020clg400\0'),
                       (b'c', b'2026/10/15\0'), (b'd', b'00:00:00\0')]:
        data += tag + struct.pack('>H', len(value)) + value
    return data + b'e' + struct.pack('>I', len(payload)) + payload


def conversion_pair(tmp_path, monkeypatch):
    payload = bytes.fromhex('ffffffffaa99556620000000')
    bit = tmp_path / 'test.bit'
    bit.write_bytes(bit_fixture(payload))
    firmware = tmp_path / 'test.bin'
    firmware.write_bytes(b''.join(payload[i:i+4][::-1] for i in range(0,len(payload),4))
                         + bytes.fromhex('00000020'))
    monkeypatch.setattr(c, 'CANDIDATE_BIN_SHA256', c.sha256_file(firmware))
    return bit, firmware


def test_conversion_every_byte_and_no_boot_image(tmp_path, monkeypatch):
    bit, firmware = conversion_pair(tmp_path, monkeypatch)
    assert s.verify_bin(bit, firmware)['physical_configuration'] == 'NOT_RUN'
    good = firmware.read_bytes()
    for bad in [good[:-1], good+b'\0', bit.read_bytes(), s.bit_payload(bit.read_bytes()),
                b'BOOT'+good, good[:8]+bytes([good[8]^1])+good[9:]]:
        firmware.write_bytes(bad)
        with pytest.raises(c.SafetyError): s.verify_bin(bit, firmware)


@pytest.mark.parametrize('mutation', ['truncate', 'length', 'part', 'trailer'])
def test_bit_envelope_fails_closed(tmp_path, monkeypatch, mutation):
    bit, _ = conversion_pair(tmp_path, monkeypatch)
    good = bit.read_bytes()
    if mutation == 'truncate': bad = good[:10]
    elif mutation == 'length': bad = good[:-1]
    elif mutation == 'part': bad = good.replace(b'7z020', b'7z010')
    else: bad = good+b'\0'
    with pytest.raises(c.SafetyError): s.bit_payload(bad)


@pytest.mark.parametrize('key,value', [
    ('identity_schema_version', 2), ('hardware_abi_version', True),
    ('swd_command_abi_version', 2), ('swd_transaction_abi_version', 2),
    ('build_id', '0'*32), ('external_pl_io', True),
    ('capability_flags', 1), ('bitstream_version', '0.2.0'),
])
def test_manifest_abi_not_conflated(tmp_path, monkeypatch, key, value):
    candidate = candidate_files(tmp_path, monkeypatch)
    doc = json.loads(candidate.manifest.read_text()); doc[key] = value
    candidate.manifest.write_text(json.dumps(doc))
    with pytest.raises(c.SafetyError): c.verify_candidate(candidate)


def test_kit_missing_recovery_is_no_go_and_complete_pair_is_checked(tmp_path, monkeypatch):
    candidate = candidate_files(tmp_path, monkeypatch)
    bit, firmware = conversion_pair(tmp_path, monkeypatch)
    candidate.bit.write_bytes(bit.read_bytes())
    monkeypatch.setattr(c, 'BIT_SHA256', c.sha256_file(candidate.bit))
    doc = json.loads(candidate.manifest.read_text()); doc['bitstream_sha256'] = c.BIT_SHA256
    candidate.manifest.write_text(json.dumps(doc))
    full = s.create_kit(candidate, firmware, tmp_path/'full')
    assert full['recovery_bytes_verified'] and full['live_authorization'] == 'NOT_GRANTED'
    with tarfile.open(tmp_path/'full/swd04-offline.tar.gz') as archive:
        assert 'swd04/recovery/base.bin' in archive.getnames()
    with pytest.raises(FileExistsError): s.create_kit(candidate, firmware, tmp_path/'full')
    candidate.recovery_bin.unlink(); candidate.recovery_hwh.unlink()
    partial = s.create_kit(candidate, firmware, tmp_path/'partial')
    assert partial['physical_execution_readiness'] == 'NO_GO'
    assert partial['candidate_contract'] == 'PASS'
    assert not (tmp_path/'partial/recovery/base.bin').exists()


def test_missed_abort_window_stops_without_retry():
    from pl.hil.swd04 import mmio_contract as m
    from pl.tests.test_swd04_hil_contract import SimulatedMMIO
    class CompletedBeforeRead(SimulatedMMIO):
        def write32(self, address, value):
            super().write32(address, value)
            if address == c.COMMAND and value == 1:
                self.state[c.STATUS] = c.RESP_VALID
                self.state[c.META] = 7  # timeout is NOT an observed abort
    hw = CompletedBeforeRead()
    with pytest.raises(c.SafetyError, match='Expected BUSY'):
        m.hil03_recovery(m.RestrictedMMIO(hw))
    commands = [e[2] for e in hw.events if e[0] == 'write' and e[1] == c.COMMAND]
    assert commands == [1]


def test_live_failure_preserves_evidence_without_retry(tmp_path, monkeypatch):
    from pl.hil.swd04 import live
    from pl.tests.test_swd04_hil_contract import live_session_fixture
    p0, session, firmware, _ = live_session_fixture(tmp_path, monkeypatch)
    events = []
    class FailedMMIO:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read32(self, address):
            events.append(address)
            return 0  # wrong Identity MAGIC
    monkeypatch.setattr(live, 'DevMemBackend', lambda **kw: FailedMMIO())
    out = tmp_path/'failure.json'
    rc = live.main(['--stage', 'HIL01', '--p0-report', str(p0),
                    '--session', str(session), '--candidate-bin', str(firmware),
                    '--output', str(out), '--execute-live', '--ack-unrecoverable-axi-stall-risk'])
    assert rc == 2 and events == [c.AXI_BASES['identity_0']]
    failure = json.loads(out.read_text())
    assert failure['result'] == 'FAIL' and len(failure['mmio_audit']) == 1
    assert failure['recovery_restoration'] == 'NOT_RUN'

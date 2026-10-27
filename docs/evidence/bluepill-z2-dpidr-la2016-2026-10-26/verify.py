#!/usr/bin/env python3
"""Verify archived captures and evidence hashes offline; never open a device."""

from collections import Counter
import configparser
import hashlib
import json
from pathlib import Path
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def waveform(path: Path) -> dict:
    states = Counter()
    sample_count = 0
    chunks = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        chunks = sorted((name for name in names
                         if re.fullmatch(r'logic-1-[0-9]+', name)),
                        key=lambda item: int(item.rsplit('-', 1)[1]))
        assert chunks == [f'logic-1-{index}' for index in range(1, 25)]
        assert set(names) == {'version', 'metadata', *chunks}
        assert archive.read('version') == b'2'
        metadata = configparser.ConfigParser()
        metadata.read_string(archive.read('metadata').decode('ascii'))
        device = metadata['device 1']
        assert device['samplerate'] == '5 MHz' and device['unitsize'] == '2'
        assert [device[f'probe{index}'] for index in (1, 2, 3)] == [
            'CH0', 'CH1', 'CH2']
        for name in chunks:
            data = archive.read(name)
            assert len(data) % 2 == 0 and 0 < len(data) <= 4_194_304
            low_bytes = data[::2]
            assert all(value & ~7 == 0 for value in low_bytes)
            states.update(low_bytes)
            sample_count += len(low_bytes)
    assert states == Counter({6: sample_count})
    return {
        'sample_count': sample_count,
        'logic_chunks': len(chunks),
        'states_ch2_ch1_ch0': {'6': sample_count},
        'ch0_transitions': 0,
    }


def main() -> None:
    expected_files = {}
    for line in (ROOT / 'SHA256SUMS').read_text().splitlines():
        digest, filename = line.split('  ', 1)
        assert re.fullmatch(r'[a-f0-9]{64}', digest)
        assert filename not in expected_files and '/' not in filename
        expected_files[filename] = digest
    actual_files = {path.name for path in ROOT.iterdir()
                    if path.is_file() and path.name != 'SHA256SUMS'}
    assert set(expected_files) == actual_files
    for filename, digest in expected_files.items():
        assert sha256(ROOT / filename) == digest, filename

    provenance = json.loads((ROOT / 'source-integrity.json').read_text())
    for filename, record in provenance['redacted_reports'].items():
        assert sha256(ROOT / filename) == record['published_sha256']
    assert sha256(ROOT / 'postrun-preflight.json') == provenance['postrun_source_sha256']
    with tarfile.open(ROOT / 'bridge-bundle.tar') as bundle:
        assert {member.name for member in bundle} == set(provenance['bundle_members'])
        for member in bundle:
            assert member.isfile() and not member.issym()
            assert hashlib.sha256(bundle.extractfile(member).read()).hexdigest() == \
                provenance['bundle_members'][member.name]
    assert sha256(ROOT / 'execution-scripts-redacted.tar') == \
        provenance['execution_scripts_archive_sha256']
    with tarfile.open(ROOT / 'execution-scripts-redacted.tar') as bundle:
        assert {member.name for member in bundle} == set(provenance['execution_scripts'])
        for member in bundle:
            assert member.isfile() and not member.issym()
            content = bundle.extractfile(member).read()
            assert not re.search(rb'/home/[^/\s]+', content)
            assert b'PRIVATE KEY' not in content
            assert hashlib.sha256(content).hexdigest() == \
                provenance['execution_scripts'][member.name]['published_sha256']

    measurements = json.loads((ROOT / 'measurements.json').read_text())
    for name, expected in measurements['captures'].items():
        observed = waveform(ROOT / name)
        for key, value in observed.items():
            assert expected[key] == value, (name, key)
        receipt = json.loads((ROOT / name.replace('.sr', '-sanitized.json')).read_text())
        assert receipt['capture_exit'] == 0
        assert receipt['capture_sha256'] == sha256(ROOT / name)
    first = json.loads((ROOT / 'capture-01-sanitized.json').read_text())
    second = json.loads((ROOT / 'capture-02-sanitized.json').read_text())
    assert 'AssertionError: IMAGE_CHANGED' in first['remote_stderr']
    assert first['remote_stdout'] == ''
    second_remote = json.loads(second['remote_stdout'])
    bridge = json.loads(second_remote['bridge_stdout'])
    assert second_remote['openocd_exit'] == 1
    assert 'Error connecting DP: cannot read IDR' in second_remote['openocd_log']
    assert second_remote['dpidr_observed'] is False
    assert bridge['result'] == 'BRIDGE_CLOSED' and second_remote['bridge_exit'] == 0
    assert second_remote['socket_left'] is False
    print('BLUEPILL_Z2_DPIDR_ARCHIVE_PASS')


if __name__ == '__main__':
    main()

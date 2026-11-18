"""Offline integrity and consistency checks for the 2026-10-27 evidence package."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def receipt(name: str) -> dict:
    return json.loads((ROOT / 'receipts' / name).read_text())


def main() -> None:
    entries = (ROOT / 'SHA256SUMS').read_text().splitlines()
    for line in entries:
        expected, name = line.split('  ', 1)
        path = ROOT / name
        assert path.is_file() and sha(path) == expected, name
    assert sha(ROOT / 'fpga/plasma-bluepill-swd-65dca783.bin') == 'bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1'
    assert sha(ROOT / 'fpga/image-manifest.json') == '5f5fa580e9b437ce3a9377313bdfb4fc6012031270e1544c12034ccf3ca0fb98'
    firmware = (ROOT / 'firmware/plasma-blue-pill-cdc.bin').read_bytes()
    assert len(firmware) == 18768
    page18 = firmware[0x4800:0x4c00].ljust(1024, b'\xff')
    assert hashlib.sha256(page18).hexdigest() == 'b2206d042efe720c207c3a1b2eb1827eea2d480fa5c36efddad963708c9d38c6'
    assert receipt('page18-read-report.json')['backup_sha256'] == receipt('page18-readback-report.json')['backup_sha256']
    program = receipt('page18-program-report.json')
    assert program['remote_exit'] == program['la_exit'] == 0
    assert receipt('step5-capture-report.json')['remote_exit'] == 0
    assert 'SWD DPIDR 0x1ba01477' in receipt('step5-capture-report.json')['remote_stdout']
    clock = receipt('clock-measurement.json')
    assert clock['sample_rate_hz'] == 5_000_000 and clock['modal_period_samples'] == 1385
    assert abs(clock['modal_frequency_hz'] - 5_000_000 / 1385) < 1e-6
    assert receipt('cdc-after_reset.json')['heartbeat_count'] == 14

    wave = ROOT / 'waveforms/last-page-read-clock-only.sr'
    assert sha(wave) == '96dcbcb8d4b776931659bd9d610786e3c3f903226715b9ce4e10d4b6eae0e410'
    edges = 0
    previous = None
    with zipfile.ZipFile(wave) as archive:
        chunks = sorted((n for n in archive.namelist() if n.startswith('logic-1-')), key=lambda n: int(n.rsplit('-', 1)[1]))
        for name in chunks:
            data = archive.read(name)
            assert len(data) % 2 == 0
            low = data[::2]
            assert all(byte & 0x02 == 0 for byte in low), f'SWDIO not cleared: {name}'
            for byte in low:
                state = byte & 1
                if previous is not None and state != previous:
                    edges += 1
                previous = state
    assert edges == 42_570, edges
    print(f'PASS: {len(entries)} SHA256 entries, FPGA/firmware/receipts, sanitized SWDIO, {edges} SWCLK edges')


if __name__ == '__main__':
    main()

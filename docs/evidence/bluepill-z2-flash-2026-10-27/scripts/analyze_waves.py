"""Offline edge/state summary for every original LA2016 Flash-test archive."""
import configparser
import hashlib
import json
from pathlib import Path
import re
import zipfile

here = Path(__file__).resolve().parent
stages = [
    ('probe', 'probe.sr', 'probe-report.json'),
    ('read_last_page', 'read.sr', 'read-report.json'),
    ('read_page18', 'page18-read.sr', 'page18-read-report.json'),
    ('erase_program_verify', 'page18-program.sr', 'page18-program-report.json'),
    ('readback_page18', 'page18-readback.sr', 'page18-readback-report.json'),
    ('reset_run', 'reset.sr', 'reset-report.json'),
]
tables = [bytes((value >> channel) & 1 for value in range(256)) for channel in range(4)]
output = {}
for stage, filename, report_name in stages:
    path = here / filename
    report = json.loads((here / report_name).read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == report['wave_sha256'], stage
    states = {v: 0 for v in range(16)}
    edges = [0, 0, 0, 0]
    previous = None
    samples = 0
    with zipfile.ZipFile(path) as archive:
        chunks = sorted((name for name in archive.namelist()
                         if re.fullmatch(r'logic-1-[0-9]+', name)),
                        key=lambda name: int(name.rsplit('-', 1)[1]))
        meta = configparser.ConfigParser()
        meta.read_string(archive.read('metadata').decode('ascii'))
        device = meta['device 1']
        assert device['samplerate'] == '5 MHz' and device['unitsize'] == '2'
        assert [device[f'probe{i}'] for i in (1, 2, 3, 4)] == \
               ['CH0', 'CH1', 'CH2', 'CH3']
        for name in chunks:
            data = archive.read(name)
            assert len(data) % 2 == 0
            low = data[::2]
            assert set(low) <= set(range(16)), stage
            for value in range(16):
                states[value] += low.count(value)
            for channel, table in enumerate(tables):
                bits = low.translate(table)
                if previous is not None and bits[0] != ((previous >> channel) & 1):
                    edges[channel] += 1
                edges[channel] += bits.count(b'\x00\x01') + bits.count(b'\x01\x00')
            previous = low[-1]
            samples += len(low)
    assert sum(states.values()) == samples
    output[stage] = {
        'wave_sha256': digest, 'sample_rate_hz': 5_000_000,
        'sample_count': samples, 'duration_s': samples / 5_000_000,
        'logic_chunks': len(chunks),
        'states_ch3_ch2_ch1_ch0': {str(k): v for k, v in states.items() if v},
        'edges_CH0_CH1_CH2_CH3': edges,
        'la_exit': report['la_exit'], 'remote_exit': report['remote_exit'],
        'la_started_before_remote_trigger': report['la_session_start_observed'] and
            report['capture_start_unix_ns'] < report['remote_trigger_unix_ns'] <
            report['capture_finish_unix_ns'],
    }
(here / 'wave-analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
print(json.dumps(output, sort_keys=True))

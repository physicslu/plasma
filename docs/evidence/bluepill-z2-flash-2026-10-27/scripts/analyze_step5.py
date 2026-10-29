"""Count signal states and edges in the original 5 MHz DPIDR capture."""
import configparser
import hashlib
import json
from pathlib import Path
import re
import zipfile

here = Path(__file__).resolve().parent
path = here / 'step5-dpidr.sr'
report = json.loads((here / 'step5-capture-report.json').read_text())
digest = hashlib.sha256(path.read_bytes()).hexdigest()
assert digest == report['wave_sha256'], 'WAVE_CHANGED'
states = {v: 0 for v in range(16)}
edges = [0, 0, 0, 0]
first_edges = [[], [], [], []]
count = 0
previous = None
tables = [bytes((value >> channel) & 1 for value in range(256))
          for channel in range(4)]
with zipfile.ZipFile(path) as archive:
    chunks = sorted((name for name in archive.namelist()
                     if re.fullmatch(r'logic-1-[0-9]+', name)),
                    key=lambda name: int(name.rsplit('-', 1)[1]))
    metadata = configparser.ConfigParser()
    metadata.read_string(archive.read('metadata').decode('ascii'))
    device = metadata['device 1']
    assert device['samplerate'] == '5 MHz' and device['unitsize'] == '2'
    assert [device[f'probe{i}'] for i in (1, 2, 3, 4)] == \
           ['CH0', 'CH1', 'CH2', 'CH3']
    for name in chunks:
        data = archive.read(name)
        assert len(data) % 2 == 0
        low = data[::2]
        assert all(value < 16 for value in set(low)), 'UNEXPECTED_CHANNEL_BITS'
        for value in range(16):
            states[value] += low.count(value)
        for channel, table in enumerate(tables):
            mapped = low.translate(table)
            bit = mapped[0]
            if previous is not None and bit != ((previous >> channel) & 1):
                edges[channel] += 1
                if len(first_edges[channel]) < 12:
                    first_edges[channel].append(count)
            edges[channel] += mapped.count(b'\x00\x01') + mapped.count(b'\x01\x00')
            if len(first_edges[channel]) < 12:
                found = []
                for pattern in (b'\x00\x01', b'\x01\x00'):
                    start = 0
                    seen = 0
                    while seen < 12:
                        at = mapped.find(pattern, start)
                        if at < 0:
                            break
                        found.append(count + at + 1)
                        start = at + 1
                        seen += 1
                first_edges[channel].extend(sorted(found)[:12-len(first_edges[channel])])
        previous = low[-1]
        count += len(low)
assert sum(states.values()) == count
result = {
    'wave_sha256': digest,
    'sample_rate_hz': 5_000_000,
    'sample_count': count,
    'duration_s': count / 5_000_000,
    'logic_chunks': len(chunks),
    'states_ch3_ch2_ch1_ch0': {str(k): v for k, v in states.items() if v},
    'edge_counts_CH0_CH1_CH2_CH3': edges,
    'first_edge_sample_indices_CH0_CH1_CH2_CH3': first_edges,
    'la_started_before_remote_trigger': report['la_session_start_observed'] and
        report['capture_start_unix_ns'] < report['remote_trigger_unix_ns'] <
        report['capture_finish_unix_ns'],
    'la_exit': report['la_exit'],
    'remote_exit': report['remote_exit'],
}
(here / 'step5-analysis.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, sort_keys=True))

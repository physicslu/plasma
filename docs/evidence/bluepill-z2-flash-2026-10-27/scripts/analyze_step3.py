"""Read the raw passive LA capture and count each channel's transitions."""
from collections import Counter
import configparser
import hashlib
import json
from pathlib import Path
import re
import zipfile

here = Path(__file__).resolve().parent
path = here / 'step3-swclk.sr'
report = json.loads((here / 'step3-capture-report.json').read_text())
digest = hashlib.sha256(path.read_bytes()).hexdigest()
assert digest == report['wave_sha256'], 'WAVE_CHANGED'
states = Counter()
edges = [0, 0, 0, 0]
first_edges = [[], [], [], []]
count = 0
previous = None
with zipfile.ZipFile(path) as archive:
    chunks = sorted((name for name in archive.namelist()
                     if re.fullmatch(r'logic-1-[0-9]+', name)),
                    key=lambda name: int(name.rsplit('-', 1)[1]))
    metadata = configparser.ConfigParser()
    metadata.read_string(archive.read('metadata').decode('ascii'))
    device = metadata['device 1']
    assert device['samplerate'] == '1 MHz' and device['unitsize'] == '2'
    assert [device[f'probe{i}'] for i in (1, 2, 3, 4)] == \
           ['CH0', 'CH1', 'CH2', 'CH3']
    for name in chunks:
        data = archive.read(name)
        assert len(data) % 2 == 0
        for value in data[::2]:
            assert value & ~0x0F == 0
            states[value] += 1
            if previous is not None:
                changed = value ^ previous
                for channel in range(4):
                    if changed & (1 << channel):
                        edges[channel] += 1
                        if len(first_edges[channel]) < 12:
                            first_edges[channel].append(count)
            previous = value
            count += 1
result = {
    'wave_sha256': digest,
    'sample_rate_hz': 1_000_000,
    'sample_count': count,
    'duration_s': count / 1_000_000,
    'logic_chunks': len(chunks),
    'states_ch3_ch2_ch1_ch0': {str(k): v for k, v in sorted(states.items())},
    'edge_counts_CH0_CH1_CH2_CH3': edges,
    'first_edge_sample_indices_CH0_CH1_CH2_CH3': first_edges,
    'la_started_before_remote_trigger': report['la_session_start_observed'] and
        report['capture_start_unix_ns'] < report['remote_trigger_unix_ns'] <
        report['capture_finish_unix_ns'],
    'la_exit': report['la_exit'],
    'remote_exit': report['remote_exit'],
}
(here / 'step3-analysis.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, sort_keys=True))

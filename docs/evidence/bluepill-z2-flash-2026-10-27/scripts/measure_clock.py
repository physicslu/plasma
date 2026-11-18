"""Measure CH0 rising-edge periods from the real 5 MHz program capture."""
from collections import Counter
import json
from pathlib import Path
import re
import zipfile

path = Path(__file__).resolve().parent / 'page18-program.sr'
rises = []
offset = 0
previous = None
table = bytes(value & 1 for value in range(256))
with zipfile.ZipFile(path) as archive:
    chunks = sorted((name for name in archive.namelist()
                     if re.fullmatch(r'logic-1-[0-9]+', name)),
                    key=lambda name: int(name.rsplit('-', 1)[1]))
    for name in chunks:
        bits = archive.read(name)[::2].translate(table)
        if previous == 0 and bits[0] == 1:
            rises.append(offset)
        start = 0
        while True:
            at = bits.find(b'\x00\x01', start)
            if at < 0:
                break
            rises.append(offset + at + 1)
            start = at + 1
        previous = bits[-1]
        offset += len(bits)
periods = [b-a for a,b in zip(rises,rises[1:])]
active = [value for value in periods if value <= 500000]
hist = Counter(active)
modal_samples, modal_count = hist.most_common(1)[0]
active.sort()
result = {
    'sample_rate_hz': 5_000_000,
    'rising_edges': len(rises),
    'all_periods': len(periods),
    'active_periods_le_500000_samples': len(active),
    'minimum_period_samples': min(periods),
    'modal_period_samples': modal_samples,
    'modal_period_count': modal_count,
    'modal_period_us': modal_samples / 5,
    'modal_frequency_hz': 5_000_000 / modal_samples,
    'median_period_samples': active[len(active)//2],
    'p05_period_samples': active[len(active)//20],
    'p95_period_samples': active[(len(active)*95)//100],
    'top_periods': hist.most_common(12),
}
(path.parent / 'clock-measurement.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, sort_keys=True))

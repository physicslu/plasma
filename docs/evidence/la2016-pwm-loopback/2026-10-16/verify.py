#!/usr/bin/env python3
"""Recompute this saved experiment offline; never open an instrument."""

import configparser
import hashlib
import json
from pathlib import Path
import struct
import statistics
import zipfile


ROOT = Path(__file__).resolve().parent


def read_ch0(path):
    with zipfile.ZipFile(path) as archive:
        metadata = configparser.ConfigParser()
        metadata.read_string(archive.read("metadata").decode())
        device = metadata["device 1"]
        assert device["probe1"] == "CH0"
        assert device["samplerate"] == "1 MHz"
        assert device["unitsize"] == "2"
        chunks = sorted(
            (name for name in archive.namelist() if name.startswith("logic-1-")),
            key=lambda name: int(name.rsplit("-", 1)[1]),
        )
        assert chunks and sum(archive.getinfo(n).file_size for n in chunks) < 1_000_000
        data = b"".join(archive.read(name) for name in chunks)
    assert data and len(data) % 2 == 0
    return [word[0] & 1 for word in struct.iter_unpack("<H", data)]


def main():
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name

    for result in json.loads((ROOT / "measurements.json").read_text()):
        values = read_ch0(ROOT / result["capture_file"])
        edges = [i for i in range(1, len(values)) if values[i] != values[i - 1]]
        rising = [i for i in edges if values[i]]
        falling = [i for i in edges if not values[i]]
        assert len(values) == result["actual_sample_count"]
        assert len(edges) == result["edge_count"] > 0
        assert len(rising) == result["rising_edge_count"]
        assert len(falling) == result["falling_edge_count"]
        periods, highs = [], []
        for first, last in zip(rising, rising[1:]):
            middle = [i for i in falling if first < i < last]
            assert len(middle) == 1
            periods.append(last - first)
            highs.append(middle[0] - first)
        assert len(periods) == result["complete_cycles"] > 1
        expected_period = 1_000_000 / result["requested_frequency_Hz"]
        expected_high = expected_period * result["requested_duty_percent"] / 100
        assert all(period == expected_period for period in periods)
        assert all(high == expected_high for high in highs)
        frequency = 1_000_000 / statistics.mean(periods)
        duty = 100 * sum(highs) / sum(periods)
        assert frequency == result["frequency_Hz"]
        assert duty == result["duty_cycle_percent"]
        assert statistics.mean(periods) == result["period_us"]
        assert statistics.mean(highs) == result["high_us"]
        assert statistics.mean(p - h for p, h in zip(periods, highs)) == result["low_us"]

        off = read_ch0(ROOT / result["off_capture_file"])
        assert len(off) == result["off_sample_count"] == 22496
        assert all(value == 0 for value in off)
        assert result["off_edge_count"] == result["off_high_sample_count"] == 0
        logs = json.loads(
            (ROOT / Path(result["capture_file"]).parent / "execution-sanitized.json").read_text()
        )
        assert all(log["returncode"] == 0 for log in logs)
        assert logs[1]["stage"] == "pwm1-finally-off"
        assert "channel_group=PWM1:enabled=off" in logs[1]["argv"]
        assert "ch 0, en 0" in logs[1]["stderr"]
        assert result["result"] == result["shutdown_command"] == "PASS"
        print(f"{frequency:g} Hz, {duty:g}%, {len(edges)} edges; OFF constant Low: PASS")
    print("Archive checksums and offline waveform replay: PASS (no new hardware run)")


if __name__ == "__main__":
    main()

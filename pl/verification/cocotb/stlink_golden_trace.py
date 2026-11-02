"""Read *real* STLINK-V3SET SWCLK/SWDIO capture, not a synthetic target model.

This reader is deliberately independent of SWD RTL, its AXI codec and Sigrok's
text decoder. The signal truth comes from the SHA-pinned original .sr archive.
CH0=SWCLK, CH1=SWDIO; use stable SWCLK-LOW samples immediately BEFORE rising,
the same physical sampling order as OpenOCD bitbang.

Only bounded DPIDR/ACK response windows are returned: the archived waveform
contains real programmer/target traffic, not a full reusable host/target stimulus
with direction/OE, and must never be blindly replayed to an actual DUT.
"""
from collections import Counter, deque
import configparser
import hashlib
from pathlib import Path
import re
import zipfile

GOLDEN_DIR = (Path(__file__).resolve().parents[3] / "docs/evidence/"
              "stlink-stm32f103-swd-reference/2026-10-23")
VERIFY_CAPTURE = "round-01-verify.sr"
DPIDR = 0x1BA01477


def _bits(value, count):
    return tuple((value >> bit) & 1 for bit in range(count))


def _request_valid(bits):
    if any(value is None for value in bits):
        return False
    start, ap, read, a2, a3, parity, stop, park = bits
    return start == 1 and stop == 0 and park == 1 and parity == (ap ^ read ^ a2 ^ a3)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_reference(name=VERIFY_CAPTURE):
    """Find independently decoded SWD DPIDR and WAIT evidence in raw samples.

    Sample resolution must allow multiple samples in each SWCLK LOW window.
    A bit is the SWDIO level 4 samples before its SWCLK rising edge, not the
    next bit which the target is permitted to update *after* that edge.
    """
    if name not in ("round-01-verify.sr", "round-02-verify.sr",
                    "round-03-verify.sr"):
        raise ValueError("Only approved ST-LINK Verify captures are admissible")
    path = GOLDEN_DIR / name
    manifest = dict(line.rstrip("\n").split("  ", 1)
                    for line in (GOLDEN_DIR / "SHA256SUMS").read_text().splitlines())
    expected = manifest[name]
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"Golden waveform SHA mismatch: {name}")
    edges = []
    samples = []
    previous_clock = None
    # Fixed-memory LOW-window ring. Require stable last seven samples; do not
    # infer bits when the analyzer resolution cannot distinguish transitions.
    lows = deque(maxlen=8)
    sample_index = 0
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        chunks = sorted((n for n in names if re.fullmatch(r"logic-1-\d+", n)),
                        key=lambda n: int(n.rsplit("-", 1)[1]))
        if not chunks or z.read("version") != b"2":
            raise ValueError("Unexpected Sigrok archive")
        m = configparser.ConfigParser()
        m.read_string(z.read("metadata").decode("ascii"))
        d = m["device 1"]
        if d["samplerate"] != "5 MHz" or d["unitsize"] != "2" or [
            d[f"probe{i}"] for i in (1, 2, 3)] != ["CH0", "CH1", "CH2"]:
            raise ValueError("Golden reference sample format mismatch")
        for member in chunks:
            raw = z.read(member)
            if len(raw) & 1 or len(raw) > 4_194_304:
                raise ValueError("Invalid Sigrok logic chunk length")
            for value in raw[::2]:
                clk = value & 1
                swdio = (value >> 1) & 1
                if previous_clock is not None and clk and not previous_clock:
                    stable = len(lows) >= 7 and len(set(list(lows)[-7:])) == 1
                    samples.append(lows[-4] if stable else None)
                    edges.append(sample_index)
                    lows.clear()
                elif previous_clock is not None and not clk and previous_clock:
                    lows.clear()
                if not clk:
                    lows.append(swdio)
                previous_clock = clk
                sample_index += 1
    if len(edges) < 100_000:
        raise ValueError("Golden trace lacks physical SWCLK activity")
    dpidr_windows = []
    wait_windows = []
    # Capture every verified DPIDR frame, plus a bounded WAIT example.
    # 8 request clocks, 1 turnaround, 3 ACK, 32 data, 1 parity.
    for index in range(len(edges) - 46):
        header_bits = samples[index:index + 8]
        if not _request_valid(header_bits):
            continue
        if any(edges[k + 1] - edges[k] > 180 for k in range(index, index + 45)):
            continue
        ack_bits = samples[index + 9:index + 12]
        if None in ack_bits:
            continue
        ack = sum(bit << k for k, bit in enumerate(ack_bits))
        if ack == 2 and len(wait_windows) < 2:
            wait_windows.append(dict(ack=2, header=tuple(header_bits),
                                     response_bits=tuple(ack_bits),
                                     position=index))
        if tuple(header_bits) != _bits(0xA5, 8) or ack != 1:
            continue
        data_bits = samples[index + 12:index + 44]
        parity = samples[index + 44]
        if None in data_bits or parity is None:
            continue
        data = sum(bit << k for k, bit in enumerate(data_bits))
        if data == DPIDR and parity == (data.bit_count() & 1):
            dpidr_windows.append(dict(ack=1, data=data, parity=parity,
                                      header=tuple(header_bits),
                                      response_bits=tuple(ack_bits + data_bits + [parity]),
                                      position=index))
    if len(dpidr_windows) < 2 or not wait_windows:
        raise AssertionError(
            f"Real Golden SWD decode mismatch: {name}, DPIDR={len(dpidr_windows)}, "
            f"WAIT={len(wait_windows)}, SWCLK_rises={len(edges)}; "
            "do not substitute synthetic pass values")
    return dict(name=name, sha256=actual, sample_rate_hz=5_000_000,
                swclk_rises=len(edges), dpidr=dpidr_windows, wait=wait_windows)

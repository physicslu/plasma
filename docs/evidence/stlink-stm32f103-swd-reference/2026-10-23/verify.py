#!/usr/bin/env python3
"""Verify this archived ST-LINK reference entirely offline; never open USB."""

from collections import Counter
import configparser
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parent
CAPTURES = [f"round-{number:02d}-{phase}.sr"
            for number in (1, 2, 3) for phase in ("program", "verify")]
FIRMWARE_SHA256 = "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def weighted_quantile(histogram, numerator, denominator):
    total = sum(histogram.values())
    rank = (total - 1) * numerator // denominator
    seen = 0
    for value, count in sorted(histogram.items()):
        seen += count
        if seen > rank:
            return value
    raise ValueError("empty period histogram")


def waveform(path):
    periods = Counter()
    rising = [0, 0, 0]
    falling = [0, 0, 0]
    previous = None
    first = None
    last_rising = None
    ch2_high_start = None
    ch2_high_samples = 0
    samples = 0
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        chunks = sorted((name for name in names if re.fullmatch(r"logic-1-[0-9]+", name)),
                        key=lambda name: int(name.rsplit("-", 1)[1]))
        require(chunks == [f"logic-1-{i}" for i in range(1, 25)],
                f"unexpected logic chunks: {path.name}")
        require(set(names) == {"version", "metadata", *chunks},
                f"unexpected archive member: {path.name}")
        require(archive.read("version") == b"2", f"sigrok archive version: {path.name}")
        metadata = configparser.ConfigParser()
        metadata.read_string(archive.read("metadata").decode("ascii"))
        device = metadata["device 1"]
        require(device["samplerate"] == "5 MHz" and device["unitsize"] == "2",
                f"sample format: {path.name}")
        require([device[f"probe{i}"] for i in (1, 2, 3)] == ["CH0", "CH1", "CH2"],
                f"channel map: {path.name}")
        for name in chunks:
            info = archive.getinfo(name)
            require(0 < info.file_size <= 4_194_304 and info.file_size % 2 == 0,
                    f"chunk size: {path.name}/{name}")
            data = archive.read(name)
            for value in data[::2]:
                value &= 7
                if previous is None:
                    first = value
                    if value & 4:
                        ch2_high_start = 0
                else:
                    changed = previous ^ value
                    if changed:
                        for bit in range(3):
                            mask = 1 << bit
                            if changed & mask:
                                if value & mask:
                                    rising[bit] += 1
                                    if bit == 0:
                                        if last_rising is not None:
                                            periods[samples - last_rising] += 1
                                        last_rising = samples
                                    if bit == 2:
                                        ch2_high_start = samples
                                else:
                                    falling[bit] += 1
                                    if bit == 2:
                                        ch2_high_samples += samples - ch2_high_start
                                        ch2_high_start = None
                previous = value
                samples += 1
    require(49_000_000 <= samples <= 51_000_000, f"sample count: {path.name}")
    require(periods, f"no SWCLK periods: {path.name}")
    if previous & 4:
        ch2_high_samples += samples - ch2_high_start
    most_common = sorted(periods.items(), key=lambda item: (-item[1], item[0]))[0]
    return {
        "capture_file": path.name,
        "capture_sha256": sha256(path),
        "samplerate_hz": 5_000_000,
        "sample_count": samples,
        "duration_ns": samples * 200,
        "first_logic_bits_ch2_ch1_ch0": first,
        "last_logic_bits_ch2_ch1_ch0": previous,
        "ch0_rising": rising[0], "ch0_falling": falling[0],
        "ch1_rising": rising[1], "ch1_falling": falling[1],
        "ch2_rising": rising[2], "ch2_falling": falling[2],
        "ch2_high_samples": ch2_high_samples,
        "swclk_rising_period_count": sum(periods.values()),
        "swclk_period_min_samples": min(periods),
        "swclk_period_p50_samples": weighted_quantile(periods, 1, 2),
        "swclk_period_p95_samples": weighted_quantile(periods, 95, 100),
        "swclk_period_max_samples": max(periods),
        "swclk_modal_period_samples": most_common[0],
        "swclk_modal_period_count": most_common[1],
        "swclk_period_49_to_53_count": sum(v for k, v in periods.items() if 49 <= k <= 53),
        "swclk_period_80_to_88_count": sum(v for k, v in periods.items() if 80 <= k <= 88),
        "swclk_period_over_130_count": sum(v for k, v in periods.items() if k > 130),
        "swclk_period_histogram_samples": [[k, v] for k, v in sorted(periods.items())],
    }


def verify_manifest():
    listed = {}
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "bad digest")
        require(name == Path(name).name and name != "SHA256SUMS" and name not in listed,
                f"unsafe or duplicate manifest path: {name}")
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(), f"missing file: {name}")
        require(sha256(path) == digest, f"SHA256 mismatch: {name}")
        listed[name] = digest
    actual = {p.name for p in ROOT.iterdir() if p.is_file() and p.name != "SHA256SUMS"}
    require(actual == set(listed), f"manifest coverage: missing={actual-set(listed)}, extra={set(listed)-actual}")
    require(set(CAPTURES) <= set(listed), "six source waveforms missing")


def verify_source_integrity():
    provenance = json.loads((ROOT / "source-integrity.json").read_text())
    require(provenance["source_workspace"] ==
            ".work/blue-pill-hil-unblock-20261023/", "source workspace label")
    rows = provenance["waveforms"]
    require([row["file"] for row in rows] == CAPTURES, "six source comparisons")
    for row in rows:
        path = ROOT / row["file"]
        require(row["byte_identical"] is True and
                row["bytes"] == path.stat().st_size and
                row["source_sha256"] == row["archive_sha256"] == sha256(path),
                f"source/archive digest comparison: {row['file']}")


def verify_receipts():
    for number in (1, 2, 3):
        prefix = f"round-{number:02d}"
        program = json.loads((ROOT / f"{prefix}-program-sanitized.json").read_text())
        readback = json.loads((ROOT / f"{prefix}-verify-sanitized.json").read_text())
        require(program["sanitized_derivative"] and readback["sanitized_derivative"],
                f"receipt provenance {prefix}")
        require(program["stlink_exit"] == readback["stlink_exit"] == 0,
                f"Flash/readback exit {prefix}")
        require(program["la_exit"] == readback["la_exit"] == 0,
                f"LA exit {prefix}")
        require(program["firmware_sha256"] == readback["firmware_sha256"] == FIRMWARE_SHA256,
                f"firmware identity {prefix}")
        require(readback["readback_sha256"] == FIRMWARE_SHA256 and
                readback["readback_size_bytes"] == 18768 and
                readback["readback_matches_firmware"] is True,
                f"readback receipt {prefix}")
        require(program["stlink_command"][2:] ==
                ["write", "plasma-blue-pill-cdc.bin", "0x08000000"] and
                readback["stlink_command"][2:] ==
                ["read", f"{prefix}-readback.bin", "0x08000000", "18768"],
                f"Flash/readback command arguments {prefix}")
        require(sha256(ROOT / f"{prefix}-readback.bin") == FIRMWARE_SHA256,
                f"archived readback bytes {prefix}")
        for phase, receipt in (("program", program), ("verify", readback)):
            require(receipt["waveform_sha256"] == sha256(ROOT / f"{prefix}-{phase}.sr"),
                    f"waveform receipt {prefix}-{phase}")
            require(receipt["la_start_epoch"] < receipt["stlink_start_epoch"] <
                    receipt["stlink_end_epoch"] < receipt["la_end_epoch"],
                    f"capture time overlap {prefix}-{phase}")
        program_log = (ROOT / f"{prefix}-program-stlink-sanitized.log").read_text()
        verify_log = (ROOT / f"{prefix}-verify-stlink-sanitized.log").read_text()
        reset_log = (ROOT / f"{prefix}-reset-sanitized.log").read_text()
        require("Flash written and verified!" in program_log and
                "Finished erasing 19 pages" in program_log, f"Flash log {prefix}")
        require("read from address 0x08000000 size 18768" in verify_log,
                f"independent readback log {prefix}")
        require("NRST is not connected" in reset_log, f"reset warning {prefix}")
    for number in (2, 3):
        voltage_log = (ROOT / f"round-{number:02d}-voltage-sanitized.log").read_text()
        require("Target voltage: 3.316944" in voltage_log,
                f"target voltage log round {number}")


def verify_decode():
    summaries = json.loads((ROOT / "swd-decode-summary.json").read_text())
    require({row["capture_file"] for row in summaries} == set(CAPTURES), "decode summary coverage")
    for row in summaries:
        lines = (ROOT / row["decoder_file"]).read_text().splitlines()
        annotations = Counter(line.removeprefix("swd-1: ") for line in lines)
        require(all(line.startswith("swd-1: ") for line in lines), "non-annotation decoder line")
        require(row["decoder_sha256"] == sha256(ROOT / row["decoder_file"]),
                f"decoder SHA {row['capture_file']}")
        require(row["annotation_count"] == len(lines), "annotation count")
        for key, label in (("ack_ok", "OK"), ("ack_wait", "WAIT"),
                           ("ack_fault", "FAULT"), ("idcode_annotations", "IDCODE"),
                           ("idcode_value_annotations", "0x1ba01477")):
            require(row[key] == annotations[label], f"decoder count {key}: {row['capture_file']}")
        require(row["read_requests"] == sum(v for k, v in annotations.items() if k.startswith("R ")),
                "read requests")
        require(row["write_requests"] == sum(v for k, v in annotations.items() if k.startswith("W ")),
                "write requests")
        require(row["ack_ok"] > 1000 and row["read_requests"] > 1000 and
                row["ack_fault"] == 0, f"SWD decode activity {row['capture_file']}")
        if row["capture_file"].endswith("verify.sr"):
            require(row["idcode_annotations"] >= 1 and
                    row["idcode_value_annotations"] >= 1,
                    f"saved IDCODE annotation {row['capture_file']}")


def verify_cdc():
    summary = json.loads((ROOT / "cdc-summary.json").read_text())
    require(len(summary["observations"]) == 6, "CDC observation count")
    for row in summary["observations"]:
        lines = (ROOT / row["sanitized_log"]).read_text().splitlines()
        match = re.search(r"(?m)^exit_code=(\d+)$", "\n".join(lines))
        require(match is not None and int(match.group(1)) == row["exit_code"],
                f"CDC exit {row['label']}")
        heartbeats = []
        for line in lines:
            m = re.fullmatch(r"(\d+\.\d{6}) HB version=0\.1 seq=(\d+) uptime_ms=(\d+)", line)
            if m:
                seconds, micros = m.group(1).split(".")
                heartbeats.append((int(seconds) * 1_000_000 + int(micros),
                                   int(m.group(2)), int(m.group(3))))
        require(len(heartbeats) == row["heartbeat_count"], f"CDC count {row['label']}")
        require(list(heartbeats[0][1:]) == row["first_seq_uptime"] and
                list(heartbeats[-1][1:]) == row["last_seq_uptime"], f"CDC boundary {row['label']}")
        intervals = [b[0] - a[0] for a, b in zip(heartbeats, heartbeats[1:])]
        gaps = sum(max(0, b[1] - a[1] - 1) for a, b in zip(heartbeats, heartbeats[1:]))
        require(row["sequence_gaps"] == gaps and row["uptime_monotonic"] ==
                all(b[2] >= a[2] for a, b in zip(heartbeats, heartbeats[1:])),
                f"CDC integrity {row['label']}")
        require(row["interval_min_us"] == min(intervals) and
                row["interval_max_us"] == max(intervals) and
                row["interval_sum_us"] == sum(intervals), f"CDC timing {row['label']}")
        require(row["id_assertion_passed"] ==
                any(re.fullmatch(r"\d+\.\d{6} PASS: .*firmware ID; .*", line) for line in lines),
                f"CDC ID assertion {row['label']}")
        if row["label"] in ("round-02-first", "round-03-first"):
            require(row["exit_code"] == 1 and
                    any("ERR UNKNOWN_COMMAND" in line for line in lines), "first-attempt failure")
        elif row["label"] == "host-reopen":
            require(row["exit_code"] == 0 and row["id_assertion_passed"] and
                    any("HOST_PORT_PAUSE" in line for line in lines),
                    "host close/reopen result")
        else:
            require(row["exit_code"] == 0 and row["id_assertion_passed"] and
                    row["heartbeat_count"] >= 102 and row["sequence_gaps"] == 0 and
                    300_000 <= min(intervals) <= max(intervals) <= 700_000,
                    f"continuous CDC acceptance {row['label']}")
    require(summary["round_01_initial_failure_raw_log"] == "UNAVAILABLE_OVERWRITTEN",
            "round-01 evidence limit")


def verify_matrix():
    matrix = json.loads((ROOT / "acceptance-matrix.json").read_text())
    require(matrix["reference_programmer"] == "STLINK-V3SET" and
            matrix["z2_swd_programming"] == "NOT_RUN" and
            matrix["strict_post_reset_cdc_acceptance"] == "FAIL",
            "reference identity or acceptance boundary")
    rows = {row["test"]: row for row in matrix["rows"]}
    require(len(rows) == len(matrix["rows"]), "duplicate acceptance row")
    allowed = {"PASS", "FAIL", "NOT_RUN", "EVIDENCE_INSUFFICIENT"}
    for row in rows.values():
        require({row[f"round_{i:02d}"] for i in (1, 2, 3)} <= allowed,
                "invalid acceptance status")
    for test in ("ST-LINK Flash command and exit",
                 "Independent full-length readback SHA256",
                 "LA acquisition and CH0/CH1 activity",
                 "SWD DP/AP request and ACK decode",
                 "CDC after recorded empty-line recovery"):
        require(all(rows[test][f"round_{i:02d}"] == "PASS" for i in (1, 2, 3)),
                f"matrix mismatch: {test}")
    first = rows["First saved 60-second CDC probe and ID"]
    require([first[f"round_{i:02d}"] for i in (1, 2, 3)] ==
            ["PASS", "FAIL", "FAIL"], "first saved CDC matrix")
    for test in ("SWD timing qualification", "Physical NRST assertion"):
        require(all(rows[test][f"round_{i:02d}"] == "EVIDENCE_INSUFFICIENT"
                    for i in (1, 2, 3)), f"unsupported qualification claim: {test}")


def main():
    if sys.argv[1:] == ["--write-measurements"]:
        result = [waveform(ROOT / name) for name in CAPTURES]
        (ROOT / "measurements.json").write_text(json.dumps(result, indent=2) + "\n")
        print("Wrote six independently measured waveform records")
        return
    require(not sys.argv[1:], "usage: verify.py [--write-measurements]")
    verify_manifest()
    verify_source_integrity()
    saved = json.loads((ROOT / "measurements.json").read_text())
    require([row["capture_file"] for row in saved] == CAPTURES, "measurement coverage")
    for row in saved:
        actual = waveform(ROOT / row["capture_file"])
        require(row == actual, f"waveform measurement mismatch: {row['capture_file']}")
        require(actual["ch0_rising"] > 100_000 and actual["ch1_rising"] > 10_000,
                f"SWD channel activity: {row['capture_file']}")
        require(actual["ch2_high_samples"] == actual["sample_count"] and
                actual["ch2_rising"] == actual["ch2_falling"] == 0,
                f"DUT logic threshold status: {row['capture_file']}")
        print(f"{row['capture_file']}: {actual['sample_count']} samples, "
              f"CH0 {actual['ch0_rising']} rises, CH1 {actual['ch1_rising']} rises, "
              f"modal period {actual['swclk_modal_period_samples']} samples: PASS")
    verify_receipts()
    verify_decode()
    verify_cdc()
    verify_matrix()
    print("Archive SHA256, waveform, receipt, decode and CDC replay: PASS (offline only)")


if __name__ == "__main__":
    main()

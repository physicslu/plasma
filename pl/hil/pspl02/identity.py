"""Read-only board identity, shared by inventory, preflight and runtime.

Generic Zynq compatibility and software health never identify a board. A DT
without a board model needs independently reviewed, externally hash-pinned
physical enrollment evidence. Enrollment is operational identification, not
cryptographic attestation of silicon; machine-id and SD images can be cloned.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from pl.hil.swd04.contract import (
    SafetyError, _require, sha256_file, RECOVERY_BIN_SHA256, RECOVERY_HWH_SHA256,
)

MODELS = frozenset({"tul pynq-z2", "pynq-z2", "pynq z2"})
COMPATIBLE = ["xlnx,zynq-7000"]
OPTION_NAMES = ("board_record", "board_record_sha256", "board_physical_evidence",
                "board_base_bin", "board_base_hwh")


def add_arguments(parser):
    for name in OPTION_NAMES:
        parser.add_argument("--"+name.replace("_", "-"),
                            type=str if name.endswith("sha256") else Path,
                            help="Missing-model enrollment input; no automatic trust or enrollment")


def options(args):
    return {name: getattr(args, name) for name in OPTION_NAMES}


def digest_report(report: dict) -> str:
    validate_report(report)
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _digest(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate enrollment JSON key")
        result[key] = value
    return result


def _strings(raw: bytes):
    parts = raw.decode("ascii").split("\0")
    if parts[-1] == "":
        parts.pop()
    _require(bool(parts) and all(parts), "Malformed Device Tree string property")
    return parts


def validate_report(report: dict) -> None:
    _require(type(report) is dict and type(report.get("schema_version")) is int
             and report["schema_version"] == 1 and report.get("board") == "PYNQ-Z2",
             "Missing/invalid structured board identity")
    model, compatible = report.get("model"), report.get("compatible")
    _require(type(compatible) is list and compatible in ([], COMPATIBLE),
             "Unsupported or conflicting Device Tree compatible")
    if report.get("method") == "device_tree_model":
        _require(type(model) is str and model.strip().casefold() in MODELS,
                 "Device Tree model is not an exact reviewed PYNQ-Z2 name")
    elif report.get("method") == "reviewed_enrollment":
        _require(model is None and compatible == COMPATIBLE,
                 "Enrollment requires absent model and compatible Zynq platform")
        for name in ("enrollment_sha256", "physical_evidence_sha256", "machine_id_sha256"):
            _require(_digest(report.get(name)), "Missing enrollment binding: " + name)
        _require(report.get("base_bin_sha256") == RECOVERY_BIN_SHA256
                 and report.get("base_hwh_sha256") == RECOVERY_HWH_SHA256,
                 "Enrollment recovery fingerprints differ")
    else:
        raise SafetyError("Unsupported board identity method")


def _properties(device_tree: Path):
    try:
        raw = (device_tree/"model").read_bytes()
    except FileNotFoundError:
        model = None
    else:
        parts = _strings(raw)
        _require(len(parts) == 1 and bool(parts[0].strip()), "Malformed Device Tree model")
        model = parts[0]
    try:
        raw = (device_tree/"compatible").read_bytes()
    except FileNotFoundError:
        compatible = []
    else:
        compatible = _strings(raw)
    _require(compatible in ([], COMPATIBLE), "Unsupported or incompatible Device Tree board")
    return model, compatible


def verify(*, device_tree=Path("/proc/device-tree"), machine_id=Path("/etc/machine-id"),
           board_record=None, board_record_sha256=None, board_physical_evidence=None,
           board_base_bin=None, board_base_hwh=None) -> dict:
    """No MMIO, device import, network or writes. Unreadable evidence fails closed."""
    model, compatible = _properties(device_tree)
    report = dict(schema_version=1, board="PYNQ-Z2", model=model, compatible=compatible)
    supplied = (board_record, board_record_sha256, board_physical_evidence, board_base_bin, board_base_hwh)
    if model is not None:
        # Explicit conflicting model cannot be overridden by a record or flag.
        report["method"] = "device_tree_model"
        validate_report(report)
        _require(not any(x is not None for x in supplied),
                 "Enrollment inputs are only supported when model is absent")
        return report
    _require(compatible == COMPATIBLE, "Missing board model and supported SoC compatibility")
    _require(all(x is not None for x in supplied) and _digest(board_record_sha256),
             "Generic compatible alone is insufficient; externally pinned enrollment required")
    data = board_record.read_bytes()
    _require(hashlib.sha256(data).hexdigest() == board_record_sha256, "Enrollment digest mismatch")
    record = json.loads(data, object_pairs_hook=_unique_keys)
    _require(type(record) is dict and type(record.get("schema_version")) is int
             and record["schema_version"] == 1 and record.get("board") == "PYNQ-Z2"
             and record.get("physical_board_marking_verified") is True,
             "Enrollment lacks independently reviewed PYNQ-Z2 physical identification")
    _require(board_physical_evidence.is_file() and board_physical_evidence.stat().st_size > 0,
             "Physical enrollment evidence must be a nonempty retained file")
    raw_id = machine_id.read_text().strip()
    _require(re.fullmatch(r"[a-f0-9]{32}", raw_id) is not None and raw_id != "0"*32,
             "Missing/invalid current machine-id")
    bindings = {
        "machine_id_sha256": hashlib.sha256(raw_id.encode("ascii")).hexdigest(),
        "physical_evidence_sha256": sha256_file(board_physical_evidence),
        "base_bin_sha256": sha256_file(board_base_bin),
        "base_hwh_sha256": sha256_file(board_base_hwh),
    }
    for name, value in bindings.items():
        _require(_digest(record.get(name)) and record[name] == value,
                 "Enrollment/current evidence mismatch: " + name)
    report.update(method="reviewed_enrollment", enrollment_sha256=board_record_sha256, **bindings)
    validate_report(report)
    return report

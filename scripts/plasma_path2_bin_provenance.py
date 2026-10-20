"""F1-B Path 2 BIT -> raw BIN provenance; files and claims only, never device I/O.

A conversion digest cannot prove Bootgen ran. Execution provenance MUST be
separately authenticated by a trusted executor before a target may be armed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pl.hil.swd04 import staging

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class ProvenanceDenied(ValueError):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise ProvenanceDenied(reason)


def _sha(value: object, width: int = 64) -> bool:
    return type(value) is str and (HEX40 if width == 40 else HEX64).fullmatch(value) is not None


def read_pinned_file(path: Path, expected: str, *, max_bytes: int) -> bytes:
    require(_sha(expected), "INVALID_EXPECTED_DIGEST")
    require(isinstance(path, Path) and path.is_file() and not path.is_symlink(),
            "PINNED_ARTIFACT_MISSING")
    size = path.stat().st_size
    require(0 < size <= max_bytes, "ARTIFACT_SIZE_DENIED")
    data = path.read_bytes()
    require(len(data) == size and hashlib.sha256(data).hexdigest() == expected,
            "PINNED_ARTIFACT_HASH_MISMATCH")
    return data


def verify_f1b_conversion(*, bit: Path, hwh: Path, firmware: Path,
                          build_receipt: dict, hwh_sha256: str,
                          bin_sha256: str, bootgen_receipt: dict) -> dict:
    """Verify distinct hashes, actual bytes, and bounded provenance fields.

    No raw Build Receipt or Bootgen JSON can independently authenticate itself.
    The privileged target must additionally verify provenance from an
    independent, reviewed source before installing the image.
    """
    require(type(build_receipt) is dict and
            set(build_receipt) == {"stage", "status", "source_sha",
                                   "profile_id", "artifact_sha256",
                                   "evidence_sha256"} and
            build_receipt["stage"] == "build" and build_receipt["status"] == "PASS" and
            build_receipt["profile_id"] == "f1b-site1-v1" and
            _sha(build_receipt["source_sha"], 40) and
            _sha(build_receipt["artifact_sha256"]) and
            _sha(build_receipt["evidence_sha256"]) and
            _sha(hwh_sha256) and _sha(bin_sha256),
            "BUILD_PROVENANCE_DENIED")
    require(type(bootgen_receipt) is dict and set(bootgen_receipt) == {
                "schema", "source_sha", "bit_sha256", "hwh_sha256",
                "bin_sha256", "tool_version", "execution_evidence_sha256",
                "authentication_status"} and
            bootgen_receipt["schema"] == "plasma.path2.bootgen.provenance.v1" and
            bootgen_receipt["source_sha"] == build_receipt["source_sha"] and
            bootgen_receipt["bit_sha256"] == build_receipt["artifact_sha256"] and
            bootgen_receipt["hwh_sha256"] == hwh_sha256 and
            bootgen_receipt["bin_sha256"] == bin_sha256 and
            bootgen_receipt["tool_version"] == "2026.1" and
            _sha(bootgen_receipt["execution_evidence_sha256"]) and
            bootgen_receipt["authentication_status"] == "EXTERNALLY_VERIFIED",
            "BOOTGEN_EXECUTION_NOT_AUTHENTICATED")
    bit_data = read_pinned_file(bit, build_receipt["artifact_sha256"],
                                max_bytes=16_000_000)
    read_pinned_file(hwh, hwh_sha256, max_bytes=4_000_000)
    bin_data = read_pinned_file(firmware, bin_sha256, max_bytes=16_000_000)
    try:
        payload = staging.bit_payload(bit_data)
    except (ValueError, IndexError) as exc:
        raise ProvenanceDenied("BIT_ENVELOPE_DENIED") from exc
    expected = b"".join(payload[i:i+4][::-1] for i in range(0, len(payload), 4))
    expected += bytes.fromhex("00000020")
    require(bin_data == expected, "BIT_BIN_PAYLOAD_MISMATCH")
    return {
        "source_sha": build_receipt["source_sha"],
        "bit_sha256": build_receipt["artifact_sha256"],
        "hwh_sha256": hwh_sha256,
        "bin_sha256": bin_sha256,
        "build_qualification_sha256": build_receipt["evidence_sha256"],
        "bootgen_evidence_sha256": bootgen_receipt["execution_evidence_sha256"],
        "scope": "BYTE_EQUIVALENCE_ONLY",
        "physical_load": "NOT_RUN",
    }

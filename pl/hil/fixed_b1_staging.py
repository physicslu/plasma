"""F1-B BIT -> Zynq FPGA-Manager BIN, OFFLINE ONLY.

Uses the already-reviewed SWD-04 Xilinx BIT header parser and its exact
observed word-swap + one trailing NOP convention. This is not bootgen output,
hardware admission, a /lib/firmware installer, or a FPGA Manager loader.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from pl.hil.fixed_b1_contract import (
    B1Blocked, F1_BIT_SHA256, F1_HWH_SHA256, CANDIDATE_BIN_SHA256,
)
from pl.hil.swd04.staging import bit_payload

HOST_SOURCE_SHA = "5473176a5ca6a04f9fe9359b4406c38208f9498f"
EXPECTED_PAYLOAD_BYTES = 4045564
EXPECTED_BIN_BYTES = EXPECTED_PAYLOAD_BYTES + 4
TAIL_NOP = bytes.fromhex("00000020")
BIT_SUFFIX = "/system_wrapper.bit"
HWH_SUFFIX = "/system.hwh"
HOST_RECEIPT = "_temp/plasma-path2-vivado-host-receipt.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_candidate(bit: bytes, hwh: bytes, receipt: dict) -> tuple[bytes, dict]:
    """Pinned real artifact bytes; reject unrelated build or malformed output."""
    if (digest(bit) != F1_BIT_SHA256 or digest(hwh) != F1_HWH_SHA256
            or receipt.get("source_sha") != HOST_SOURCE_SHA
            or receipt.get("bit_sha256") != F1_BIT_SHA256
            or receipt.get("hwh_sha256") != F1_HWH_SHA256
            or receipt.get("execution_path") != "path2-cli"
            or receipt.get("physical_image_loaded") != "NOT_RUN"):
        raise B1Blocked("B1_HOST_BUILD_PROVENANCE_MISMATCH")
    payload = bit_payload(bit)  # also checks target part and tagged header
    if len(payload) != EXPECTED_PAYLOAD_BYTES:
        raise B1Blocked("B1_BIT_PAYLOAD_SIZE_MISMATCH")
    result = b"".join(payload[i:i+4][::-1] for i in range(0, len(payload), 4)) + TAIL_NOP
    if (len(result) != EXPECTED_BIN_BYTES
            or digest(result) != CANDIDATE_BIN_SHA256
            or result.find(bytes.fromhex("665599aa")) != 48):
        raise B1Blocked("B1_DERIVED_BIN_FORMAT_OR_DIGEST_MISMATCH")
    manifest = {
        "schema": "plasma.f1b.b1.candidate-bin.offline.v1",
        "source_sha": HOST_SOURCE_SHA,
        "bit_sha256": F1_BIT_SHA256, "hwh_sha256": F1_HWH_SHA256,
        "candidate_bin_sha256": CANDIDATE_BIN_SHA256,
        "candidate_bin_bytes": len(result),
        "conversion": "tagged_bit_payload_reverse_each_32bit_word_plus_one_zynq_nop",
        "bootgen_independent_confirmation": "NOT_RUN",
        "fpga_manager_load": "NOT_RUN",
        "z2_hil": "NOT_RUN",
        "hardware_go": False,
    }
    return result, manifest


def from_evidence_zip(archive: Path) -> tuple[bytes, dict]:
    """Do not extract attacker-controlled archive member paths."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        exact = lambda suffix: [x for x in names if x.endswith(suffix)]
        bits, hwhs, receipts = exact(BIT_SUFFIX), exact(HWH_SUFFIX), exact(HOST_RECEIPT)
        if len(bits) != 1 or len(hwhs) != 1 or len(receipts) != 1:
            raise B1Blocked("B1_EVIDENCE_MEMBERS_MISSING_OR_AMBIGUOUS")
        bit = z.read(bits[0])
        hwh = z.read(hwhs[0])
        receipt = json.loads(z.read(receipts[0]))
    if not isinstance(receipt, dict):
        raise B1Blocked("B1_EVIDENCE_RECEIPT_INVALID")
    return derive_candidate(bit, hwh, receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise B1Blocked("B1_OUTPUT_ALREADY_EXISTS")
    blob, receipt = from_evidence_zip(args.evidence_zip)
    # Never copy the generated BIN into firmware directories here.
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    (args.output_dir / "f1b-candidate.bin").write_bytes(blob)
    (args.output_dir / "conversion-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("F1B_DERIVED_BIN_HOST_ONLY_NOT_BOOTGEN_QUALIFIED")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

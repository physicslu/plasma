"""Offline pinned-source check for a *reference* Linux Zynq FPGA Manager.

This code opens only caller-supplied ordinary files. It neither inspects the
running target nor controls a device. Matching Git blob contents does not
prove a source tree's commit membership, a deployed kernel binary, or AXI
isolation. All outcomes forbid FPGA load and retain M1 NO-GO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


class EvidenceError(ValueError):
    """Unsafe or malformed lineage evidence; never promote to hardware GO."""


REFERENCE_COMMIT = "e475cc1c9432587298212570c2af2be66b820c41"
REFERENCE_FILES = {
    "drivers/fpga/zynq-fpga.c": "96611d424a104ed25b3d618688fd806cff430a1e",
    "drivers/fpga/fpga-mgr.c": "6e8c45974f289917fa6b5b4b6544e9bf644cdc31",
    "drivers/fpga/fpga-region.c": "b364a929425ce9b54345a0098e28837894359495",
    "drivers/fpga/of-fpga-region.c": "48ac7617296e83b7ad4eafeba8ad2c730e951e09",
}
TARGET_RELEASE = "6.6.10-xilinx-v2024.1-g3c0eca68c652"
TARGET_CONFIG_SHA256 = "842cd4d4f17487123ca33c7b04f593dc85340df11da59c2059ccc12b699a5169"
MAX_REFERENCE_FILE_BYTES = 1_000_000


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceError(message)


def validate_reference_manifest(manifest: object) -> dict:
    """Reject a promoted/forged manifest; return a no-authority review only."""
    require(type(manifest) is dict, "expected JSON object")
    require(manifest.get("schema") == "plasma-z2-kernel-lineage-reference-v1",
            "schema mismatch")
    require(manifest.get("evidence_class") == "PUBLIC_REFERENCE_NOT_TARGET_ATTESTATION",
            "reference cannot be claimed to be an attestation")
    target = manifest.get("target_observation")
    reference = manifest.get("public_reference")
    require(type(target) is dict and type(reference) is dict,
            "missing source/target evidence")
    expected_target = {
        "board": "PYNQ-Z2",
        "kernel_release": TARGET_RELEASE,
        "commit_prefix": "3c0eca68c652",
        "config_sha256": TARGET_CONFIG_SHA256,
        "matching_source_commit": None,
        "matching_source_patchset_sha256": None,
        "deployed_kernel_binary_sha256": None,
        "deployed_dtb_sha256": None,
        "source_to_binary_attested": False,
        "registered_bridge_count": 0,
    }
    for key, value in expected_target.items():
        require(type(target.get(key)) is type(value) and target[key] == value,
                "target observed/unresolved field changed: " + key)
    expected_reference = {
        "repository": "Xilinx/linux-xlnx",
        "tag": "xilinx-v2024.1",
        "commit": REFERENCE_COMMIT,
        "files": REFERENCE_FILES,
    }
    for key, value in expected_reference.items():
        require(type(reference.get(key)) is type(value) and reference[key] == value,
                "public reference pin mismatch: " + key)
    for key, value in (
        ("source_classification", "REFERENCE_ONLY"),
        ("axi_drain_measured", False),
        ("hardware_ready", False),
        ("reload_authorized", False),
    ):
        require(type(manifest.get(key)) is type(value) and manifest[key] == value,
                "unsafe reference promotion: " + key)
    return {
        "verdict": "M1_NO_GO",
        "reference_commit": REFERENCE_COMMIT,
        "source_to_binary_match": "UNRESOLVED",
        "target_source_commit": None,
        "registered_bridge_count": 0,
        "hardware_ready": False,
        "reload_authorized": False,
        "reference_files_verified": False,
        "blockers": [
            "TARGET_KERNEL_COMMIT_NOT_RESOLVED",
            "TARGET_KERNEL_PATCHSET_AND_BINARY_ATTESTATION_MISSING",
            "TARGET_DTB_BINARY_NOT_ATTESTED",
            "MANAGER_FIRMWARE_PATH_BYPASSES_REGION_BRIDGE_LIST",
            "NO_REGISTERED_FPGA_BRIDGE_IN_OBSERVED_Z2_INVENTORY",
            "AXI_MASTER_QUIESCENCE_AND_INFLIGHT_DRAIN_NOT_MEASURED",
            "EXTERNAL_ELECTRICAL_SAFE_STATE_AND_RECOVERY_NOT_QUALIFIED",
        ],
    }


def git_blob_object_id(path: Path) -> str:
    """Return *Git SHA-1 blob object ID* of a bounded regular file.

    This is NOT SHA-256 and never proves commit ancestry. Reject symlinks
    at every component; even a matching reference blob is not a target binary.
    """
    require(path.is_file() and not path.is_symlink(), "source must be regular file")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EvidenceError("source file cannot be read") from exc
    require(len(data) <= MAX_REFERENCE_FILE_BYTES,
            "source file exceeds reference size ceiling")
    h = hashlib.sha1()
    h.update(b"blob " + str(len(data)).encode("ascii") + b"\x00")
    h.update(data)
    return h.hexdigest()


def verify_reference_tree(root: Path, files: dict[str, str]) -> None:
    """Check complete Git blob bytes, excluding symlink escapes and path drift."""
    require(type(files) is dict and 0 < len(files) <= 16,
            "source manifest missing files")
    require(root.is_dir() and not root.is_symlink(),
            "source root must be a real directory")
    for name, sha in files.items():
        require(type(name) is str and
                re.fullmatch(r"(?:[a-z0-9-]+/)+[a-z0-9-]+\.c", name) is not None
                and ".." not in name and name.startswith("drivers/fpga/"),
                "unsafe source path")
        require(type(sha) is str and
                re.fullmatch("[0-9a-f]{40}", sha) is not None,
                "invalid Git blob object ID")
        item = root
        for component in name.split("/"):
            item = item / component
            require(not item.is_symlink(),
                    "symlink cannot be used in reference source")
        require(item.is_file() and git_blob_object_id(item) == sha,
                "missing or drifted source blob: " + name)


def review(manifest: object, *, reference_root: Path | None = None) -> dict:
    result = validate_reference_manifest(manifest)
    if reference_root is not None:
        verify_reference_tree(reference_root, REFERENCE_FILES)
        result["reference_files_verified"] = True
    # A Git blob SHA identifies file bytes only. Even 4/4 matches DO NOT
    # authenticate the Git commit tree, source patches, deployed binary,
    # Device Tree, current boot, AXI drain, or physical isolation.
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline public kernel reference check; never FPGA load authority")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--reference-root", type=Path, default=None,
                        help="Optional local Xilinx source tree, not the target /sys")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        response = review(manifest, reference_root=args.reference_root)
    except (EvidenceError, OSError, ValueError) as exc:
        response = {
            "verdict": "M1_NO_GO",
            "hardware_ready": False,
            "reload_authorized": False,
            "reference_files_verified": False,
            "error_class": type(exc).__name__,
        }
        print(json.dumps(response, sort_keys=True))
        return 2
    print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

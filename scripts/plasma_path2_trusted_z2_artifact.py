#!/usr/bin/env python3
"""Trusted Path 2 source-pinned Z2 kit admission; no runtime deployment.

This module runs only in the trusted GitHub Actions step. PR candidate code never
receives GH_TOKEN/GITHUB_TOKEN. It verifies one reviewed GitHub Actions artifact
identity and its complete downloaded kit bytes before any SWPC/Z2 operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPOSITORY = "physicslu/plasma"
SOURCE_PR = 1299
RUN_ID = 41792402221
ARTIFACT_ID = 13303674147
ARTIFACT_NAME = "plasma-z2-ps-kit-0.2.1-7ef3509265bc"
RUN_HEAD_SHA = "d53953e517f27582c2071fc84795f21cc89de77c"
SOURCE_MERGE_SHA = "7ef3509265bc4773ca8629eec99727f94646ab7b"
ARTIFACT_ZIP_SHA256 = "d538c2cb7a671b3b60dd7dcbc4fb17189de801d498523b1f872a1d2f72f39168"
KIT_SHA256 = "e83dbb429c795b43cbb5556c76b2d488ffe454257e6fdb5ef952c9a4316283f8"


class AdmissionError(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise AdmissionError(reason)


def _read_json(path: Path) -> dict:
    _require(path.is_file() and not path.is_symlink() and
             path.stat().st_size < 512_000, "METADATA_FILE_INVALID")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise AdmissionError("METADATA_JSON_INVALID") from exc
    _require(isinstance(data, dict), "METADATA_OBJECT_REQUIRED")
    return data


def verify_metadata(run: dict, listing: dict) -> dict:
    _require(run.get("id") == RUN_ID and run.get("head_sha") == RUN_HEAD_SHA,
             "RUN_SOURCE_IDENTITY_MISMATCH")
    _require(run.get("status") == "completed" and
             run.get("conclusion") == "success" and
             run.get("event") == "pull_request",
             "RUN_NOT_QUALIFIED")
    _require(isinstance(run.get("repository"), dict) and
             run["repository"].get("full_name") == REPOSITORY,
             "RUN_REPOSITORY_MISMATCH")
    prs = run.get("pull_requests", [])
    _require(isinstance(prs, list) and any(
        isinstance(pr, dict) and pr.get("number") == SOURCE_PR
        for pr in prs), "RUN_PR_BINDING_MISSING")
    records = listing.get("artifacts")
    _require(isinstance(records, list) and len(records) <= 100,
             "ARTIFACT_LIST_INVALID")
    matches = [r for r in records if isinstance(r, dict) and
               r.get("id") == ARTIFACT_ID and r.get("name") == ARTIFACT_NAME]
    _require(len(matches) == 1, "PINNED_ARTIFACT_NOT_FOUND")
    artifact = matches[0]
    _require(artifact.get("expired") is False and
             artifact.get("digest") == "sha256:" + ARTIFACT_ZIP_SHA256 and
             type(artifact.get("size_in_bytes")) is int and
             0 < artifact["size_in_bytes"] < 1_000_000_000,
             "ARTIFACT_METADATA_MISMATCH")
    producer = artifact.get("workflow_run")
    _require(isinstance(producer, dict) and
             producer.get("id") == RUN_ID and
             producer.get("head_sha") == RUN_HEAD_SHA,
             "ARTIFACT_RUN_BINDING_MISMATCH")
    return {
        "result": "TRUSTED_ARTIFACT_METADATA_PASS",
        "repository": REPOSITORY, "run_id": RUN_ID,
        "artifact_id": ARTIFACT_ID, "artifact_name": ARTIFACT_NAME,
        "producer_head_sha": RUN_HEAD_SHA,
        "source_merge_sha": SOURCE_MERGE_SHA,
        "artifact_zip_sha256": ARTIFACT_ZIP_SHA256,
        "no_download": True, "no_install": True, "no_dut_action": True,
    }


def verify_archive(directory: Path) -> dict:
    _require(directory.is_dir() and not directory.is_symlink(),
             "TRUSTED_ARTIFACT_DIR_INVALID")
    archive = directory / (ARTIFACT_NAME + ".tar.gz")
    sidecar = directory / (archive.name + ".sha256")
    _require(archive.is_file() and not archive.is_symlink() and
             sidecar.is_file() and not sidecar.is_symlink() and
             0 < archive.stat().st_size < 1_000_000_000 and
             sidecar.stat().st_size <= 256, "KIT_FILES_INVALID")
    try:
        sidecar_line = sidecar.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise AdmissionError("KIT_SIDECAR_INVALID") from exc
    _require(sidecar_line == f"{KIT_SHA256}  {archive.name}",
             "KIT_SIDECAR_MISMATCH")
    digest = hashlib.sha256()
    try:
        with archive.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise AdmissionError("KIT_UNREADABLE") from exc
    _require(digest.hexdigest() == KIT_SHA256, "KIT_SHA256_MISMATCH")
    return {
        "result": "TRUSTED_ARTIFACT_BYTES_PASS", "run_id": RUN_ID,
        "artifact_id": ARTIFACT_ID, "artifact_name": ARTIFACT_NAME,
        "producer_head_sha": RUN_HEAD_SHA, "source_merge_sha": SOURCE_MERGE_SHA,
        "kit_sha256": KIT_SHA256, "no_install": True, "no_dut_action": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    metadata = sub.add_parser("verify-metadata")
    metadata.add_argument("--run-json", type=Path, required=True)
    metadata.add_argument("--artifacts-json", type=Path, required=True)
    metadata.add_argument("--github-output", type=Path, required=True)
    archive = sub.add_parser("verify-archive")
    archive.add_argument("--directory", type=Path, required=True)
    archive.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-metadata":
            receipt = verify_metadata(_read_json(args.run_json),
                                      _read_json(args.artifacts_json))
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write(f"run_id={RUN_ID}\nartifact_name={ARTIFACT_NAME}\n")
        else:
            receipt = verify_archive(args.directory)
            args.receipt.write_text(json.dumps(receipt, sort_keys=True) + "\n",
                                    encoding="utf-8")
    except (AdmissionError, OSError) as exc:
        reason = str(exc) if isinstance(exc, AdmissionError) else "TRUSTED_IO_UNAVAILABLE"
        print(json.dumps({"result": "TRUSTED_ARTIFACT_BLOCKED",
                          "reason": reason}), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

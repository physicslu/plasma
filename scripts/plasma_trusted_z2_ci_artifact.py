#!/usr/bin/env python3
"""Trusted GitHub Actions -> Z2 PS Kit handoff (no token enters Path 3).

Only the trusted Dispatcher calls this helper. An owner-authenticated Work
Order supplies a source commit and successful CI run ID, never a download URL
or arbitrary artifact filename. Both the GitHub ZIP and its payload are
verified before publishing any local paths to a Codex child.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import sys
import tarfile
import tempfile
import zipfile

REPOSITORY = "physicslu/plasma"
WORKFLOW = ".github/workflows/z2-ps-release.yml"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
KIT_NAME = re.compile(
    r"plasma-z2-ps-kit-(?P<version>[0-9]+\.[0-9]+\.[0-9]+"
    r"(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?)-(?P<prefix>[0-9a-f]{12})\Z"
)
MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_KIT_BYTES = 512 * 1024 * 1024


class ArtifactDenied(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise ArtifactDenied(reason)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    need(path.is_file() and not path.is_symlink() and
         path.stat().st_size <= 1024 * 1024, "METADATA_FILE_INVALID")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise ArtifactDenied("METADATA_JSON_INVALID") from exc
    need(type(value) is dict, "METADATA_OBJECT_DENIED")
    return value


def admit(run: dict, listing: dict, *, source_sha: str, run_id: int) -> dict:
    need(type(source_sha) is str and SHA40.fullmatch(source_sha) is not None,
         "SOURCE_SHA_INVALID")
    need(type(run_id) is int and run_id > 0, "RUN_ID_INVALID")
    need(type(run) is dict and type(listing) is dict, "RUN_METADATA_INVALID")
    repo = run.get("repository")
    head_repo = run.get("head_repository")
    need(type(repo) is dict and repo.get("full_name") == REPOSITORY and
         type(repo.get("id")) is int and type(head_repo) is dict and
         head_repo.get("full_name") == REPOSITORY, "RUN_REPOSITORY_DENIED")
    need(type(run.get("id")) is int and run["id"] == run_id and
         run.get("head_sha") == source_sha and
         run.get("head_branch") == "main" and
         run.get("event") == "push" and
         run.get("path") == WORKFLOW and
         run.get("status") == "completed" and
         run.get("conclusion") == "success", "RUN_PROVENANCE_DENIED")
    records = listing.get("artifacts")
    need(type(listing.get("total_count")) is int and
         0 <= listing["total_count"] <= 100 and
         type(records) is list and
         len(records) == listing["total_count"], "ARTIFACT_LIST_INCOMPLETE")
    matches = []
    for item in records:
        if type(item) is not dict or type(item.get("name")) is not str:
            continue
        name_match = KIT_NAME.fullmatch(item["name"])
        if name_match is not None and name_match["prefix"] == source_sha[:12]:
            matches.append(item)
    need(len(matches) == 1, "KIT_ARTIFACT_NOT_UNIQUE")
    item = matches[0]
    producer = item.get("workflow_run")
    digest = item.get("digest")
    need(item.get("expired") is False and type(item.get("id")) is int and
         item["id"] > 0 and type(item.get("size_in_bytes")) is int and
         0 < item["size_in_bytes"] <= MAX_ZIP_BYTES and
         type(digest) is str and digest.startswith("sha256:") and
         SHA256.fullmatch(digest[7:]) is not None and
         type(producer) is dict and producer.get("id") == run_id and
         producer.get("head_sha") == source_sha and
         producer.get("head_branch") == "main" and
         producer.get("repository_id") == repo["id"],
         "KIT_ARTIFACT_PROVENANCE_DENIED")
    return {
        "status": "TRUSTED_CI_ARTIFACT_ADMITTED",
        "repository": REPOSITORY,
        "source_sha": source_sha,
        "run_id": run_id,
        "artifact_id": item["id"],
        "artifact_name": item["name"],
        "zip_sha256": digest[7:],
    }


def extract_verified_zip(path: Path, admission: dict, destination: Path) -> tuple[Path, Path, str]:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size <= MAX_ZIP_BYTES, "ARTIFACT_ZIP_INVALID")
    need(sha256(path) == admission["zip_sha256"], "ARTIFACT_ZIP_SHA256_MISMATCH")
    name = admission["artifact_name"] + ".tar.gz"
    expected = {name, name + ".sha256"}
    need(not destination.exists() and not destination.is_symlink(),
         "ARTIFACT_DESTINATION_EXISTS")
    destination.mkdir(mode=0o700, parents=True)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            need(len(infos) == 2 and {i.filename for i in infos} == expected,
                 "ARTIFACT_ZIP_FILE_SET_DENIED")
            for info in infos:
                filetype = stat.S_IFMT(info.external_attr >> 16)
                need(not info.is_dir() and filetype in (0, stat.S_IFREG) and
                     0 < info.file_size <= MAX_KIT_BYTES and
                     not (info.flag_bits & 0x1), "ARTIFACT_ZIP_MEMBER_DENIED")
                if info.filename.endswith(".sha256"):
                    need(info.file_size <= 256, "KIT_SIDECAR_TOO_LARGE")
                with archive.open(info) as source, (destination / info.filename).open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
    except (OSError, ValueError, zipfile.BadZipFile, EOFError) as exc:
        if isinstance(exc, ArtifactDenied):
            raise
        raise ArtifactDenied("ARTIFACT_ZIP_EXTRACT_DENIED") from exc
    artifact = destination / name
    sidecar = destination / (name + ".sha256")
    need(artifact.stat().st_size <= MAX_KIT_BYTES, "KIT_TOO_LARGE")
    try:
        sidecar_text = sidecar.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise ArtifactDenied("KIT_SIDECAR_INVALID") from exc
    kit_sha = sha256(artifact)
    need(sidecar_text == f"{kit_sha}  {name}", "KIT_SIDECAR_MISMATCH")
    return artifact, sidecar, kit_sha


def verify_kit_source(artifact: Path, sidecar: Path,
                      source_sha: str, artifact_name: str,
                      *, helper: Path) -> None:
    # Reuse existing trusted full kit verifier (safe tar extraction, SHA256SUMS,
    # inner artifact file set). A sidecar alone is not sufficient provenance.
    spec = importlib.util.spec_from_file_location("plasma_ci_kit_verifier", helper)
    need(spec is not None and spec.loader is not None and helper.is_file(),
         "KIT_VERIFIER_NOT_FOUND")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="plasma-trusted-kit-") as scratch:
        verified = module.verify_kit(
            artifact, sidecar=sidecar, extract_to=Path(scratch) / "extract"
        )
        need(verified.root.name == artifact_name, "KIT_IDENTITY_MISMATCH")
        # Bind the exact full commit, not merely the 12-char release prefix.
        with tarfile.open(verified.ppu_artifact, "r:gz") as release:
            member = release.getmember("plasma-release/release.json")
            need(member.isfile() and 0 < member.size <= 8192,
                 "PPU_RELEASE_MANIFEST_DENIED")
            stream = release.extractfile(member)
            need(stream is not None, "PPU_RELEASE_MANIFEST_DENIED")
            with stream:
                manifest = json.loads(stream.read(8193))
        need(type(manifest) is dict and
             manifest.get("git_sha") == source_sha and
             manifest.get("role") == "ppu" and
             manifest.get("target") == "linux-armv7l",
             "PPU_SOURCE_IDENTITY_MISMATCH")
        name_match = KIT_NAME.fullmatch(artifact_name)
        need(name_match is not None and
             manifest.get("product_version") == name_match["version"],
             "PPU_RELEASE_VERSION_MISMATCH")


def verify_download(zip_path: Path, admission: dict, destination: Path,
                    *, helper: Path) -> dict:
    need(admission.get("status") == "TRUSTED_CI_ARTIFACT_ADMITTED" and
         admission.get("repository") == REPOSITORY and
         type(admission.get("source_sha")) is str and
         SHA40.fullmatch(admission["source_sha"]) is not None and
         type(admission.get("run_id")) is int and admission["run_id"] > 0 and
         type(admission.get("artifact_id")) is int and admission["artifact_id"] > 0 and
         type(admission.get("artifact_name")) is str and
         KIT_NAME.fullmatch(admission["artifact_name"]) is not None and
         admission["artifact_name"].endswith(admission["source_sha"][:12]) and
         type(admission.get("zip_sha256")) is str and
         SHA256.fullmatch(admission["zip_sha256"]) is not None,
         "ARTIFACT_ADMISSION_INVALID")
    artifact, sidecar, kit_sha = extract_verified_zip(zip_path, admission, destination)
    verify_kit_source(artifact, sidecar, admission["source_sha"],
                      admission["artifact_name"], helper=helper)
    return {
        **admission,
        "status": "TRUSTED_CI_ARTIFACT_VERIFIED",
        "kit_sha256": kit_sha,
        "kit_path": str(artifact.resolve(strict=True)),
        "sidecar_path": str(sidecar.resolve(strict=True)),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    metadata = sub.add_parser("admit")
    metadata.add_argument("--run-json", type=Path, required=True)
    metadata.add_argument("--artifacts-json", type=Path, required=True)
    metadata.add_argument("--source-sha", required=True)
    metadata.add_argument("--run-id", type=int, required=True)
    metadata.add_argument("--receipt", type=Path, required=True)
    metadata.add_argument("--github-output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--admission", type=Path, required=True)
    verify.add_argument("--zip", type=Path, required=True)
    verify.add_argument("--destination", type=Path, required=True)
    verify.add_argument("--helper", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--github-env", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "admit":
            record = admit(read_json(args.run_json), read_json(args.artifacts_json),
                           source_sha=args.source_sha, run_id=args.run_id)
            args.receipt.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write(f"artifact_id={record['artifact_id']}\n")
        else:
            record = verify_download(args.zip, read_json(args.admission),
                                     args.destination, helper=args.helper)
            args.receipt.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
            with args.github_env.open("a", encoding="utf-8") as env:
                env.write(f"PLASMA_Z2_KIT_ARTIFACT_PATH={record['kit_path']}\n")
                env.write(f"PLASMA_Z2_KIT_SIDECAR_PATH={record['sidecar_path']}\n")
    except (ArtifactDenied, OSError, ValueError, KeyError, tarfile.TarError) as exc:
        reason = str(exc) if isinstance(exc, ArtifactDenied) else "ARTIFACT_VERIFICATION_FAILED"
        print(json.dumps({"status": "TRUSTED_CI_ARTIFACT_BLOCKED", "reason": reason}),
              file=sys.stderr)
        return 2
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

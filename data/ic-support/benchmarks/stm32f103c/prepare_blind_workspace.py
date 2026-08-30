#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parents[3]
DEFAULT_SOURCE_LOCK = HERE / "source-lock.json"
DEFAULT_CONTRACT = HERE / "extraction-contract.json"
DEFAULT_SCHEMA = HERE / "extraction-observed.schema.json"


class WorkspaceError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorkspaceError(f"{path}: top-level JSON must be an object")
    return value


def is_within(child: Path, parent: Path) -> bool:
    child = child.resolve()
    parent = parent.resolve()
    return child == parent or parent in child.parents


def require_command(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise WorkspaceError(f"required command not found: {name}")
    return found


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_integrity(path: Path, integrity: dict[str, Any]) -> None:
    algorithm = integrity.get("algorithm")
    expected = integrity.get("digest")
    if not isinstance(expected, str) or not expected:
        raise WorkspaceError(f"{path}: missing expected digest")
    if algorithm == "sha256":
        actual = sha256_file(path)
        if actual != expected:
            raise WorkspaceError(f"{path}: sha256 {actual} != locked {expected}")
        expected_size = integrity.get("byte_length")
        if isinstance(expected_size, int) and path.stat().st_size != expected_size:
            raise WorkspaceError(f"{path}: byte length {path.stat().st_size} != locked {expected_size}")
        return
    if algorithm == "git_blob_sha1":
        data = path.read_bytes()
        header = f"blob {len(data)}\0".encode()
        actual = hashlib.sha1(header + data).hexdigest()
        if actual != expected:
            raise WorkspaceError(f"{path}: git blob {actual} != locked {expected}")
        return
    raise WorkspaceError(f"{path}: unsupported integrity algorithm {algorithm!r}")


def download_locked_source(url: str, destination: Path) -> None:
    curl = require_command("curl")
    subprocess.run([
        curl, "--fail", "--location", "--silent", "--show-error",
        "--connect-timeout", "30", "--max-time", "300",
        "--output", str(destination), url
    ], check=True)


def materialize_git_blob(repo_root: Path, digest: str, destination: Path) -> None:
    git = require_command("git")
    result = subprocess.run(
        [git, "-C", str(repo_root), "cat-file", "blob", digest],
        check=True,
        stdout=subprocess.PIPE,
    )
    destination.write_bytes(result.stdout)


def source_filename(source: dict[str, Any]) -> str:
    source_id = source["source_id"]
    if "requested_url" in source:
        return f"{source_id}.pdf"
    path = source.get("path")
    suffix = Path(path).suffix if isinstance(path, str) else ""
    return f"{source_id}{suffix or '.bin'}"


def write_prompt(workspace: Path, contract: dict[str, Any]) -> None:
    targets = ", ".join(contract["targets"])
    text = f"""# STM32F103C blind extraction mission

This workspace is an isolated benchmark input bundle. Treat files in this workspace
as the complete evidence set. Do not use external knowledge, another Plasma checkout,
or any prior answer key.

Targets: {targets}

Read:
- `contracts/source-lock.json`
- `contracts/extraction-contract.json`
- `contracts/extraction-observed.schema.json`
- the locked source files under `inputs/`

For the ST PDF sources, searchable text produced from the exact locked PDF bytes is
available next to each PDF as `*.txt`. The original PDF remains present for provenance.

Produce `candidate.json` in this workspace. It must satisfy the candidate contract.
For facts not supported by the supplied evidence, use `null` or `unknown` where the
observed schema permits it. Do not guess. Profile relationships describe whether the
two targets require the same or different technical behavior; do not invent Plasma
profile IDs.

Before finishing:
1. report the exact locked source digests from `source-lock.json`;
2. set `extractor.name` to the actual model/Harness identity;
3. set `extractor.version` to a reproducible model/prompt/workflow identifier;
4. keep all output inside this workspace.
"""
    (workspace / "PROMPT.md").write_text(text, encoding="utf-8")


def prepare_workspace(
    workspace: Path,
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    source_lock_path: Path = DEFAULT_SOURCE_LOCK,
    contract_path: Path = DEFAULT_CONTRACT,
    schema_path: Path = DEFAULT_SCHEMA,
    source_cache: Path | None = None,
) -> None:
    repo_root = repo_root.resolve()
    workspace = workspace.expanduser().resolve()
    if is_within(workspace, repo_root):
        raise WorkspaceError("benchmark workspace must be outside the Plasma repository")
    if workspace.exists() and any(workspace.iterdir()):
        raise WorkspaceError(f"workspace is not empty: {workspace}")

    lock = load_json(source_lock_path)
    contract = load_json(contract_path)
    schema = load_json(schema_path)
    if lock.get("source_lock_id") != contract.get("source_lock_id"):
        raise WorkspaceError("source-lock and extraction contract IDs do not match")
    if schema.get("$id") != contract.get("observed_schema_id"):
        raise WorkspaceError("observed schema ID does not match extraction contract")

    inputs = workspace / "inputs"
    contracts = workspace / "contracts"
    inputs.mkdir(parents=True, exist_ok=True)
    contracts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_lock_path, contracts / "source-lock.json")
    shutil.copy2(contract_path, contracts / "extraction-contract.json")
    shutil.copy2(schema_path, contracts / "extraction-observed.schema.json")

    manifest_sources: list[dict[str, Any]] = []
    for source in lock.get("sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            raise WorkspaceError("invalid source-lock source entry")
        destination = inputs / source_filename(source)
        integrity = source.get("integrity")
        if not isinstance(integrity, dict):
            raise WorkspaceError(f"{source['source_id']}: integrity object required")

        if "requested_url" in source:
            if source_cache is not None:
                cached = source_cache / destination.name
                if not cached.is_file():
                    raise WorkspaceError(f"cached source missing: {cached}")
                shutil.copy2(cached, destination)
            else:
                download_locked_source(str(source["requested_url"]), destination)
        elif integrity.get("algorithm") == "git_blob_sha1":
            materialize_git_blob(repo_root, str(integrity["digest"]), destination)
        else:
            raise WorkspaceError(f"{source['source_id']}: unsupported source materialization")

        verify_integrity(destination, integrity)
        record: dict[str, Any] = {
            "source_id": source["source_id"],
            "file": f"inputs/{destination.name}",
            "algorithm": integrity["algorithm"],
            "digest": integrity["digest"],
        }
        if destination.suffix.lower() == ".pdf":
            pdftotext = require_command("pdftotext")
            text_path = destination.with_suffix(".txt")
            subprocess.run([pdftotext, "-layout", str(destination), str(text_path)], check=True)
            if not text_path.is_file() or text_path.stat().st_size == 0:
                raise WorkspaceError(f"{destination}: pdftotext produced no text")
            record["searchable_text"] = f"inputs/{text_path.name}"
            record["searchable_text_sha256"] = sha256_file(text_path)
        manifest_sources.append(record)

    manifest = {
        "schema_version": "0.1.0",
        "benchmark_id": lock["benchmark_id"],
        "source_lock_id": lock["source_lock_id"],
        "isolation": {
            "workspace_outside_repository": True,
            "repository_ground_truth_copied": False,
            "repository_profiles_copied": False,
            "repository_bindings_copied": False,
            "os_sandbox_enforced": False,
        },
        "sources": manifest_sources,
    }
    (workspace / "workspace-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    write_prompt(workspace, contract)

    git = require_command("git")
    subprocess.run([git, "-C", str(workspace), "init", "-q"], check=True)
    subprocess.run([git, "-C", str(workspace), "add", "."], check=True)
    subprocess.run([
        git, "-C", str(workspace),
        "-c", "user.name=Plasma Benchmark",
        "-c", "user.email=benchmark@invalid",
        "commit", "-q", "-m", "Prepare isolated STM32F103C benchmark inputs"
    ], check=True)


def verify_workspace(workspace: Path, repo_root: Path = DEFAULT_REPO_ROOT) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    if is_within(workspace, repo_root.resolve()):
        raise WorkspaceError("benchmark workspace must be outside the Plasma repository")
    manifest_path = workspace / "workspace-manifest.json"
    if not manifest_path.is_file():
        raise WorkspaceError(f"workspace manifest missing: {manifest_path}")
    manifest = load_json(manifest_path)
    for source in manifest.get("sources", []):
        if not isinstance(source, dict):
            raise WorkspaceError("workspace manifest source entry is invalid")
        relative = source.get("file")
        if not isinstance(relative, str):
            raise WorkspaceError("workspace manifest source file is invalid")
        path = workspace / relative
        verify_integrity(path, {"algorithm": source.get("algorithm"), "digest": source.get("digest")})
        searchable = source.get("searchable_text")
        if searchable:
            text_path = workspace / str(searchable)
            expected = source.get("searchable_text_sha256")
            if sha256_file(text_path) != expected:
                raise WorkspaceError(f"{text_path}: searchable text digest mismatch")
    return manifest


def resolve_harness_command() -> list[str]:
    dsh = shutil.which("dsh")
    if dsh:
        return [dsh, "--profile", "web"]
    npx = shutil.which("npx")
    if npx:
        probe = subprocess.run(
            [npx, "--offline", "--no-install", "--package=@deepseek-ai/dsh", "dsh", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return [npx, "--offline", "--no-install", "--package=@deepseek-ai/dsh", "dsh", "--profile", "web"]
    raise WorkspaceError(
        "DeepSeek Harness is unavailable; install @deepseek-ai/dsh explicitly before launching the benchmark"
    )


def harness_port() -> str:
    value = os.environ.get("PLASMA_HARNESS_PORT", "3080")
    if not value.isdigit() or not (1 <= int(value) <= 65535):
        raise WorkspaceError("PLASMA_HARNESS_PORT must be an integer from 1 to 65535")
    return value


def launch_harness(workspace: Path) -> None:
    workspace = workspace.expanduser().resolve()
    verify_workspace(workspace)
    command = resolve_harness_command() + ["--port", harness_port()]
    os.chdir(workspace)
    print(f"[ic-support-benchmark] Harness workspace: {workspace}", flush=True)
    print("[ic-support-benchmark] Read PROMPT.md and create a fresh Harness session.", flush=True)
    os.execvp(command[0], command)


def validate_candidate(workspace: Path) -> int:
    verify_workspace(workspace)
    candidate = workspace.expanduser().resolve() / "candidate.json"
    if not candidate.is_file():
        raise WorkspaceError(f"candidate missing: {candidate}")
    validator = HERE / "validate_extraction_candidate.py"
    return subprocess.run([sys.executable, str(validator), str(candidate)]).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and run the isolated STM32F103C blind extraction benchmark"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="materialize a clean source-locked workspace")
    prepare.add_argument("workspace", type=Path)
    prepare.add_argument("--source-cache", type=Path)
    harness = sub.add_parser("harness", help="launch DeepSeek Harness from the isolated workspace")
    harness.add_argument("workspace", type=Path)
    validate = sub.add_parser("validate", help="validate workspace/candidate against the answer key")
    validate.add_argument("workspace", type=Path)
    status = sub.add_parser("status", help="verify workspace source integrity")
    status.add_argument("workspace", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare_workspace(args.workspace, source_cache=args.source_cache)
            print(f"IC Support blind workspace READY: {args.workspace.expanduser().resolve()}")
            return 0
        if args.command == "harness":
            launch_harness(args.workspace)
            return 0
        if args.command == "validate":
            return validate_candidate(args.workspace)
        if args.command == "status":
            verify_workspace(args.workspace)
            print("IC Support blind workspace PASS: locked inputs are intact")
            return 0
    except (OSError, json.JSONDecodeError, WorkspaceError, subprocess.CalledProcessError) as exc:
        print(f"IC Support blind workspace FAIL: {exc}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

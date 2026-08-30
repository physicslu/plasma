#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER_PATH = HERE / "prepare_blind_workspace.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("ic_support_blind_workspace", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    runner = load_runner()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)

        catalog = b"manufacturer,icpn\nSTMicroelectronics,TEST123\n"
        digest = git_blob_sha(catalog)
        stored = subprocess.run(
            ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
            input=catalog,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.decode().strip()
        assert stored == digest

        contract_dir = root / "contracts"
        contract_dir.mkdir()
        lock_path = contract_dir / "source-lock.json"
        contract_path = contract_dir / "extraction-contract.json"
        schema_path = contract_dir / "extraction-observed.schema.json"

        write_json(
            lock_path,
            {
                "schema_version": "0.1.0",
                "source_lock_id": "test-lock",
                "benchmark_id": "test-benchmark",
                "targets": ["TEST123"],
                "sources": [
                    {
                        "source_id": "catalog",
                        "authority": "test",
                        "path": "catalog.csv",
                        "integrity": {
                            "algorithm": "git_blob_sha1",
                            "digest": digest,
                        },
                    }
                ],
            },
        )
        write_json(
            contract_path,
            {
                "schema_version": "0.1.0",
                "benchmark_id": "test-benchmark",
                "source_lock_id": "test-lock",
                "targets": ["TEST123"],
                "observed_schema_id": "plasma://test/extraction-observed",
            },
        )
        write_json(
            schema_path,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "plasma://test/extraction-observed",
                "type": "object",
            },
        )

        workspace = root / "isolated-workspace"
        runner.prepare_workspace(
            workspace,
            repo_root=repo,
            source_lock_path=lock_path,
            contract_path=contract_path,
            schema_path=schema_path,
        )
        assert (workspace / "PROMPT.md").is_file()
        assert (workspace / ".git").is_dir()
        copied = workspace / "inputs" / "catalog.csv"
        assert copied.read_bytes() == catalog
        manifest = runner.verify_workspace(workspace, repo_root=repo)
        assert manifest["isolation"]["workspace_outside_repository"] is True
        assert manifest["isolation"]["repository_ground_truth_copied"] is False
        assert manifest["isolation"]["os_sandbox_enforced"] is False

        copied.write_bytes(b"tampered")
        try:
            runner.verify_workspace(workspace, repo_root=repo)
        except runner.WorkspaceError:
            pass
        else:
            raise AssertionError("tampered locked input was accepted")

        inside = repo / "benchmark-workspace"
        try:
            runner.prepare_workspace(
                inside,
                repo_root=repo,
                source_lock_path=lock_path,
                contract_path=contract_path,
                schema_path=schema_path,
            )
        except runner.WorkspaceError:
            pass
        else:
            raise AssertionError("workspace inside Plasma repository was accepted")

    print("IC Support blind workspace tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

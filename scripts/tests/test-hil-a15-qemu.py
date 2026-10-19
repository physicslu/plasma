#!/usr/bin/env python3
"""Offline HIL-A1.5 negative tests. No QEMU, Docker, SWPC or target access."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    out = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(out)
    return out


probe = module("hil_a15_probe", "scripts/hil-a15-armv7-qemu.py")
policy = module("hil_a15_policy", "scripts/hil-a15-contract.py")


def fixture(parent: Path) -> tuple[Path, dict]:
    root = parent / "artifact"
    root.mkdir()
    header = bytearray(64)
    header[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<H", header, 16, 3)
    struct.pack_into("<H", header, 18, 40)
    struct.pack_into("<I", header, 36, 0x05000000)
    (root / probe.BIN).write_bytes(header)
    for name in ("elf-header.txt", "elf-attributes.txt", "elf-symbols.txt"):
        (root / name).write_text("ARMv7 build test\n")
    (root / "barrier-disassembly.txt").write_text("100: dmb sy\n")
    expected = {name: ("a" * 64) for name in probe.FILES - {"SHA256SUMS"}}
    expected[probe.BIN] = probe.EXPECTED_BINARY_SHA256
    data = {
        "schema": "plasma-hil-a1-armv7-barrier-build-v1",
        "result": "PASS", "binary": probe.BIN,
        "binary_sha256": probe.EXPECTED_BINARY_SHA256,
        "compiler_triplet": "arm-linux-gnueabihf",
        "toolchain_image": probe.IMAGE, "toolchain_snapshot": probe.SNAPSHOT,
        "z2_native_execution": "NOT_RUN", "physical_mmio_or_uio": "NOT_RUN",
        "fpga_or_dut": "NOT_RUN", "m1": "NO_GO", "github_sha": "c" * 40,
        "inspection_sha256": {
            name: expected[name] for name in
            ("elf-header.txt", "elf-attributes.txt", "elf-symbols.txt",
             "barrier-disassembly.txt")
        },
    }
    import json
    (root / "receipt.json").write_text(json.dumps(data))
    (root / "SHA256SUMS").write_text("".join(
        f"{expected[name]}  {name}\n" for name in sorted(expected)
    ))
    return root, expected


class FrozenArtifactContracts(unittest.TestCase):
    def test_exact_happy_fixture_passes_under_injected_fake_digests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, expected = fixture(Path(tmp))
            with patch.object(probe, "sha256", side_effect=lambda p: expected[p.name]):
                result = probe.check_artifact(root)
            self.assertEqual(result["elf_sha256"], probe.EXPECTED_BINARY_SHA256)
            self.assertEqual(result["manifest_file_count"], 6)

    def test_refuse_missing_extra_symlink_manifest_traversal_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, expected = fixture(Path(tmp))
            with patch.object(probe, "sha256", side_effect=lambda p: expected[p.name]):
                original = (root / "SHA256SUMS").read_text()
                for modified in (
                    original + ("a"*64 + "  ../../../etc/passwd\n"),
                    original + ("a"*64 + "  receipt.json\n"),
                    original.replace("  receipt.json", "  ../../outside"),
                    original.replace(probe.EXPECTED_BINARY_SHA256, "0"*64),
                ):
                    (root / "SHA256SUMS").write_text(modified)
                    with self.subTest(manifest=modified[-90:]), self.assertRaises(probe.Rejected):
                        probe.check_artifact(root)
                (root / "SHA256SUMS").write_text(original)
                (root / "unexpected").write_text("rogue")
                with self.assertRaises(probe.Rejected):
                    probe.check_artifact(root)
                (root / "unexpected").unlink()
                (root / "elf-header.txt").unlink()
                (root / "elf-header.txt").symlink_to(root / "elf-symbols.txt")
                with self.assertRaises(probe.Rejected):
                    probe.check_artifact(root)

    def test_tampered_binary_and_receipt_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, expected = fixture(Path(tmp))
            with patch.object(probe, "sha256", side_effect=lambda p: (
                "0"*64 if p.name == probe.BIN else expected[p.name]
            )), self.assertRaises(probe.Rejected):
                probe.check_artifact(root)
            import json
            receipt = json.loads((root / "receipt.json").read_text())
            receipt["z2_native_execution"] = "PASS"
            (root / "receipt.json").write_text(json.dumps(receipt))
            with patch.object(probe, "sha256", side_effect=lambda p: expected[p.name]), \
                 self.assertRaises(probe.Rejected):
                probe.check_artifact(root)

    def test_refuse_x86_execution_before_any_library_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = fixture(Path(tmp))
            with patch.object(probe.platform, "machine", return_value="x86_64"), \
                 patch.object(probe.ctypes, "CDLL") as loader, \
                 self.assertRaises(probe.Rejected):
                probe.execute(root, Path(tmp) / "report.json", 1000)
            loader.assert_not_called()

    def test_repetition_count_is_exact_and_not_caller_controlled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = fixture(Path(tmp))
            with self.assertRaisesRegex(probe.Rejected, "1000"):
                probe.execute(root, Path(tmp) / "report.json", 1)


class GitHubHostedPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = policy.WORKFLOW.read_text()
        cls.hosted = policy.HOSTED.read_text()
        cls.probe_src = policy.PROBE.read_text()

    def test_reviewed_allowlist(self):
        policy.validate(self.workflow, self.hosted, self.probe_src)

    def test_event_runner_artifact_and_hardware_mutations_denied(self):
        mutations = (
            ("  pull_request:", "  workflow_dispatch:"),
            ("  pull_request:", "  pull_request:\n  push:"),
            ("runs-on: ubuntu-24.04", "runs-on: [self-hosted, linux, x64]"),
            ("run-id: 39192248348", "run-id: 39192248349"),
            ("name: plasma-armv7-hil-a1-pr-39192248348",
             "name: plasma-armv7-hil-a1-pr-39192248349"),
            ("persist-credentials: false", "persist-credentials: true"),
            ("bash scripts/hil-a15-gh-hosted-qemu.sh", "echo skip"),
            ("if-no-files-found: error", "if-no-files-found: warn"),
            ("jobs:\n", "jobs:\n  rogue:\n    runs-on: self-hosted\n"),
        )
        for before, after in mutations:
            mutated = self.workflow.replace(before, after, 1)
            with self.subTest(before=before):
                self.assertNotEqual(mutated, self.workflow)
                with self.assertRaises(policy.ContractError):
                    policy.validate(mutated, self.hosted, self.probe_src)

    def test_no_network_weakening_or_existing_swpc_container(self):
        mutations = (
            ("--network none", "--network host"),
            ("--cap-drop=ALL", "--cap-add=SYS_ADMIN"),
            ("dst=/artifact,readonly", "dst=/artifact"),
            ('test "$RUNNER_ENVIRONMENT" = github-hosted',
             'test "$RUNNER_ENVIRONMENT" = self-hosted'),
            ("timeout 120s docker run", "docker exec plasma-z2like-demo-qemu"),
        )
        for before, after in mutations:
            mutated = self.hosted.replace(before, after, 1)
            with self.subTest(before=before):
                self.assertNotEqual(mutated, self.hosted)
                with self.assertRaises(policy.ContractError):
                    policy.validate(self.workflow, mutated, self.probe_src)


if __name__ == "__main__":
    unittest.main(verbosity=2)

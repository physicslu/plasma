#!/usr/bin/env python3
"""HIL-A Gate 1 synthetic validator/security negative tests. Never hardware."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(loaded)
    return loaded


a1 = module("armv7_hil_a1", "scripts/armv7-barrier-hil-a1.py")
contract = module("armv7_hil_contract", "scripts/armv7-barrier-hil-a-contract.py")

HEADER = """ELF Header:
  Class:                             ELF32
  Data:                              2's complement, little endian
  Type:                              DYN (Shared object file)
  Machine:                           ARM
  Flags:                             0x5000400, Version5 EABI, hard-float ABI
"""
ATTRS = """Attribute Section: aeabi
  Tag_CPU_arch: v7
  Tag_ABI_VFP_args: VFP registers
"""
SYMBOLS = """Symbol table '.dynsym' contains 12 entries:
   10: 000003e8     8 FUNC    GLOBAL DEFAULT   11 plasma_mmio_dmb_sy
"""
DISASM = """Disassembly of section .text:

000003e8 <plasma_mmio_dmb_sy>:
 3e8: f57ff05f     dmb sy
 3ec: e12fff1e     bx lr
"""


class ArmELFValidatorTests(unittest.TestCase):
    def test_synthetic_good_armv7_hardfloat_dmb(self):
        a1.validate_elf(HEADER, ATTRS, SYMBOLS, DISASM)

    def test_reject_wrong_arch_abi_export_and_instruction(self):
        bad = (
            (HEADER.replace("ELF32", "ELF64"), ATTRS, SYMBOLS, DISASM),
            (HEADER.replace("little endian", "big endian"), ATTRS, SYMBOLS, DISASM),
            (HEADER.replace("Machine:                           ARM",
                            "Machine:                           Advanced Micro Devices X86-64"),
             ATTRS, SYMBOLS, DISASM),
            (HEADER.replace("Type:                              DYN", "Type:                              EXEC"),
             ATTRS, SYMBOLS, DISASM),
            (HEADER.replace("Version5 EABI", "Version4 EABI"), ATTRS, SYMBOLS, DISASM),
            (HEADER, ATTRS.replace("Tag_CPU_arch: v7", "Tag_CPU_arch: v6"), SYMBOLS, DISASM),
            (HEADER, ATTRS.replace("Tag_ABI_VFP_args: VFP registers", ""),
             SYMBOLS, DISASM),
            (HEADER, ATTRS, SYMBOLS.replace("GLOBAL DEFAULT", "LOCAL DEFAULT"), DISASM),
            (HEADER, ATTRS, SYMBOLS.replace("DEFAULT   11", "DEFAULT  UND"), DISASM),
            (HEADER, ATTRS, SYMBOLS.replace("plasma_mmio_dmb_sy", "not_our_barrier"), DISASM),
            (HEADER, ATTRS, SYMBOLS, DISASM.replace("dmb sy", "dmb ish")),
            (HEADER, ATTRS, SYMBOLS, DISASM.replace("dmb sy", "nop")),
            (HEADER, ATTRS, SYMBOLS,
             DISASM.replace(" 3ec:", " 3ed: f57ff05f     dmb sy\n 3ec:")),
            (HEADER, ATTRS, SYMBOLS, DISASM.replace(
                " 3ec:", " 3ed: e12fff3e     blx lr\n 3ec:")),
            (HEADER, ATTRS, SYMBOLS,
             DISASM.replace("<plasma_mmio_dmb_sy>", "<different_symbol>")),
        )
        for header, attrs, symbols, disasm in bad:
            with self.subTest(case=(header[:60], attrs[:60], symbols[-35:], disasm[-60:])):
                with self.assertRaises(a1.HILA1Error):
                    a1.validate_elf(header, attrs, symbols, disasm)

    def test_build_requires_exact_commit_sha_before_touching_runner(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(a1.HILA1Error):
                a1.build(Path(folder) / "candidate", "no_sha")
            self.assertFalse((Path(folder) / "candidate").exists())

    def test_build_refuses_output_outside_runner_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder) / "runner"
            temp.mkdir()
            expected = "a" * 40
            with patch.object(a1, "_run", return_value=expected + "\n"):
                with patch.dict("os.environ", {"RUNNER_TEMP": str(temp)}, clear=False):
                    with self.assertRaisesRegex(a1.HILA1Error, "RUNNER_TEMP"):
                        a1.build(Path(folder) / "escape", expected)
            self.assertFalse((Path(folder) / "escape").exists())

    def test_source_is_approved_minimal_dmb_primitive(self):
        source = (ROOT / "software/python/native/armv7_mmio_barrier.c").read_text()
        self.assertIn("__ARM_ARCH_7A__", source)
        self.assertIn('"dmb sy"', source)
        self.assertIn('"memory"', source)
        self.assertIn("plasma_mmio_dmb_sy", source)


class WorkflowSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = contract.WORKFLOW.read_text()
        cls.host_ci = contract.HOST_CI.read_text()
        cls.wrapper = contract.HOST_SCRIPT.read_text()

    def test_hosted_manual_and_pr_cross_build_are_identical(self):
        contract.validate(self.main, self.host_ci, self.wrapper)

    def test_manual_requires_owner_main_hosted_only(self):
        changes = (
            ("  workflow_dispatch:", "  push:"),
            ("  workflow_dispatch:", "  workflow_dispatch:\n  pull_request:"),
            ("github.actor == 'physicslu'", "github.actor == 'intruder'"),
            ("github.ref == 'refs/heads/main'", "github.ref == 'refs/heads/agent'"),
            ("runs-on: ubuntu-24.04", "runs-on: [self-hosted, linux, x64]"),
            ('test "$RUNNER_ENVIRONMENT" = github-hosted',
             'test "$RUNNER_ENVIRONMENT" = self-hosted'),
            ("persist-credentials: false", "persist-credentials: true"),
            ("jobs:\n", "jobs:\n  z2:\n    runs-on: self-hosted\n"),
            ("      - name: Declare exact qualification boundary",
             "      - run: ssh z2.local uptime\n      - name: Declare exact qualification boundary"),
            ("bash scripts/armv7-barrier-hil-a1-hosted.sh", "echo bypass"),
        )
        for old, new in changes:
            changed = self.main.replace(old, new, 1)
            with self.subTest(old=old):
                self.assertNotEqual(self.main, changed)
                with self.assertRaises(contract.ContractError):
                    contract.validate(changed, self.host_ci, self.wrapper)

    def test_pr_uses_real_compiler_but_no_self_hosted_runner(self):
        changes = (
            ("runs-on: ubuntu-24.04", "runs-on: self-hosted"),
            ("  pull_request:", "  workflow_dispatch:"),
            ("  pull_request:", "  pull_request:\n  push:"),
            ("persist-credentials: false", "persist-credentials: true"),
            ("bash scripts/armv7-barrier-hil-a1-hosted.sh", "echo no build"),
            ("if-no-files-found: error", "if-no-files-found: warn"),
        )
        for old, new in changes:
            changed = self.host_ci.replace(old, new, 1)
            with self.subTest(old=old):
                self.assertNotEqual(changed, self.host_ci)
                with self.assertRaises(contract.ContractError):
                    contract.validate(self.main, changed, self.wrapper)

    def test_fail_closed_toolchain_image_snapshot_or_host_access(self):
        changes = (
            ("bc49dc1918ee1a47a93e65b5e4676e8680fb754b133197b92ca52bfe6731d5f0",
             "f"*64),
            ("20261005T000000Z", "20261019T000000Z"),
            ("dst=/plasma,readonly", "dst=/plasma"),
            ("--cap-drop=ALL", "--cap-add=SYS_ADMIN"),
            ('test "$RUNNER_ENVIRONMENT" = github-hosted',
             'test "$RUNNER_ENVIRONMENT" = self-hosted'),
            ("python3 /plasma/scripts/armv7-barrier-hil-a1.py build", "echo fake receipt"),
        )
        for old, new in changes:
            changed = self.wrapper.replace(old, new, 1)
            with self.subTest(old=old):
                self.assertNotEqual(changed, self.wrapper)
                with self.assertRaises(contract.ContractError):
                    contract.validate(self.main, self.host_ci, changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)

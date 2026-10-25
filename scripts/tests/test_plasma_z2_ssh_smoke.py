#!/usr/bin/env python3
"""Host-only Bash contracts. Never SSH, sudo, deploy, or touch FPGA."""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOST = ROOT / "scripts/plasma-z2-smoke.sh"
TARGET = ROOT / "scripts/z2/plasma-z2-ssh-smoke-target.sh"


class SSHDeploySmokeContracts(unittest.TestCase):
    def test_both_bash_scripts_parse(self):
        for path in (HOST, TARGET):
            with self.subTest(path=path):
                result = subprocess.run(
                    ["bash", "-n", str(path)], capture_output=True, text=True,
                    timeout=5, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_git_archive_lists_only_existing_reviewed_files(self):
        import shlex
        content = HOST.read_text()
        segment = content.split("sources=(", 1)[1].split(")", 1)[0]
        paths = shlex.split(segment)
        self.assertTrue(paths)
        self.assertEqual(len(paths), len(set(paths)))
        for path in paths:
            with self.subTest(path=path):
                self.assertFalse(path.startswith("/"))
                self.assertNotIn("..", Path(path).parts)
                self.assertTrue((ROOT / path).is_file(), path)

    def test_host_rejects_missing_or_injected_target_without_ssh(self):
        for argv in ([], ["--target", "bad;id"], ["--target", "../escape"],
                     ["--target", "-oProxyCommand=bad"], ["--unexpected"]):
            with self.subTest(args=argv):
                result = subprocess.run(
                    ["bash", str(HOST), *argv],
                    capture_output=True, text=True, timeout=5, check=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("DEPLOY_START", result.stdout)

    def test_one_command_uses_existing_root_and_exact_pr_pin(self):
        host = HOST.read_text()
        target = TARGET.read_text()
        self.assertIn("refs/pull/1167/head", host)
        self.assertIn("git archive --format=tar", host)
        self.assertIn(".plasma-path2-source-commit", host)
        self.assertIn("StrictHostKeyChecking=yes", host)
        self.assertIn("ssh -tt", host)
        self.assertIn("--plan", host)
        self.assertIn("sha256sum --check --status .plasma-path2-source-sha256",
                      target)
        self.assertIn("plasma-path2-approved", target)
        self.assertIn("z2-path2-root-entry", target)
        self.assertIn("run_op download LOADED_AND_HELD", target)
        self.assertIn("run_op test IDENTITY_PASS", target)
        self.assertIn("run_op restore RESTORED_VERIFIED,ALREADY_RESTORED", target)
        self.assertIn("read32_count", target)
        self.assertIn("write32_count", target)

    def test_golden_check_real_zynq_dmesg_and_latest_load(self):
        """Execute production dmesg filter and predicate with simulated output.

        Actual 2026-10-25 Z2 log includes 'Xilinx Zynq FPGA Manager';
        avoid a false NO_GO without accepting an earlier base image.
        """
        lines = TARGET.read_text().splitlines()
        selector = next(
            x.strip() for x in lines
            if x.strip().startswith('last="$(dmesg --color=never ')
        )
        predicate = next(
            x.strip().split(" ||", 1)[0] for x in lines
            if x.strip().startswith('[[ "$last" == ')
        )
        shell = (
            'dmesg() { printf "%s\\n" "$MOCK_DMESG"; }\\n'
            + selector + "\\n" + predicate
        )
        intro = "[   40.229271] fpga_manager fpga0: Xilinx Zynq FPGA Manager registered"
        golden = "[13027.805055] fpga_manager fpga0: writing base.bin to Xilinx Zynq FPGA Manager"
        old_name = "[129.930197] fpga_manager fpga0: writing base.bin to Xilinx FPGA Manager"
        candidate = "[12979.051154] fpga_manager fpga0: writing plasma-f1b-owner-20261020-once.bin to Xilinx Zynq FPGA Manager"
        cases = [
            ("actual Z2 last restored", "\\n".join([intro, old_name, candidate, golden]), True),
            ("older driver name", old_name, True),
            ("candidate loaded last", "\\n".join([intro, golden, candidate]), False),
            ("no manager load", intro, False),
            ("unrelated manager writes", "[3.0] fpga_manager fpga1: writing base.bin to Xilinx Zynq FPGA Manager", False),
            ("empty dmesg", "", False),
        ]
        for description, dmesg_output, expected in cases:
            with self.subTest(case=description):
                proc = subprocess.run(
                    ["bash", "-c", shell],
                    env={**os.environ, "MOCK_DMESG": dmesg_output},
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(proc.returncode == 0, expected, proc.stderr)

    def test_never_autorun_hardware_from_ci_or_deploy_without_golden(self):
        src = HOST.read_text() + TARGET.read_text()
        for forbidden in ("workflow_dispatch", "path2-stage-contract",
                          ".plasma-path2-profile", "shell=True",
                          "StrictHostKeyChecking=no", "sshpass ",
                          "sudo -S ", "Blue Pill", "openocd "):
            self.assertNotIn(forbidden, src)
        target = TARGET.read_text()
        self.assertIn("Golden Image not positively observed", target)
        self.assertIn("prior FPGA image not BASE", target)
        self.assertIn("firmware digest mismatch", target)
        self.assertIn("RECOVERY_UNKNOWN", target)
        self.assertIn("source Manifest mismatch", target)


if __name__ == "__main__":
    unittest.main()

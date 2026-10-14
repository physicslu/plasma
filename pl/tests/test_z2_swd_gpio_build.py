"""Host-only verification of Z2 EMIO/Identity build contracts and packaging."""
from __future__ import annotations

import importlib.util
import os
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "projects/z2-swd-gpio/artifact.py"


def load_artifact():
    spec = importlib.util.spec_from_file_location("z2_swd_gpio_artifact", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IdentityArtifactContractTest(unittest.TestCase):
    def test_prepare_generates_expected_hardware_abi_words(self):
        tool = load_artifact()
        commit = "0123456789abcdef0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as tmp, patch.object(tool, "_commit", return_value=commit):
            gen = Path(tmp) / "gen"
            tool.prepare(gen, "0.1.0")
            header = (gen / "plasma_identity_generated.vh").read_text()
            # The standalone SV must contain the *actual* source RTL with
            # immutable release constants substituted before IP Integrator.
            standalone = (gen / "pl_identity_axi_lite.sv").read_text()
            original = (ROOT / "rtl/bus/pl_identity_axi_lite.sv").read_text()
            directive = '`include "plasma_identity_generated.vh"'
            self.assertEqual(original.count(directive), 1)
            self.assertIn(original.replace(directive, header.rstrip("\n")), standalone)
            self.assertNotIn(directive, standalone)
            self.assertIn("module pl_identity_axi_lite (", standalone)
            self.assertIn("PLSM_VERSION = 32'h00000100", header)
            self.assertIn("PLSM_BUILD_ID_0 = 32'h01234567", header)
            self.assertIn("PLSM_BUILD_ID_3 = 32'h89ABCDEF", header)
            payload = json.loads((gen / "build-identity.json").read_text())
            self.assertEqual(payload["source_git_sha"], commit)
            self.assertEqual(payload["build_id"], commit[:32])
            self.assertEqual(payload["capabilities"], ["swd_gpio"])
            self.assertEqual(payload["board_part"], "tul.com.tw:pynq-z2:part0:1.0")
            self.assertEqual(
                payload["board_files_git_sha"],
                "e02d6a3866b5465218f777168cdc51344ac94e07",
            )
            self.assertFalse(payload["hardware_runtime_ready"])
            self.assertFalse(payload["physical_programming_qualified"])

    def test_version_rejects_invalid_or_overwide(self):
        tool = load_artifact()
        for bad in ("", "1.2", "1.2.3.4", "1.256.0", "v0.1.0", "01.2.3", "1.2.3-rc"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tool._version(bad)

    def test_finalize_content_hashes_copied_handoff(self):
        tool = load_artifact()
        commit = "abcdef0123456789abcdef0123456789abcdef01"
        with tempfile.TemporaryDirectory() as tmp, patch.object(tool, "_commit", return_value=commit):
            root = Path(tmp)
            gen = root / "generated"
            project = root / "project"
            tool.prepare(gen, "0.1.0")
            impl = project / "z2_swd_gpio.runs/impl_1"
            impl.mkdir(parents=True)
            (impl / "system_wrapper.bit").write_bytes(b"dummy-host-only-bitstream")
            hwh = project / "z2_swd_gpio.gen/sources_1/bd/system/hw_handoff/system.hwh"
            hwh.parent.mkdir(parents=True)
            hwh.write_text("<HWH>mock</HWH>")
            addr = gen / "identity-axi-base.txt"
            addr.write_text("0x43C00000\n")
            tool.finalize(gen, project, "2024.1", addr)
            artifact_dir = root / "artifacts"
            manifest = json.loads((artifact_dir / "manifest.json").read_text())
            bit = artifact_dir / manifest["bitstream_file"]
            self.assertTrue(bit.is_file())
            self.assertEqual(manifest["identity_axi_base_address"], "0x43C00000")
            self.assertEqual(manifest["bitstream_sha256"], tool._digest(bit))
            self.assertEqual(manifest["build_validation"]["physical_hil"], "NOT_RUN")
            self.assertFalse(manifest["physical_programming_qualified"])

    def test_finalize_rejects_source_change_and_invalid_base(self):
        tool = load_artifact()
        with tempfile.TemporaryDirectory() as tmp, patch.object(tool, "_commit", return_value="a" * 40):
            root = Path(tmp)
            gen = root / "generated"
            tool.prepare(gen, "0.1.0")
            with patch.object(tool, "_commit", return_value="b" * 40):
                with self.assertRaisesRegex(ValueError, "Source commit changed"):
                    tool.finalize(gen, root, "2024.1", gen / "missing-address")


class Z2SourceContractTest(unittest.TestCase):
    def test_mapped_pmodb_pins_are_unique_and_match_board_master(self):
        xdc = (ROOT / "constraints/pynq-z2/z2-swd-gpio.xdc").read_text()
        pairs = re.findall(r"PACKAGE_PIN\s+(\w+)\s+IOSTANDARD\s+LVCMOS33\}\s+\[get_ports\s+(\w+)\]", xdc)
        self.assertEqual(
            pairs, [("W14", "swclk_io"), ("Y14", "swdio_io"), ("T11", "nrst_io")],
        )
        master = (ROOT / "constraints/pynq-z2/pynq-z2-base.xdc").read_text()
        for pin in ("W14", "Y14", "T11"):
            self.assertRegex(master, rf"PACKAGE_PIN\s+{pin}\b")

    def test_swdio_tristate_and_reset_open_drain(self):
        rtl = (ROOT / "rtl/site/swd_emio_bridge.sv").read_text()
        self.assertIn(".I(gpio_o[1]), .T(gpio_t[1])", rtl)
        self.assertIn(".I(1'b0), .T(gpio_t[2] | gpio_o[2])", rtl)
        self.assertIn("gpio_i[1] = swdio_input", rtl)

    def test_identity_contract_offsets_and_axi_fail_closed(self):
        rtl = (ROOT / "rtl/bus/pl_identity_axi_lite.sv").read_text()
        for offset in ("5'h00", "5'h04", "5'h08", "5'h0C", "5'h10", "5'h14", "5'h18", "5'h1C"):
            self.assertIn(offset, rtl)
        self.assertIn("32'h504C534D", rtl)
        self.assertIn("s_axi_bresp   = 2'b10", rtl)
        # AXI interconnect may forward a full nonzero mapped physical base.
        self.assertIn("s_axi_araddr[11:5] != 7'b0", rtl)
        self.assertNotIn("s_axi_araddr[31:5] != 27'b0", rtl)

    def test_vivado_requires_board_preset_timing_and_no_load(self):
        folder = ROOT / "projects/z2-swd-gpio"
        project = (folder / "create_project.tcl").read_text()
        bd = (folder / "create_block_design.tcl").read_text()
        build = (folder / "build_bitstream.tcl").read_text()
        shell = (folder / "build-on-swpc.sh").read_text()
        self.assertIn("[file join $generated_dir pl_identity_axi_lite.sv]", project)
        self.assertNotIn("[file join $pl_dir rtl bus pl_identity_axi_lite.sv]", project)
        self.assertNotIn("set_property include_dirs", project)
        self.assertIn("set_param board.repoPaths [list $board_repo]", project)
        self.assertIn("tul.com.tw:pynq-z2:part0:1.0", project)
        board_script = (folder / "prepare-board-repository.sh").read_text()
        self.assertIn("e02d6a3866b5465218f777168cdc51344ac94e07", board_script)
        self.assertIn("PLASMA_BOARD_REPO", shell)
        self.assertIn("prepare-board-repository.sh", shell)
        self.assertIn("apply_board_preset \"1\"", bd)
        self.assertIn("PCW_GPIO_EMIO_GPIO_ENABLE", bd)
        self.assertIn("M_AXI_GP0", bd)
        self.assertIn("get_timing_paths -setup", build)
        self.assertIn("get_timing_paths -hold", build)
        self.assertIn("BITSTREAM_BUILD_PASS", build)
        # Prevent concurrent Vivado builds and the observed ext4 stale
        # Block Design cleanup race; old generated data is never reused.
        self.assertIn('flock -n 9', shell)
        self.assertIn('VIVADO_BUILD_BUSY', shell)
        self.assertIn('mv -T -- "$project" "$retired/project"', shell)
        self.assertIn('mktemp -d "$build/.retired-project.XXXXXXXX"', shell)
        self.assertNotIn('rm -rf -- "$project"', shell)
        self.assertNotIn("systemctl", shell)
        self.assertNotIn("fpga_manager", shell)

    def test_vivado_version_parser_handles_actual_swpc_banner(self):
        shell = (ROOT / "projects/z2-swd-gpio/build-on-swpc.sh").read_text()
        expression = next(
            line.split("sed -n '", 1)[1].split("'", 1)[0]
            for line in shell.splitlines()
            if line.startswith("vivado_version=")
        )
        for banner in ("vivado v2026.1 (64-bit)\nTool Version Limit: 2026.06\n",
                       "Vivado v2024.2 (64-bit)\n"):
            output = subprocess.run(
                ["sed", "-n", expression], input=banner,
                text=True, capture_output=True, check=True,
            ).stdout.strip()
            self.assertEqual(output, banner.split()[1][1:])
        output = subprocess.run(
            ["sed", "-n", expression], input="unsupported tool\n",
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        self.assertEqual(output, "")

    def test_monitored_build_has_hard_timeout_and_terminal_status(self):
        folder = ROOT / "projects/z2-swd-gpio"
        monitor = (folder / "run-monitored-on-swpc.sh").read_text()
        self.assertIn('SUPERVISOR_PID=%s', monitor)
        self.assertIn('STARTED_EPOCH_MS=%s', monitor)
        blocker = (folder / "build-blocking-on-swpc.sh").read_text()
        self.assertIn('PLASMA_PROGRESS_INTERVAL_SECONDS:-10', blocker)
        self.assertIn('python3 "$progress" --logdir "$logdir"', blocker)
        self.assertIn('UPDATED_EPOCH_MS=%s', monitor)
        self.assertIn('PLASMA_BUILD_TIMEOUT_MINUTES:-120', monitor)
        self.assertIn('flock -n 8', monitor)
        self.assertIn('flock -n "$build/.build.lock" -c true', monitor)
        self.assertIn('timeout --signal=TERM --kill-after=60s', monitor)
        self.assertIn('bash "$script_dir/build-on-swpc.sh"', monitor)
        for state in ("RUNNING", "PASS", "FAIL", "TIMEOUT"):
            self.assertIn(state, monitor)
        self.assertIn('[[ -s "$build/artifacts/manifest.json" ]]', monitor)
        for forbidden in ("fpga_manager", "systemctl", "git push", "killall"):
            self.assertNotIn(forbidden, monitor)

    def test_tcl_measures_real_vivado_stage_transitions(self):
        tcl = (ROOT / "projects/z2-swd-gpio/build_bitstream.tcl").read_text()
        for phase in ("BLOCK_DESIGN", "SYNTHESIS", "IMPLEMENTATION", "TIMING_AND_REPORTS"):
            self.assertIn(f"plasma_stage {phase} START", tcl)
            self.assertIn(f"plasma_stage {phase} DONE", tcl)
        self.assertIn("launch_runs synth_1", tcl)
        self.assertIn("wait_on_run synth_1", tcl)
        self.assertIn("launch_runs impl_1", tcl)
        self.assertIn("wait_on_run impl_1", tcl)

    def test_progress_reporter_shows_stage_and_total_elapsed(self):
        """Report exact measured durations without any FPGA build dependency."""
        script = ROOT / "projects/z2-swd-gpio/build-progress.py"
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / "monitored-build.status").write_text(
                "STATUS=RUNNING\nSTARTED_EPOCH_MS=1700000000000\n"
            )
            (logs / "vivado-console.log").write_text(
                "STAGE_EVENT BLOCK_DESIGN START 1700000001000\n"
                "STAGE_EVENT BLOCK_DESIGN DONE 1700000002500\n"
                "STAGE_EVENT SYNTHESIS START 1700000003000\n"
                # A prior build's events must not contaminate current totals.
                "STAGE_EVENT TIMING_AND_REPORTS DONE 1699999999000\n"
            )
            reporter = importlib.util.spec_from_file_location("fpga_progress", script)
            self.assertIsNotNone(reporter)
            module = importlib.util.module_from_spec(reporter)
            reporter.loader.exec_module(module)
            running = module.render(logs, now_ms=1700000005500)
            self.assertIn("RUNNING | total=00:00:05", running)
            self.assertIn("Synthesis (00:00:02)", running)
            finished_status = (
                "STATUS=PASS\nSTARTED_EPOCH_MS=1700000000000\n"
                "UPDATED_EPOCH_MS=1700000006700\n"
            )
            (logs / "monitored-build.status").write_text(finished_status)
            summary = module.render(logs, summary=True, now_ms=1700000999000)
            self.assertIn("TOTAL_ELAPSED=00:00:06", summary)
            self.assertIn("STAGE Block Design: 00:00:01", summary)

    def test_foreground_blocking_client_with_mock_supervisor(self):
        """Real Bash detach+block+reattach behavior, no Vivado/FPGA execution."""
        import shutil

        source = ROOT / "projects/z2-swd-gpio/build-blocking-on-swpc.sh"
        for tool in ("bash", "flock", "nohup", "tail", "git"):
            if shutil.which(tool) is None:
                self.skipTest(f"{tool} not available")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "pl/projects/z2-swd-gpio"
            folder.mkdir(parents=True)
            monitor = folder / "run-monitored-on-swpc.sh"
            shutil.copyfile(source, folder / source.name)
            shutil.copyfile(ROOT / "projects/z2-swd-gpio/build-progress.py", folder / "build-progress.py")
            monitor.write_text(
                '#!/usr/bin/env bash\n'
                'set -Eeuo pipefail\n'
                'd="$(cd -- "$(dirname "$0")/../../build/z2-swd-gpio/logs" && pwd)"\n'
                'printf "STATUS=RUNNING\\nSUPERVISOR_PID=%s\\n" "$$" > "$d/monitored-build.status"\n'
                'echo MOCK_BUILD_STARTED\n'
                'sleep 0.3\n'
                'printf "STATUS=PASS\\nSUPERVISOR_PID=%s\\n" "$$" > "$d/monitored-build.status"\n'
                'echo MOCK_BUILD_FINISHED\n'
            )
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
            run = subprocess.run(
                ["bash", str(folder / source.name), "start"],
                text=True, capture_output=True, timeout=15,
                env={**os.environ, "PLASMA_PROGRESS_INTERVAL_SECONDS": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("BUILD_STARTED_SUPERVISOR_PID=", run.stdout)
            self.assertIn("MOCK_BUILD_FINISHED", run.stdout)
            self.assertIn("RESULT=PASS", run.stdout)
            pid = (Path(tmp) / "pl/build/z2-swd-gpio/logs/monitored-build.pid").read_text().strip()
            reattach = subprocess.run(
                ["bash", str(folder / source.name), "attach", pid],
                text=True, capture_output=True, timeout=15,
            )
            self.assertEqual(reattach.returncode, 0, reattach.stdout + reattach.stderr)
            self.assertIn("RESULT=PASS", reattach.stdout)
            wrong = subprocess.run(
                ["bash", str(folder / source.name), "attach", "99999999"],
                text=True, capture_output=True, timeout=15,
            )
            self.assertNotEqual(wrong.returncode, 0)
            self.assertIn("stale/unrelated status", wrong.stderr)



if __name__ == "__main__":
    unittest.main()

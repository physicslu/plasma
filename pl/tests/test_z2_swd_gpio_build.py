"""Host-only verification of Z2 EMIO/Identity build contracts and packaging."""
from __future__ import annotations

import importlib.util
import json
import re
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


if __name__ == "__main__":
    unittest.main()

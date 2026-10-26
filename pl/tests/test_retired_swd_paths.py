"""Retired Z2 SWD project guards; does not access Vivado, USB or Z2."""
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.parametrize("project,tag", [
    ("z2-swd-gpio", "RETIRED_Z2_SWD_GPIO"),
    ("z2-swd03-axi", "RETIRED_Z2_SWD03_AXI"),
])
def test_retired_build_entrypoints(project, tag):
    root = ROOT / "pl/projects" / project
    proc = subprocess.run(["bash", str(root / "build-on-swpc.sh")],
                          capture_output=True, text=True, timeout=5)
    assert proc.returncode == 2
    assert tag in proc.stderr
    for file in ("create_project.tcl", "create_block_design.tcl", "build_bitstream.tcl"):
        s = (root / file).read_text().splitlines()
        assert s[0].startswith("# RETIRED:")
        assert tag in s[1]
    assert 'raise SystemExit("' + tag in (root / "artifact.py").read_text()
    assert (root / "README.md").read_text().startswith("# RETIRED")

@pytest.mark.parametrize("name", ("pl-z2-swd-gpio.yml", "pl-swd03-axi.yml"))
def test_legacy_ci_host_only_no_manual_dispatch(name):
    content = (ROOT / ".github/workflows" / name).read_text()
    assert "workflow_dispatch:" not in content
    assert "runs-on: ubuntu-latest" in content

def test_old_swpc_persistent_bitstream_workflow_gone():
    assert not (ROOT / ".github/workflows/swpc-vivado-bitstream-build.yml").exists()

def test_current_contract_and_shared_dependencies():
    root_contract = (ROOT / "AGENTS.md").read_text()
    assert "Current Z2 Blue Pill physical SWD path (normative)" in root_contract
    for path in ("scripts/bluepill-wordport-session.py",
                 "pl/projects/z2-bluepill-rbb/image-manifest.json",
                 "pl/hil/fpga_image_root.py",
                 "pl/hil/swd04/one_shot.py",
                 "pl/projects/z2-swd-gpio/artifact.py",
                 "pl/projects/z2-swd-gpio/prepare-board-repository.sh"):
        assert (ROOT / path).is_file()
    inventory = (ROOT / "docs/development/swd-legacy-path-retirement.md").read_text()
    for symbol in ("swd03_dpidr_responder.sv", "plasma_vivado_host_build.py",
                   "bluepill-wordport-session.py", "pl/hil/swd04/"):
        assert symbol in inventory


@pytest.mark.parametrize("module,tag", [
    ("pl.hil.swd04.one_shot", "RETIRED_SWD05_INTERNAL_IMAGE_CLI"),
    ("pl.hil.swd04.native_qualify", "RETIRED_SWD04_SYNTHETIC_MMIO_CLI"),
])
def test_legacy_internal_hil_command_line_rejects_execution(module, tag):
    """Static fail-closed CLI check; no USB, FPGA Manager or /dev/mem."""
    source = (ROOT / (module.replace(".", "/") + ".py")).read_text()
    assert source.count('if __name__ == "__main__":') == 1
    code = source.split('if __name__ == "__main__":', 1)[1]
    assert tag in code
    assert "raise SystemExit(2)" in code


def test_loopback_and_fixed_abi_are_not_external_swd():
    inventory = (ROOT / "docs/development/swd-legacy-path-retirement.md").read_text()
    for name in ("pl.hil.pspl02.runner", "pl.hil.lt02.native",
                 "z2-fixed-unified-site1", "scripts/plasma-z2-smoke.sh"):
        assert name in inventory
    for name in ("pl/hil/fpga_image_root.py", "pl/hil/path2_z2_target_guard.py",
                 "pl/hil/swd04/one_shot.py", "scripts/bluepill-wordport-session.py"):
        assert (ROOT / name).is_file()

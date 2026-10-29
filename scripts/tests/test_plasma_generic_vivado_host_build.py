"""Host-only admission tests for project-owned Vivado build contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plasma_vivado_host_build as build


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


def task(project: str) -> dict:
    return {"execution_path": "path2-cli", "capability": "vivado-host-build",
            "project": project, "toolchain": "2026.1", "board_repo_sha": SHA}


APPROVAL = {"task_id": "path2-work-order", "execution_path": "path2-cli",
            "execution_capability": "vivado-host-build", "pinned_sha": SHA,
            "work_order_sha256": "b" * 64}


class GenericVivadoContracts(unittest.TestCase):
    def test_two_non_f1_projects_supply_the_same_interface(self):
        for name, expected in (("z2-identity", "z2_identity"),
                               ("z2-control-waveform", "z2_control_waveform")):
            with self.subTest(project=name):
                plan = build.generic_project_contract(
                    task("pl/projects/" + name), workspace=ROOT,
                    approval=APPROVAL)
                self.assertEqual(plan["vivado_project"], expected)
                self.assertEqual(plan["success_marker"], "BITSTREAM_BUILD_PASS")
                self.assertTrue(plan["prepare_artifact"])

    def test_f1b_is_not_an_implicit_generic_project(self):
        with self.assertRaisesRegex(build.BuildDenied, "BUILD_SOURCE_DENIED"):
            build.generic_project_contract(
                task("pl/projects/z2-fixed-unified-site1"),
                workspace=ROOT, approval=APPROVAL)

    def test_bad_or_missing_contract_stops_before_build(self):
        for project in ("pl/projects/does-not-exist", "../other"):
            with self.subTest(project=project), self.assertRaises(build.BuildDenied):
                build.generic_project_contract(task(project), workspace=ROOT,
                                               approval=APPROVAL)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "pl/projects/example"
            project.mkdir(parents=True)
            source = ROOT / "pl/projects/z2-identity"
            for name in ("create_project.tcl", "create_block_design.tcl",
                         "build_bitstream.tcl", "verify_hwh.py", "artifact.py"):
                (project / name).write_bytes((source / name).read_bytes())
            contract = json.loads((source / "host-build.json").read_text())
            text = json.dumps(contract).replace('"schema":',
                                                '"schema": "duplicate", "schema":', 1)
            (project / "host-build.json").write_text(text)
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_GENERIC_CONTRACT_DUPLICATE"):
                build.generic_project_contract(task("pl/projects/example"),
                                               workspace=root, approval=APPROVAL)

    def test_hardware_command_in_project_tcl_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "pl/projects/example"
            project.mkdir(parents=True)
            source = ROOT / "pl/projects/z2-identity"
            for name in ("host-build.json", "create_project.tcl",
                         "create_block_design.tcl", "build_bitstream.tcl",
                         "verify_hwh.py", "artifact.py"):
                (project / name).write_bytes((source / name).read_bytes())
            with (project / "create_project.tcl").open("a") as stream:
                stream.write("\nprogram_hw_devices [current_hw_device]\n")
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_GENERIC_TCL_DENIED"):
                build.generic_project_contract(task("pl/projects/example"),
                                               workspace=root, approval=APPROVAL)

    def test_dynamic_work_order_selects_generic_runner(self):
        with patch.object(build, "run_generic", return_value={"status": "observed"}) as runner:
            result = build.run(task("pl/projects/z2-identity"),
                               workspace=ROOT, approval=APPROVAL)
        self.assertEqual(result["status"], "observed")
        runner.assert_called_once()

    def test_runtime_requires_dispatcher_source_binding_before_tool_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_GENERIC_SOURCE_BINDING_DENIED"):
                build.run_generic(task("pl/projects/z2-identity"),
                                  workspace=ROOT, approval=APPROVAL,
                                  evidence_dir=Path(temporary),
                                  executor=lambda *_a, **_kw: self.fail("tool launched"))


if __name__ == "__main__":
    unittest.main()

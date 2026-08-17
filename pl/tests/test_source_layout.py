"""Source-layout checks that do not require a Vivado installation."""

from pathlib import Path
import re
import unittest


PL_DIR = Path(__file__).resolve().parents[1]
RTL_FILE = PL_DIR / "rtl" / "examples" / "btled.sv"
XDC_FILE = PL_DIR / "constraints" / "pynq-z2" / "btled.xdc"
CREATE_TCL = PL_DIR / "projects" / "btled" / "create_project.tcl"
VERIFICATION_DIR = PL_DIR / "verification"


class BtledSourceLayoutTest(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        for path in (RTL_FILE, XDC_FILE, CREATE_TCL):
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"Missing required file: {path}")

    def test_there_is_only_one_btled_module_definition(self) -> None:
        definitions = []
        pattern = re.compile(r"^\s*module\s+btled\b", re.MULTILINE)

        for rtl_path in (PL_DIR / "rtl").rglob("*.sv"):
            if pattern.search(rtl_path.read_text(encoding="utf-8")):
                definitions.append(rtl_path)

        self.assertEqual(definitions, [RTL_FILE])

    def test_all_btled_ports_have_unique_package_pins(self) -> None:
        xdc = XDC_FILE.read_text(encoding="utf-8")
        entries = re.findall(
            r"PACKAGE_PIN\s+(\w+).*?get_ports\s+\{\s*(\w+\[\d+\])\s*\}",
            xdc,
        )
        expected_ports = {
            "led[0]", "led[1]", "led[2]", "led[3]",
            "btn[0]", "btn[1]", "btn[2]", "btn[3]",
        }

        pins = [pin for pin, _ in entries]
        ports = [port for _, port in entries]
        self.assertEqual(set(ports), expected_ports)
        self.assertEqual(len(ports), len(expected_ports))
        self.assertEqual(len(pins), len(set(pins)), "PACKAGE_PIN values must be unique")

    def test_create_project_tcl_uses_repository_relative_paths(self) -> None:
        tcl = CREATE_TCL.read_text(encoding="utf-8")
        self.assertIn("[info script]", tcl)
        self.assertIn("xc7z020clg400-1", tcl)
        self.assertIn("set_property top btled", tcl)
        self.assertNotIn("/storage/", tcl)

    def test_generated_vivado_project_files_are_not_in_source_tree(self) -> None:
        forbidden_files = list(PL_DIR.rglob("*.xpr"))
        forbidden_dirs = [
            path
            for path in PL_DIR.rglob("*")
            if path.is_dir() and path.suffix in {".srcs", ".runs", ".cache"}
        ]
        self.assertEqual(forbidden_files, [])
        self.assertEqual(forbidden_dirs, [])

    def test_generated_simulation_artifacts_are_not_in_verification_tree(self) -> None:
        forbidden_patterns = (
            "*.vcd",
            "*.fst",
            "*.ghw",
            "*.result.xml",
            "results.xml",
        )
        forbidden_files = sorted(
            path
            for pattern in forbidden_patterns
            for path in VERIFICATION_DIR.rglob(pattern)
        )
        self.assertEqual(
            forbidden_files,
            [],
            "Generated simulation artifacts must live under pl/build/, not pl/verification/",
        )


if __name__ == "__main__":
    unittest.main()

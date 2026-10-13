#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "data/ic-support/validate_stm32f103_openocd_real_binary.py"
spec = importlib.util.spec_from_file_location("stm32f103_openocd_real_binary", MODULE_PATH)
assert spec and spec.loader
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def _marker_output(*, size: int = 65536, driver: str = "stm32f1x") -> str:
    return "\n".join(
        [
            "PLASMA_FLASH_NAME=stm32f1x.flash",
            f"PLASMA_FLASH_DRIVER={driver}",
            "PLASMA_FLASH_BASE=134217728",
            f"PLASMA_FLASH_SIZE={size}",
            "PLASMA_FLASH_TARGET=stm32f1x.cpu",
            "PLASMA_CONFIG_ONLY_NOINIT=1",
        ]
    )


class STM32F103RealOpenOCDSoftwareAcceptanceTests(unittest.TestCase):
    def test_contract_preserves_exact_c8_identity_and_closed_hardware_gate(self) -> None:
        contract = acceptance.load_contract()
        self.assertEqual(contract["icpn"], "STM32F103C8T6")
        self.assertEqual(contract["flash_start"], 0x08000000)
        self.assertEqual(contract["flash_size_bytes"], 64 * 1024)
        self.assertEqual(contract["interface_config"], "interface/dummy.cfg")
        self.assertEqual(contract["target_config"], "target/stm32f1x.cfg")
        self.assertEqual(contract["openocd_version"], "0.12.0")
        self.assertFalse(contract["hardware_runtime_ready"])

    def test_argv_is_noinit_config_only_and_uses_exact_c8_flash_size(self) -> None:
        contract = acceptance.load_contract()
        argv = acceptance.build_openocd_argv(
            openocd=Path("/opt/test/openocd"),
            scripts_root=Path("/opt/test/scripts"),
            contract=contract,
        )
        commands = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "-c"]
        files = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "-f"]

        self.assertEqual(commands[0], "noinit")
        self.assertEqual(commands[-1], "shutdown")
        self.assertIn("transport select jtag", commands)
        self.assertIn("set FLASH_SIZE 0x10000", commands)
        self.assertIn("interface/dummy.cfg", files)
        self.assertIn("target/stm32f1x.cfg", files)
        self.assertFalse(any("board/" in value for value in files))
        self.assertFalse(any("blue_pill" in value.lower() for value in argv))

        forbidden_exact = {"init", "reset", "halt", "resume"}
        self.assertTrue(forbidden_exact.isdisjoint(command.strip().lower() for command in commands))

    def test_safe_argv_rejects_hardware_init(self) -> None:
        contract = acceptance.load_contract()
        argv = acceptance.build_openocd_argv(
            openocd=Path("/opt/test/openocd"),
            scripts_root=Path("/opt/test/scripts"),
            contract=contract,
        )
        shutdown_index = len(argv) - 1
        mutated = argv[:shutdown_index - 1] + ["-c", "init"] + argv[shutdown_index - 1 :]
        with self.assertRaises(acceptance.OpenOCDSoftwareAcceptanceError):
            acceptance.validate_safe_argv(mutated)

    def test_safe_argv_rejects_blue_pill_board_config(self) -> None:
        contract = acceptance.load_contract()
        argv = acceptance.build_openocd_argv(
            openocd=Path("/opt/test/openocd"),
            scripts_root=Path("/opt/test/scripts"),
            contract=contract,
        )
        target_index = argv.index("target/stm32f1x.cfg")
        mutated = list(argv)
        mutated[target_index] = "board/stm32f103c8_blue_pill.cfg"
        with self.assertRaises(acceptance.OpenOCDSoftwareAcceptanceError):
            acceptance.validate_safe_argv(mutated)

    def test_marker_validation_accepts_real_stm32f1_driver_registration(self) -> None:
        contract = acceptance.load_contract()
        observed = acceptance.validate_markers(_marker_output(), contract)
        self.assertEqual(observed["flash_driver"], "stm32f1x")
        self.assertEqual(observed["flash_size_bytes"], 64 * 1024)

    def test_marker_validation_rejects_blue_pill_128k_override(self) -> None:
        contract = acceptance.load_contract()
        with self.assertRaises(acceptance.OpenOCDSoftwareAcceptanceError):
            acceptance.validate_markers(_marker_output(size=128 * 1024), contract)

    def test_marker_validation_rejects_wrong_flash_driver(self) -> None:
        contract = acceptance.load_contract()
        with self.assertRaises(acceptance.OpenOCDSoftwareAcceptanceError):
            acceptance.validate_markers(_marker_output(driver="not-stm32f1x"), contract)

    def test_acceptance_evidence_keeps_process_and_hardware_boundaries_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "bin" / "openocd"
            scripts = root / "share" / "openocd" / "scripts"
            dummy = scripts / "interface" / "dummy.cfg"
            target = scripts / "target" / "stm32f1x.cfg"
            binary.parent.mkdir(parents=True)
            dummy.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            binary.write_bytes(b"fake-openocd-for-runner-injection")
            dummy.write_text("# Dummy interface\nadapter driver dummy\n", encoding="utf-8")
            target.write_text(
                "\n".join(
                    [
                        "if { [info exists FLASH_SIZE] } {",
                        "    set _FLASH_SIZE $FLASH_SIZE",
                        "}",
                        "flash bank $_FLASHNAME stm32f1x 0x08000000 $_FLASH_SIZE 0 0 $_TARGETNAME",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            calls: list[list[str]] = []

            def runner(argv, **_kwargs):
                calls.append(list(argv))
                if "--version" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout="Open On-Chip Debugger 0.12.0\n",
                        stderr="",
                    )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=_marker_output() + "\n",
                    stderr="",
                )

            evidence = acceptance.run_acceptance(
                openocd=binary,
                scripts_root=scripts,
                runner=runner,
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(evidence["result"], "PASS")
        self.assertEqual(evidence["scope"], "real_openocd_configuration_parse_only_noinit")
        self.assertEqual(evidence["flash_driver"], "stm32f1x")
        self.assertEqual(evidence["flash_size_bytes"], 64 * 1024)
        self.assertTrue(evidence["automatic_init_disabled"])
        self.assertFalse(evidence["board_config_loaded"])
        self.assertFalse(evidence["adapter_initialization_requested"])
        self.assertFalse(evidence["target_examination_requested"])
        self.assertFalse(evidence["flash_operation_requested"])
        self.assertFalse(evidence["hardware_runtime_ready"])
        self.assertFalse(evidence["physical_programming_qualified"])


if __name__ == "__main__":
    unittest.main()

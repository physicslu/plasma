"""No-Docker regressions for best-effort Phase 2 failure diagnostics."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/ppu-network-phase2-acceptance.py"
SPEC = importlib.util.spec_from_file_location("ppu_phase2_diagnostics_test_subject", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
phase2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase2)


class Phase2DiagnosticTests(unittest.TestCase):
    def test_precleanup_writes_bounded_best_effort_evidence_without_running_hardware(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            commands = []

            def fake_run(command, **kwargs):
                commands.append(command)
                self.assertEqual(kwargs["timeout"], 5)
                self.assertFalse(kwargs["check"])
                if command[1:3] == ["logs", "--tail"] and "helper" in command[-1]:
                    raise subprocess.TimeoutExpired(command, 5)
                return subprocess.CompletedProcess(
                    args=command, returncode=0, stdout="ready\n", stderr=""
                )

            with patch.object(phase2.subprocess, "run", side_effect=fake_run):
                phase2._capture_failure_diagnostics(
                    root, "phase2-ppu", "phase2-helper", "phase2-probe",
                    {"helper_socket_ready": "PASS"}
                )
            result = json.loads((root / "failure-diagnostics.json").read_text())
            self.assertEqual(result["evidence_scope"], "ppu-phase2-diagnostic-only-no-hardware")
            self.assertEqual(result["passed_checks_before_failure"],
                             {"helper_socket_ready": "PASS"})
            self.assertEqual(len(commands), 11)
            self.assertEqual(result["observations"]["helper_logs"],
                             {"capture_error": "TimeoutExpired"})
            self.assertEqual(result["observations"]["ppu_local_tcp"]["returncode"], 0)
            self.assertEqual(result["observations"]["probe_to_ppu_tcp"]["returncode"], 0)
            self.assertEqual(result["observations"]["probe_arp"]["returncode"], 0)

    def test_diagnostic_capture_failure_does_not_override_original_error(self):
        with tempfile.TemporaryDirectory() as temp:
            bad_work = Path(temp) / "nonexistent"
            with patch.object(phase2.subprocess, "run", side_effect=OSError("unavailable")):
                # Writes may fail and must not raise.
                phase2._capture_failure_diagnostics(
                    bad_work, "ppu", "helper", "probe", {}
                )
            self.assertFalse((bad_work / "failure-diagnostics.json").exists())


if __name__ == "__main__":
    unittest.main()

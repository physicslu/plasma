"""No Docker / no Z2 regression for PPU Phase 2 bootstrap gate."""
from __future__ import annotations

import importlib.util
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/ppu-network-phase2-acceptance.py"
SPEC = importlib.util.spec_from_file_location("ppu_phase2_bootstrap", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
phase2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase2)


class BootstrapGateTests(unittest.TestCase):
    def test_control_preflight_uses_immutable_docker_ip_and_verified_identity(self):
        with patch.object(phase2, "_wait_reachable",
                          return_value={"ppu": {"ppu_id": phase2.PPU_ID}}) as wait:
            self.assertEqual(phase2._wait_gateway_bootstrap_control("probe"), phase2.PPU_ID)
        wait.assert_called_once_with("probe", phase2.PPU_CONTROL_IP, timeout_s=30.0)

    def test_wrong_identity_fails_closed(self):
        with patch.object(phase2, "_wait_reachable",
                          return_value={"ppu": {"ppu_id": "wrong-ppu"}}):
            with self.assertRaisesRegex(phase2.AcceptanceError, "unexpected bootstrap"):
                phase2._wait_gateway_bootstrap_control("probe")

    def test_absent_gateway_does_not_bypass_any_network_check(self):
        with patch.object(phase2, "_wait_reachable",
                          side_effect=phase2.AcceptanceError("gateway not ready")):
            with self.assertRaisesRegex(phase2.AcceptanceError, "gateway not ready"):
                phase2._wait_gateway_bootstrap_control("probe")

    def test_unchanged_management_gate_follows_bootstrap(self):
        host = inspect.getsource(phase2._host_mode)
        self.assertLess(host.index("_wait_gateway_bootstrap_control(probe)"),
                        host.index("_wait_reachable(probe, INITIAL_IP)"))
        self.assertIn("initial_ppu_id != bootstrap_ppu_id", host)
        self.assertIn("if initial_ppu_id != PPU_ID", host)
        self.assertIn("_wait_unreachable(probe,INITIAL_IP)", host)
        self.assertIn("ROLLBACK_TIMEOUT_S", host)
        self.assertEqual(inspect.signature(phase2._wait_reachable).parameters[
            "timeout_s"].default, 8.0)


if __name__ == "__main__":
    unittest.main()

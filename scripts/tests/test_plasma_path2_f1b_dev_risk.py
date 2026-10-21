#!/usr/bin/env python3
"""Bound-passive F1-B one-session exception; Host-only tests, never real HIL."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from pl.hil import path2_f1b_dev_risk as dev
from pl.hil import path2_z2_target_guard as guard


def facts(**overrides):
    r = {
        "root": True, "boot_id": "z2-current-boot-123",
        "manager_state": "operating",
        "recovery_sha256": dev.f1b.BASE_SHA,
        "candidate_sha256": dev.f1b.BIN_SHA,
        "uio_overlaps": ["uio1"],
        "platform_overlaps": ["40000000.axi_fabric"],
        "proc_complete": True, "proc_conflicts": [],
        "observation_kind": "LIVE_ROOT_READ_ONLY",
        "axi_isolation_evidence": "UNPROVEN",
        "active_image_attestation": "UNPROVEN",
    }
    r.update(overrides)
    return r


def check(*, passive=None, uio=None, approval=dev.WAIVER,
          scope=dev.ALLOWED[0], original_manager_load=
          "fpga_manager fpga0: writing base.bin to Xilinx FPGA Manager",
          service_snapshot=None):
    return dev.check_exact(
        passive=facts() if passive is None else passive,
        uio=dict(dev.FIXED_UIO) if uio is None else uio,
        approval=approval, scope=scope,
        original_manager_load=original_manager_load,
        service_snapshot={"plasma-server": "active"} if
        service_snapshot is None else service_snapshot)


class ScopeTests(unittest.TestCase):
    def test_exact_bounded_waiver_does_not_grant_loader(self):
        result = check()
        self.assertEqual(result["site"], 1)
        self.assertEqual(result["bit_sha256"], dev.f1b.BIT_SHA)
        self.assertEqual(result["bin_sha256"], dev.f1b.BIN_SHA)
        self.assertEqual(result["recovery_sha256"], dev.f1b.BASE_SHA)
        self.assertFalse(result["production_qualification"])
        self.assertEqual(result["provider"], dev.NO_OP)
        self.assertIn("UNPROVEN", result["axi_isolation"])
        self.assertTrue(result["manual_recovery_on_timeout_or_unknown"])

    def test_no_unscoped_waiver_or_reused_one_shot_ack(self):
        for ack, scope in [
            ("F1B_ONE_SHOT_BOUND_PASSIVE_UIO", dev.ALLOWED[0]),
            (dev.WAIVER, "PRODUCTION"),
            (dev.WAIVER, "SITE2"),
            ("", dev.ALLOWED[0]),
        ]:
            with self.subTest(ack=ack, scope=scope):
                with self.assertRaisesRegex(dev.BoundedRiskDenied,
                                            "OWNER_DEV_RISK_SCOPE_DENIED"):
                    check(approval=ack, scope=scope)

    def test_any_changed_uio_state_is_no_go(self):
        bad = [
            {"driver": "vfio-platform"},
            {"uio": "uio2"},
            {"maps": [[0x40001000, 0x10000]]},
            {"runtime": "active"},
            {"irq_counts": [1, 0]},
        ]
        for b in bad:
            with self.subTest(changed=b):
                u = dict(dev.FIXED_UIO, **b)
                with self.assertRaisesRegex(dev.BoundedRiskDenied,
                                            "BOUND_UIO_EXACT_FACTS_CHANGED"):
                    check(uio=u)

    def test_other_driver_retained_owner_and_stale_proc_denied(self):
        bad = [
            {"uio_overlaps": ["uio1", "uio2"]},
            {"platform_overlaps": ["40000000.axi_fabric",
                                   "40001000.other"]},
            {"platform_overlaps": []},
            {"proc_complete": False},
            {"proc_conflicts": ["901"]},
            {"root": False},
            {"manager_state": "write err"},
            {"candidate_sha256": "0" * 64},
            {"recovery_sha256": "0" * 64},
            {"observation_kind": "HISTORICAL_ONE_SHOT"},
        ]
        for c in bad:
            with self.subTest(changed=c):
                with self.assertRaises(dev.BoundedRiskDenied):
                    check(passive=facts(**c))

    def test_no_base_manager_provenance_or_services_denied(self):
        with self.assertRaisesRegex(dev.BoundedRiskDenied, "ORIGINAL_BOOT_LOAD"):
            check(original_manager_load="fpga_manager fpga0: writing other.bin to FPGA")
        with self.assertRaisesRegex(dev.BoundedRiskDenied, "ORIGINAL_SERVICE"):
            check(service_snapshot={"plasma-server": "failed"})

    def test_new_risk_must_explicitly_remain_unproven(self):
        with self.assertRaisesRegex(dev.BoundedRiskDenied,
                                    "RISKS_MUST_REMAIN_EXPLICIT"):
            check(passive=facts(axi_isolation_evidence="VERIFIED"))
        with self.assertRaisesRegex(dev.BoundedRiskDenied,
                                    "RISKS_MUST_REMAIN_EXPLICIT"):
            check(passive=facts(active_image_attestation="PASS"))

    def test_root_live_collector_not_allowed_without_target_lock(self):
        class NoLock:
            def _require_locked(self):
                raise guard.TargetSafetyDenied("FPGA_OWNER_LOCK_REQUIRED")
        with self.assertRaisesRegex(guard.TargetSafetyDenied,
                                    "FPGA_OWNER_LOCK_REQUIRED"):
            dev.collect_live(root_port=NoLock(), approval=dev.WAIVER,
                             scope=dev.ALLOWED[0])

    def test_no_dispatcher_access_or_hardware_side_effect(self):
        code = (ROOT / "pl/hil/path2_f1b_dev_risk.py").read_text()
        self.assertNotIn("manager_write(", code)
        self.assertNotIn("subprocess", code)
        self.assertNotIn("load_candidate_once(", code)
        self.assertNotIn("sudo ", code)
        self.assertNotIn("if __name__ ==", code)
        dispatcher = (ROOT / "scripts/plasma_development_dispatch.py").read_text()
        self.assertIn("return integration.disabled_hardware_stage", dispatcher)


if __name__ == "__main__":
    unittest.main()

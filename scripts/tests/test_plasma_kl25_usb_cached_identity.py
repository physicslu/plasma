#!/usr/bin/env python3
"""Host-only positive/negative contracts; never enumerate host USB devices."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plasma_kl25_usb_cached_identity as usb
import plasma_development_dispatch as dispatch


class CachedUsbTests(unittest.TestCase):
    def test_fixture_only_cached_fields_and_no_serial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev = root / "1-2.3"
            dev.mkdir()
            for key, val in {"idVendor": "0403\n", "idProduct": "6010\n",
                             "product": "USB Adapter\n",
                             "serial": "SECRET-NEVER-EXPORT\n"}.items():
                (dev / key).write_text(val, encoding="utf-8")
            (root / "1-2.3:1.0").mkdir()
            result = usb.observe(root)
        self.assertEqual(result["status"], "PASSIVE_CACHE_READ")
        self.assertEqual(result["devices"], [{"topology": "1-2.3",
            "vid": "0403", "pid": "6010", "device_name": "USB Adapter"}])
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(result["usb_transfer"], "NOT_RUN")
        self.assertEqual(result["target_identity"], "NOT_CHECKED")

    def test_missing_and_malformed_sysfs_are_not_identity_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "2-4"
            invalid.mkdir()
            (invalid / "idVendor").write_text("not-a-hex-id")
            (invalid / "idProduct").write_text("6010")
            self.assertEqual(usb.observe(root)["devices"], [])
        self.assertEqual(usb.observe(Path("/nonexistent/plasma-usb-fixture"))
                         ["status"], "SYSFS_UNAVAILABLE")

    def test_dynamic_contract_does_not_accept_command_or_pr(self):
        order = {"schema": dispatch.WORK_ORDER_SCHEMA,
                 "objective": "Read cached USB identities and topology only.",
                 "acceptance": "No device open, transfer, or target operation.",
                 "execution_path": "path2-cli", "capability": "usb-passive-readonly",
                 "scope": "cached-usb-sysfs-only"}
        event = {"comment": {"body": dispatch.WORK_ORDER_PREFIX +
                              json.dumps(order)}}
        self.assertEqual(dispatch.parse_dynamic_work_order(event), order)
        for change in ({"scope": "guarded-hardware"},
                       {"script": "scripts/experiments/arbitrary.py"},
                       {"argv": ["openocd"]}, {"pr_number": 123,
                                                 "source_sha": "a" * 40}):
            altered = {**order, **change}
            event["comment"]["body"] = dispatch.WORK_ORDER_PREFIX + json.dumps(altered)
            with self.assertRaises(dispatch.Denied):
                dispatch.parse_dynamic_work_order(event)

    def test_worker_requires_trusted_main_and_never_spawns(self):
        task = {"capability": "usb-passive-readonly"}
        approval = {"execution_capability": "usb-passive-readonly",
                    "execution_path": "path2-cli", "task_id": "path2-work-order",
                    "pr_number": 0, "pinned_sha": "a" * 40,
                    "trusted_sha": "a" * 40}
        with patch.object(usb, "observe", return_value={"status": "PASSIVE_CACHE_READ",
                           "devices": [], "usb_transfer": "NOT_RUN"}) as observer:
            receipt = dispatch.run_task(task, approval=approval,
                                        executor=lambda *a, **k: self.fail("spawn"))
            self.assertEqual(receipt["status"], "PASS")
            observer.assert_called_once_with()
        for fields in ({"pr_number": 42}, {"pinned_sha": "b" * 40},
                       {"execution_path": "path3-codex"}):
            with self.assertRaises(dispatch.Denied):
                dispatch.run_task(task, approval={**approval, **fields})


if __name__ == "__main__":
    unittest.main()

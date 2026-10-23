#!/usr/bin/env python3
"""Offline unit tests: no SWPC group/udev/hardware operations."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[2] / "scripts/plasma-codex-hardware-parity.py"
spec = importlib.util.spec_from_file_location("plasma_codex_hardware_parity", PATH)
assert spec and spec.loader
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ParityTests(unittest.TestCase):
    def test_strict_udev_identity_and_tty_scope(self) -> None:
        p.self_test()
        rules = p.render_rules()
        self.assertEqual(rules.count('MODE="0660"'), 7)
        self.assertNotIn('MODE="0666"', rules)
        self.assertNotIn("SUBSYSTEM==\"block\"", rules)
        self.assertIn("GROUP=\"plasma-codex-io\"", rules)
        self.assertIn('ATTR{idVendor}=="0483", ATTR{idProduct}=="374f"', rules)
        self.assertIn('ATTR{idVendor}=="cafe", ATTR{idProduct}=="4001"', rules)
        self.assertIn('KERNEL=="ttyACM[0-9]*", ATTRS{idVendor}=="cafe", '
                      'ATTRS{idProduct}=="4001"', rules)
        self.assertNotIn('KERNEL=="ttyACM[0-9]*", ATTRS{idVendor}=="0483"', rules)
        self.assertEqual(p.render_rules(legacy=True).count('MODE="0660"'), 4)

    def test_existing_conflict_and_symlink_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            r = Path(root)
            existing = r / "rules"
            existing.write_text("owner-managed rules\n")
            self.assertEqual(p.file_state(existing, p.render_rules()), "CONFLICT_REFUSED")
            with self.assertRaises(RuntimeError):
                p.install_exact(existing, p.render_rules(), 0o644)
            link = r / "link"
            link.symlink_to(existing)
            self.assertEqual(p.file_state(link), "SYMLINK_REFUSED")
            with self.assertRaises(RuntimeError):
                p.install_exact(link, p.render_wrapper(), 0o755)
            self.assertEqual(existing.read_text(), "owner-managed rules\n")


    def test_unix_mode_comparison_is_not_an_acl_claim(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "usb-mock"
            path.write_bytes(b"")
            path.chmod(0o660)
            m = path.stat()
            self.assertTrue(p.unix_mode_rw(m, m.st_uid, set()))
            self.assertTrue(p.unix_mode_rw(m, m.st_uid + 1, {m.st_gid}))
            self.assertFalse(p.unix_mode_rw(m, m.st_uid + 1, set()))

    def test_install_exact_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            f = Path(root) / "udev" / "rules"
            self.assertEqual(p.install_exact(f, p.render_rules(), 0o644), "INSTALLED")
            self.assertEqual(p.install_exact(f, p.render_rules(), 0o644), "UNCHANGED")
            self.assertEqual(f.read_text(), p.render_rules())
            self.assertEqual(f.stat().st_mode & 0o777, 0o644)

    def test_only_exact_prior_managed_udev_rules_can_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "rules"
            old = p.render_rules(legacy=True)
            new = p.render_rules()
            path.write_text(old)
            with patch.object(p, "RULE_FILE", path):
                self.assertEqual(p.managed_rule_state(),
                                 "LEGACY_EXACT_UPGRADE_AVAILABLE")
                self.assertEqual(p.install_exact(path, new, 0o644, previous=old),
                                 "UPDATED")
                self.assertEqual(path.read_text(), new)
                self.assertEqual(p.managed_rule_state(), "EXACT")
                self.assertEqual(p.install_exact(path, new, 0o644, previous=old),
                                 "UNCHANGED")
                path.write_text(old + "# owner edit\n")
                self.assertEqual(p.managed_rule_state(), "CONFLICT_REFUSED")
                with self.assertRaises(RuntimeError):
                    p.install_exact(path, new, 0o644, previous=old)
                self.assertEqual(path.read_text(), old + "# owner edit\n")

    def test_la_exact_checksum_and_no_source_modification(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            r = Path(root)
            original = r / "original.AppImage"
            original.write_bytes(b"local test mock, NOT a real AppImage")
            old = original.read_bytes()
            target = r / "dest" / "LA.AppImage"
            wrapper = r / "bin" / "LA-wrapper"
            with (
                patch.object(p, "LA_BINARY", target),
                patch.object(p, "LA_WRAPPER", wrapper),
            ):
                with self.assertRaises(RuntimeError):
                    p.install_appimage(original)
                with patch.object(p, "LA_DIGEST", hashlib.sha256(old).hexdigest()):
                    self.assertEqual(p.install_appimage(original), "INSTALLED")
                    self.assertEqual(p.install_appimage(original), "UNCHANGED")
                self.assertEqual(original.read_bytes(), old)
                self.assertEqual(target.read_bytes(), old)
                self.assertEqual(wrapper.read_text(), p.render_wrapper())

    def test_admin_apply_scoped_and_no_device_operation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            r = Path(root)
            calls: list[list[str]] = []
            def fake_run(cmd: list[str]) -> None:
                calls.append(cmd)
            with (
                patch.object(p, "RULE_FILE", r / "rules.d" / "specific.rules"),
                patch.object(p, "require_safe_admin"),
                patch.object(p, "current_groups", return_value=[]),
                patch.object(p.grp, "getgrnam", side_effect=KeyError),
                patch.object(p, "run_admin", side_effect=fake_run),
            ):
                p.apply()
                self.assertTrue((r / "rules.d" / "specific.rules").exists())
            self.assertEqual(calls[0], ["groupadd", "--system", "plasma-codex-io"])
            self.assertEqual(calls[1], ["usermod", "--append", "--groups",
                                        "plasma-codex-io", "gordon"])
            self.assertEqual(calls[2], ["usermod", "--append", "--groups",
                                        "plasma-codex-io", "plasma-codex"])
            self.assertEqual(calls[3], ["udevadm", "control", "--reload"])
            self.assertEqual(len(calls), 4)
            self.assertNotIn("systemctl", repr(calls))
            self.assertNotIn("ssh", repr(calls))
            self.assertNotIn("uhubctl", repr(calls))


if __name__ == "__main__":
    unittest.main()

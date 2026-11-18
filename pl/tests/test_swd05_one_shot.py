"""Offline-only one-shot recovery state machine tests. NEVER access Z2 devices."""
from __future__ import annotations

import unittest
from pl.hil.swd04.one_shot import run_protected
from pl.hil.swd04 import one_shot
from unittest.mock import patch
from pathlib import Path


class OneShotSupervisorTests(unittest.TestCase):
    def run_scenario(self, fail="", events=None):
        events = events if events is not None else []
        def callback(name):
            def call():
                events.append(name)
                if name == fail:
                    raise RuntimeError("injected failure")
            return call
        state = run_protected(
            preflight=callback("preflight"),
            load_candidate=callback("load"),
            hil01=callback("hil01"),
            hil02=callback("hil02"),
            restore=callback("restore"),
            verify_restoration=callback("verify"))
        return events, state

    def test_happy_path_restores_original_after_hil02(self):
        events, state = self.run_scenario()
        self.assertEqual(events,
                         ["preflight", "load", "hil01", "hil02", "restore", "verify"])
        self.assertEqual(state["overall"], "PASS_DEVELOPMENT_INTERNAL_FIXTURE")
        self.assertEqual(state["restoration_verified"], "PASS")

    def test_preflight_failure_never_loads_or_attempts_restore(self):
        events, state = self.run_scenario(fail="preflight")
        self.assertEqual(events, ["preflight"])
        self.assertEqual(state["candidate_load"], "NOT_RUN")
        self.assertEqual(state["restore"], "NOT_RUN")
        self.assertEqual(state["overall"], "FAIL_OR_BLOCKED")

    def test_load_failure_marks_touch_before_write_and_restores(self):
        events, state = self.run_scenario(fail="load")
        self.assertEqual(events, ["preflight", "load", "restore", "verify"])
        self.assertEqual(state["candidate_load"], "NOT_RUN")
        self.assertNotEqual(state["overall"], "PASS_DEVELOPMENT_INTERNAL_FIXTURE")

    def test_hil01_failure_skips_hil02_and_restores(self):
        events, state = self.run_scenario(fail="hil01")
        self.assertEqual(events, ["preflight", "load", "hil01", "restore", "verify"])
        self.assertEqual(state["hil02"], "NOT_RUN")
        self.assertEqual(state["restoration_verified"], "PASS")

    def test_hil02_failure_restores_no_retry(self):
        events, state = self.run_scenario(fail="hil02")
        self.assertEqual(events, ["preflight", "load", "hil01", "hil02", "restore", "verify"])
        self.assertEqual(state["overall"], "FAIL_OR_BLOCKED")

    def test_failed_restore_is_never_reported_pass(self):
        events, state = self.run_scenario(fail="restore")
        self.assertEqual(events, ["preflight", "load", "hil01", "hil02", "restore"])
        self.assertEqual(state["restore"], "FAIL_OR_UNKNOWN")
        self.assertEqual(state["overall"], "NO_GO")

    def test_failed_post_restore_audit_is_never_reported_pass(self):
        events, state = self.run_scenario(fail="verify")
        self.assertEqual(events, ["preflight", "load", "hil01", "hil02", "restore", "verify"])
        self.assertEqual(state["restoration_verified"], "FAIL_OR_UNKNOWN")
        self.assertEqual(state["overall"], "NO_GO")


class LegacyPathRetirementTests(unittest.TestCase):
    def test_retired_default_swd05_sequence_denied_before_physical_preflight(self):
        """The retired default sequence must never reach artifacts or hardware."""
        with patch.object(one_shot, "verify_inputs",
                          side_effect=AssertionError("must not touch preflight")):
            with self.assertRaisesRegex(one_shot.c.SafetyError,
                                        "RETIRED_SWD05_INTERNAL_SEQUENCE_NO_CALLBACK"):
                one_shot.run_live(object())


if __name__ == "__main__":
    unittest.main()

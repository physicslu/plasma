#!/usr/bin/env python3
"""Host-only tests for the non-authorizing Path 2/3 SSH tmux monitor."""
from __future__ import annotations

import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_engineering_monitor as mon
import plasma_development_dispatch as dev

WORKFLOW = ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
FIXED_NOW = dt.datetime(2026, 10, 21, 16, 10, 0, tzinfo=TAIPEI)


class EngineeringMonitorTests(unittest.TestCase):
    def test_both_panes_idle_without_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.assertIn("STATUS: IDLE", mon.render_snapshot(base, "path2"))
            self.assertIn("STATUS: IDLE", mon.render_snapshot(base, "path3"))
            self.assertFalse(list(base.iterdir()))

    def test_path2_success_returns_idle_and_last_pass(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {
                "GITHUB_RUN_ID": "39546002",
                "PLASMA_MONITOR_TASK": "nine-nine-path2",
            }):
                rc = mon.run_job("path2", [sys.executable, "-c",
                                           "print('actual CLI output')"],
                                 directory=Path(td))
            self.assertEqual(rc, 0)
            state = json.loads((Path(td) / "path2.json").read_text())
            self.assertEqual(state["status"], "IDLE")
            self.assertEqual(state["last_result"], "PASS")
            self.assertEqual(state["run_id"], "39546002")
            self.assertIn("LAST: PASS", mon.render_snapshot(Path(td), "path2"))
            self.assertIn("STAGE: (not available)", mon.render_snapshot(Path(td), "path2"))

    def test_path2_authorized_goal_stage_and_clock_on_real_wrapper(self):
        with tempfile.TemporaryDirectory() as td:
            data = {
                "GITHUB_RUN_ID": "40056557048",
                "PLASMA_MONITOR_TASK": "path2-work-order",
                "PR_NUMBER": "1144",
                "WORK_ORDER_SHA256": "a" * 64,
                "PLASMA_MONITOR_SUMMARY": "PATH2 Host-only CLI regression",
                "PLASMA_MONITOR_STAGE": "CPU-only CLI",
            }
            probe = Path(td) / "child-env.txt"
            code = ("import os,sys,pathlib;pathlib.Path(sys.argv[1]).write_text("
                    "str('PLASMA_MONITOR_SUMMARY' in os.environ)+' '+"
                    "str('PLASMA_MONITOR_STAGE' in os.environ))")
            with patch.dict(os.environ, data, clear=True):
                self.assertEqual(mon.run_job(
                    "path2", [sys.executable, "-c", code, str(probe)],
                    directory=Path(td)), 0)
            self.assertEqual(probe.read_text(), "False False")
            state = json.loads((Path(td) / "path2.json").read_text())
            self.assertEqual(state["monitor_summary"], data["PLASMA_MONITOR_SUMMARY"])
            self.assertEqual(state["monitor_stage"], "CPU-only CLI")
            frame = mon.render_snapshot(
                Path(td), "path2", width=120, height=24, now=FIXED_NOW)
            self.assertIn("GOAL: PATH2 Host-only CLI regression", frame)
            self.assertIn("STAGE: CPU-only CLI", frame)
            self.assertIn("PR: #1144", frame)
            self.assertIn("NOW: 2026-10-21 16:10", frame)
            self.assertIn("LAST: PASS  EXIT: 0", frame)
            self.assertNotIn(data["PLASMA_MONITOR_SUMMARY"],
                             (Path(td) / "path2.log").read_text())
            self.assertNotIn("WORK_ORDER_SHA256", frame)

    def test_path2_rejects_untrusted_stage_or_summary(self):
        cases = [
            ("", "CPU-only CLI", "PATH2 Host-only CLI regression"),
            ("a"*64, "Erase entire DUT", "PATH2 Host-only CLI regression"),
            ("a"*64, "Guarded Download", "token SECRET in text"),
            ("bad-hash", "Guarded Restore", "PATH2 Host-only CLI regression"),
        ]
        for sha, stage, summary in cases:
            with self.subTest(sha=sha, stage=stage):
                with tempfile.TemporaryDirectory() as td:
                    with patch.dict(os.environ, {
                        "GITHUB_RUN_ID": "40056557048",
                        "PLASMA_MONITOR_TASK": "path2-work-order",
                        "WORK_ORDER_SHA256": sha,
                        "PLASMA_MONITOR_SUMMARY": summary,
                        "PLASMA_MONITOR_STAGE": stage,
                    }, clear=True):
                        self.assertEqual(mon.run_job(
                            "path2", [sys.executable, "-c", "pass"],
                            directory=Path(td)), 0)
                    state = json.loads((Path(td) / "path2.json").read_text())
                    frame = mon.render_snapshot(Path(td), "path2")
                    if not sha or sha == "bad-hash":
                        self.assertEqual(state["monitor_summary"], "")
                        self.assertIn(
                            "GOAL: (operator summary not provided)", frame)
                    else:
                        self.assertNotIn("token SECRET", frame)
                    if stage == "Erase entire DUT" or sha == "bad-hash":
                        self.assertEqual(state["monitor_stage"], "")
                        self.assertIn("STAGE: (not available)", frame)

    def test_exact_registered_path2_static_hil_label_and_denial(self):
        for task, stage in (
            ("z2-path2-download", "Guarded Download"),
            ("z2-path2-testing", "Guarded Test"),
            ("z2-path2-restore", "Guarded Restore"),
            ("z2-path2-full-hil", "Guarded Full HIL"),
        ):
            with self.subTest(task=task):
                with tempfile.TemporaryDirectory() as td:
                    with patch.dict(os.environ, {
                        "GITHUB_RUN_ID": "40056557048",
                        "PLASMA_MONITOR_TASK": task,
                        "PLASMA_MONITOR_STAGE": stage,
                    }, clear=True):
                        self.assertEqual(mon.run_job(
                            "path2", [sys.executable, "-c", "pass"],
                            directory=Path(td)), 0)
                    state = json.loads((Path(td) / "path2.json").read_text())
                    self.assertEqual(state["monitor_stage"], stage)
                    frame = mon.render_snapshot(Path(td), "path2")
                    self.assertIn("STAGE: " + stage, frame)
                    self.assertIn("GOAL: (operator summary not provided)", frame)
        # The same label must not be accepted for an unrelated static task.
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {
                "PLASMA_MONITOR_TASK": "nine-nine-path2",
                "PLASMA_MONITOR_STAGE": "Guarded Full HIL",
            }, clear=True):
                self.assertEqual(mon.run_job(
                    "path2", [sys.executable, "-c", "pass"],
                    directory=Path(td)), 0)
            self.assertIn("STAGE: (not available)",
                          mon.render_snapshot(Path(td), "path2"))

    def test_shared_100_column_terminal_cap_with_cjk(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for path, task in (("path2", "path2-work-order"),
                               ("path3", "path3-work-order")):
                (d / (path + ".json")).write_text(json.dumps({
                    "status": "IDLE", "task": task, "run_id": "42",
                    "monitor_summary": "測試測試測試測試 " + "A"*65,
                    "monitor_stage": "CPU-only CLI",
                }))
                (d / (path + ".log")).write_text("X"*180 + "\n")
                for width in (28, 80, 100, 150):
                    with self.subTest(path=path, width=width):
                        frame = mon.render_snapshot(
                            d, path, width=width, height=24,
                            now=FIXED_NOW)
                        available = max(0, min(width - 1, 100))
                        for line in frame.splitlines():
                            self.assertEqual(
                                line, mon._clip_columns(line, available))
                        self.assertIn("NOW:", frame)
                        self.assertIn("RECENT OUTPUT", frame)

    def test_authorized_task_and_pr_are_visible_without_work_order_text(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {
                "GITHUB_RUN_ID": "40056557048",
                "PLASMA_MONITOR_TASK": "path3-work-order",
                "PR_NUMBER": "1143",
            }):
                self.assertEqual(mon.run_job(
                    "path3", [sys.executable, "-c", "pass"],
                    directory=Path(td)), 0)
            state = json.loads((Path(td) / "path3.json").read_text())
            self.assertEqual(state["task"], "path3-work-order")
            self.assertEqual(state["pr_number"], "1143")
            frame = mon.render_snapshot(Path(td), "path3")
            self.assertIn("TASK: path3-work-order", frame)
            self.assertIn("PR: #1143", frame)

    def test_path3_only_displays_digest_bound_public_summary(self):
        with tempfile.TemporaryDirectory() as td:
            data = {
                "GITHUB_RUN_ID": "40056557048",
                "PLASMA_MONITOR_TASK": "path3-work-order",
                "PR_NUMBER": "1143",
                "WORK_ORDER_SHA256": "a" * 64,
                "PLASMA_MONITOR_SUMMARY":
                    "STM32F103 Low-density L1-L2 provider audit",
            }
            env_probe = Path(td) / "child-env-probe.txt"
            with patch.dict(os.environ, data, clear=True):
                self.assertEqual(mon.run_job(
                    "path3", [sys.executable, "-c",
                              "import os,pathlib,sys;pathlib.Path(sys.argv[1]).write_text(str('PLASMA_MONITOR_SUMMARY' in os.environ))",
                              str(env_probe)],
                    directory=Path(td)), 0)
            self.assertEqual(env_probe.read_text(), "False")
            state = json.loads((Path(td) / "path3.json").read_text())
            frame = mon.render_snapshot(Path(td), "path3")
            self.assertEqual(
                state["monitor_summary"], data["PLASMA_MONITOR_SUMMARY"])
            self.assertIn(
                "GOAL: STM32F103 Low-density L1-L2 provider audit", frame)
            self.assertNotIn("WORK_ORDER_SHA256", frame)
            self.assertNotIn(data["WORK_ORDER_SHA256"], frame)
            self.assertNotIn(data["PLASMA_MONITOR_SUMMARY"],
                             (Path(td) / "path3.log").read_text())

    def test_path3_summary_fail_closed_without_authorization_binding(self):
        cases = [
            ("", "STM32F103 Low-density provider audit"),
            ("not-a-sha", "STM32F103 Low-density provider audit"),
            ("a" * 64, "token SECRET in text"),
            ("a" * 64, "Run \x1b[31mcommand"),
            ("a" * 64, "STM32F103\nmalicious display"),
            ("a" * 64, "https://example.com/key"),
        ]
        for sha, summary in cases:
            with self.subTest(sha=sha, summary=repr(summary)):
                with tempfile.TemporaryDirectory() as td:
                    with patch.dict(os.environ, {
                        "GITHUB_RUN_ID": "40056557048",
                        "PLASMA_MONITOR_TASK": "path3-work-order",
                        "WORK_ORDER_SHA256": sha,
                        "PLASMA_MONITOR_SUMMARY": summary,
                    }, clear=True):
                        self.assertEqual(mon.run_job(
                            "path3", [sys.executable, "-c", "pass"],
                            directory=Path(td)), 0)
                    state = json.loads((Path(td) / "path3.json").read_text())
                    self.assertEqual(state["monitor_summary"], "")
                    frame = mon.render_snapshot(Path(td), "path3")
                    self.assertIn(
                        "GOAL: (operator summary not provided)", frame)
                    self.assertNotIn(summary, frame)
                    self.assertNotIn("\x1b", frame)

    def test_path3_summary_fits_narrow_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "path3.json").write_text(json.dumps({
                "status": "IDLE", "run_id": "123", "task": "path3-work-order",
                "monitor_summary":
                    "STM32F103 小容量 L1-L2 Provider Audit",
            }))
            frame = mon.render_snapshot(
                directory, "path3", width=28, height=16)
            self.assertIn("GOAL:", frame)
            self.assertTrue(all(
                mon._clip_columns(line, 27) == line
                for line in frame.splitlines()))

    def test_path3_failure_preserves_real_exit_and_idle(self):
        with tempfile.TemporaryDirectory() as td:
            rc = mon.run_job("path3", [sys.executable, "-c",
                                       "import sys; sys.exit(7)"],
                             directory=Path(td))
            self.assertEqual(rc, 7)
            state = json.loads((Path(td) / "path3.json").read_text())
            self.assertEqual(state["status"], "IDLE")
            self.assertEqual(state["exit_code"], 7)
            self.assertEqual(state["last_result"], "FAIL")
            self.assertIn("LAST: FAIL", mon.render_snapshot(Path(td), "path3"))

    def test_stale_worker_is_not_reported_running(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "path3.json").write_text(json.dumps({
                "status": "RUNNING", "pid": 99999999, "proc_start": "123",
                "run_id": "100", "task": "test-task",
            }))
            result = mon.render_snapshot(directory, "path3")
            self.assertIn("IDLE (interrupted/unknown)", result)
            self.assertNotIn("STATUS: RUNNING", result)

    def test_log_render_does_not_interpret_control_characters(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "path3.log").write_bytes(b"ok\n\x1b[31mBAD\x07\n")
            result = mon.render_snapshot(directory, "path3")
            self.assertNotIn("\x1b", result)
            self.assertNotIn("\x07", result)
            self.assertIn("BAD", result)

    def test_real_codex_stream_redacts_event_payload_in_both_sinks(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            live = directory / "path3.log"
            evidence = directory / "codex.log"
            live.touch()
            command = [sys.executable, "-c",
                       "import sys; sys.stdin.read(); "
                       "print('{\"type\":\"thread.started\",\"thread_id\":\"0199a213-81c0-7800-8aa1-bbab2a035a53\"}',flush=True); "
                       "print('{\"type\":\"item.completed\",\"text\":\"PASSWORD_SECRET\"}',flush=True); "
                       "print('{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":30,\"cached_input_tokens\":10,\"output_tokens\":4}}',flush=True); "
                       "print('{\"type\":\"item.started\",\"item\":{\"type\":\"command_execution\",\"command\":\"PASSWORD_SECRET\"}}',flush=True); "
                       "print('{\"type\":\"item.completed\",\"item\":{\"type\":\"command_execution\",\"command\":\"PASSWORD_SECRET\"}}',flush=True); "
                       "print('STDERR_SECRET',file=sys.stderr,flush=True)"]
            usage = dev.CodexUsageCollector()
            rc = dev._run_codex_with_live_log(
                command, b"tiny authorized test\n", directory,
                evidence, str(live), usage=usage)
            self.assertEqual(rc, 0)
            self.assertIn(b"[codex turn.completed]", live.read_bytes())
            self.assertIn(b"[codex turn.completed]", evidence.read_bytes())
            self.assertIn(b"[codex command_execution.started]", live.read_bytes())
            self.assertIn(b"[codex command_execution.completed]", live.read_bytes())
            self.assertIn(b"[codex item.started]", evidence.read_bytes())
            self.assertNotIn(b"command_execution.started", evidence.read_bytes())
            self.assertNotIn(b"PASSWORD_SECRET", live.read_bytes())
            self.assertNotIn(b"PASSWORD_SECRET", evidence.read_bytes())
            self.assertNotIn(b"STDERR_SECRET", live.read_bytes())
            self.assertNotIn(b"STDERR_SECRET", evidence.read_bytes())
            self.assertEqual(usage.snapshot()["input_tokens"], 30)
            self.assertEqual(usage.snapshot()["cached_input_tokens"], 10)
            self.assertEqual(usage.snapshot()["output_tokens"], 4)
            # Synthetic timing goes only to the transient monitor sink.
            mon._append(live, "\n" + mon._monitor_time_mark(FIXED_NOW))
            self.assertIn(b"[MONITOR TIME MARK]", live.read_bytes())
            self.assertNotIn(b"[MONITOR TIME MARK]", evidence.read_bytes())

    def test_monitor_setup_failure_is_only_pre_execution(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            with self.assertRaises(dev.LiveMonitorUnavailable):
                dev._run_codex_with_live_log(
                    [sys.executable, "-c",
                     "raise AssertionError('must not execute')"],
                    b"input", directory, directory / "evidence",
                    str(directory / "missing-live-log"))
            self.assertFalse((directory / "evidence").exists())

    def test_shortcuts_are_visible_at_top_with_configured_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            frame = mon.render_snapshot(
                Path(td), "path3", prefix="Ctrl+A", width=50, height=20)
            self.assertEqual(frame.splitlines()[0], "PATH 3 | SWPC Codex")
            self.assertIn("KEYS: C Clear | Ctrl+A 1/2 Switch", frame)
            self.assertIn("Ctrl+A D Detach", frame)
            self.assertIn("STATUS: IDLE", frame)

    def test_clear_is_display_only_and_new_lines_keep_streaming(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            log = directory / "path3.log"
            original = "old Codex message\n"
            log.write_text(original)
            output = io.StringIO()
            keys = iter([None, "C", None])
            polls = [0]

            def fake_sleep(_seconds):
                polls[0] += 1
                if polls[0] == 2:
                    with log.open("a") as f:
                        f.write("new Codex message\n")
                if polls[0] >= 3:
                    raise StopIteration

            with self.assertRaises(StopIteration):
                mon.view_loop(
                    "path3", directory=directory, output=output,
                    get_size=lambda: os.terminal_size((80, 24)),
                    sleep=fake_sleep, get_now=lambda: FIXED_NOW,
                    get_key=lambda: next(keys))
            frames = output.getvalue().split("\x1b[H")[1:]
            self.assertEqual(len(frames), 3)
            self.assertIn("old Codex message", frames[0])
            self.assertNotIn("old Codex message", frames[1])
            self.assertNotIn("old Codex message", frames[2])
            self.assertIn("new Codex message", frames[2])
            self.assertEqual(log.read_text(),
                             original + "new Codex message\n")
            self.assertFalse((directory / "path3.json").exists())
            self.assertNotIn("\x1b[2J", output.getvalue())

    def test_clear_does_not_hide_next_jobs_first_message(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            log = directory / "path2.log"
            state = directory / "path2.json"
            state.write_text(json.dumps({
                "status": "IDLE", "run_id": "100", "started": "before"}))
            log.write_text("old first line\n")
            clear_from = mon._clear_point(directory, "path2")
            self.assertNotIn("old first line", mon.render_snapshot(
                directory, "path2", clear_from=clear_from))
            # The same log inode is truncated when run_job starts anew.
            log.write_text("new job first line\n")
            state.write_text(json.dumps({
                "status": "IDLE", "run_id": "200", "started": "after"}))
            self.assertIn("new job first line", mon.render_snapshot(
                directory, "path2", clear_from=clear_from))

    def test_view_does_not_redraw_when_idle_is_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            out = io.StringIO()
            polls = [0]

            def fake_sleep(_seconds):
                polls[0] += 1
                if polls[0] == 3:
                    raise StopIteration

            with self.assertRaises(StopIteration):
                mon.view_loop("path3", directory=Path(td), output=out,
                              get_size=lambda: os.terminal_size((80, 24)),
                              sleep=fake_sleep, get_now=lambda: FIXED_NOW)
            self.assertEqual(polls[0], 3)
            self.assertEqual(out.getvalue().count("\x1b[H"), 1)
            self.assertNotIn("\x1b[2J", out.getvalue())
            self.assertIn("STATUS: IDLE", out.getvalue())

    def test_view_repaints_on_terminal_resize(self):
        with tempfile.TemporaryDirectory() as td:
            out = io.StringIO()
            sizes = iter([os.terminal_size((80, 24)),
                          os.terminal_size((80, 24)),
                          os.terminal_size((44, 15))])

            def fake_sleep(_seconds):
                if fake_sleep.count == 2:
                    raise StopIteration
                fake_sleep.count += 1
            fake_sleep.count = 0

            with self.assertRaises(StopIteration):
                mon.view_loop("path2", directory=Path(td), output=out,
                              get_size=lambda: next(sizes), sleep=fake_sleep)
            self.assertEqual(out.getvalue().count("\x1b[H"), 2)
            self.assertEqual(out.getvalue().count("\x1b[H\x1b[J"), 2)
            self.assertNotIn("\x1b[2J", out.getvalue())

    def test_view_repaints_when_status_changes(self):
        with tempfile.TemporaryDirectory() as td:
            out = io.StringIO()
            directory = Path(td)
            polls = [0]

            def fake_sleep(_seconds):
                polls[0] += 1
                if polls[0] == 1:
                    (directory / "path3.json").write_text(json.dumps({
                        "status": "IDLE", "run_id": "12345", "task": "test-task",
                        "last_result": "PASS", "exit_code": 0,
                    }))
                else:
                    raise StopIteration

            with self.assertRaises(StopIteration):
                mon.view_loop("path3", directory=directory, output=out,
                              get_size=lambda: os.terminal_size((80, 24)),
                              sleep=fake_sleep, get_now=lambda: FIXED_NOW)
            self.assertEqual(out.getvalue().count("\x1b[H"), 2)
            self.assertIn("RUN: 12345  TASK: test-task", out.getvalue())
            self.assertIn("LAST: PASS  EXIT: 0", out.getvalue())

    def test_log_is_clipped_to_pane_without_scrolling_status_offscreen(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "path3.log").write_text(
                "".join(f"line-{i:03d}: " + ("中" * 60) + "\n"
                        for i in range(60)))
            frame = mon.render_snapshot(directory, "path3", width=38, height=12)
            lines = frame.splitlines()
            # One spare row prevents scrolling even with a trailing clear.
            self.assertLessEqual(len(lines), 11)
            self.assertTrue(all(mon._clip_columns(line, 37) == line
                                for line in lines))
            self.assertIn("STATUS: IDLE", frame)
            self.assertIn("RECENT OUTPUT", frame)
            self.assertIn("line-059:", frame)
            self.assertNotIn("line-001:", frame)

    def test_both_paths_keep_latest_log_in_short_12_row_pane(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            for path in ("path2", "path3"):
                (directory / (path + ".json")).write_text(json.dumps({
                    "status": "IDLE",
                    "run_id": "12345",
                    "task": path + "-work-order",
                    "pr_number": "1144",
                    "monitor_summary": "STM32F103 Low-density provider audit",
                    "monitor_stage": "CPU-only CLI",
                }))
                (directory / (path + ".log")).write_text(
                    "".join(f"old-{i:03d}\n" for i in range(20)) +
                    "latest-visible-entry\n")
                frame = mon.render_snapshot(
                    directory, path, width=38, height=12, now=FIXED_NOW)
                with self.subTest(path=path):
                    self.assertLessEqual(len(frame.splitlines()), 11)
                    self.assertIn("STATUS: IDLE", frame)
                    self.assertIn("RUN: 12345", frame)
                    self.assertIn("PR: #1144", frame)
                    self.assertIn("GOAL:", frame)
                    if path == "path2":
                        self.assertIn("STAGE: CPU-only CLI", frame)
                    self.assertIn("LAST: NOT_RUN", frame)
                    self.assertIn("NOW: 2026-10-21 16:10", frame)
                    self.assertIn("RECENT OUTPUT", frame)
                    self.assertIn("latest-visible-entry", frame)
                    self.assertNotIn("old-000", frame)

    def test_both_paths_use_local_clock_without_iso_offset(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            before = mon.render_snapshot(directory, "path3", now=FIXED_NOW)
            same_minute = mon.render_snapshot(
                directory, "path3", now=FIXED_NOW.replace(second=59))
            next_minute = mon.render_snapshot(
                directory, "path3", now=FIXED_NOW + dt.timedelta(minutes=1))
            self.assertEqual(before, same_minute)
            self.assertNotEqual(before, next_minute)
            self.assertIn("NOW: 2026-10-21 16:10", before)
            self.assertIn("NOW: 2026-10-21 16:11", next_minute)
            self.assertIn("NOW: 2026-10-21 16:10", mon.render_snapshot(
                directory, "path2", now=FIXED_NOW))
            for path in ("path2", "path3"):
                frame = mon.render_snapshot(directory, path, now=FIXED_NOW)
                self.assertNotIn("2026-10-21T16:10", frame)
                self.assertNotIn("+08:00", frame)
                self.assertNotIn("NOW: 2026-10-21 16:10:00", frame)
            with self.assertRaisesRegex(
                    ValueError, "timezone-aware timestamp"):
                mon.render_snapshot(
                    directory, "path2",
                    now=dt.datetime(2026, 10, 21, 16, 10))

    def test_path3_view_redraws_once_at_minute_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            output = io.StringIO()
            readings = iter([FIXED_NOW.replace(second=1),
                             FIXED_NOW.replace(second=59),
                             FIXED_NOW + dt.timedelta(minutes=1)])
            polls = [0]

            def fake_sleep(_seconds):
                polls[0] += 1
                if polls[0] >= 3:
                    raise StopIteration

            with self.assertRaises(StopIteration):
                mon.view_loop("path3", directory=Path(td), output=output,
                              get_size=lambda: os.terminal_size((80, 24)),
                              sleep=fake_sleep, get_now=lambda: next(readings))
            self.assertEqual(output.getvalue().count("\x1b[H"), 2)
            self.assertNotIn("\x1b[2J", output.getvalue())
            self.assertIn("NOW: 2026-10-21 16:10", output.getvalue())
            self.assertIn("NOW: 2026-10-21 16:11", output.getvalue())

    def test_path3_time_marks_only_after_60_elapsed_seconds(self):
        class FakeProcess:
            def __init__(self):
                self.poll_count = 0

            def poll(self):
                self.poll_count += 1
                return None if self.poll_count <= 5 else 0

            def wait(self):
                return 0

        with tempfile.TemporaryDirectory() as td:
            seconds = [0]
            steps = iter([15, 15, 29, 1, 60])

            def fake_sleep(_duration):
                seconds[0] += next(steps)

            with patch.object(mon.subprocess, "Popen", return_value=FakeProcess()), \
                 patch.object(mon.time, "monotonic",
                              side_effect=lambda: seconds[0]), \
                 patch.object(mon.time, "sleep", side_effect=fake_sleep), \
                 patch.object(mon, "_monitor_time_mark",
                              return_value=mon._monitor_time_mark(FIXED_NOW)):
                rc = mon.run_job("path3", ["fake-codex"], directory=Path(td))
            self.assertEqual(rc, 0)
            log = (Path(td) / "path3.log").read_text()
            self.assertEqual(log.count("[MONITOR TIME MARK]"), 2)
            self.assertIn("[MONITOR TIME MARK] 2026-10-21T16:10:00+08:00", log)
            self.assertIn("PASS | exit=0", log)
            state = json.loads((Path(td) / "path3.json").read_text())
            self.assertEqual(state["last_result"], "PASS")

    def test_path2_does_not_emit_codex_time_mark(self):
        class FakeProcess:
            def __init__(self):
                self.poll_count = 0

            def poll(self):
                self.poll_count += 1
                return None if self.poll_count <= 1 else 0

            def wait(self):
                return 0

        with tempfile.TemporaryDirectory() as td:
            seconds = [0]

            def fake_sleep(_duration):
                seconds[0] += 120

            with patch.object(mon.subprocess, "Popen", return_value=FakeProcess()), \
                 patch.object(mon.time, "monotonic",
                              side_effect=lambda: seconds[0]), \
                 patch.object(mon.time, "sleep", side_effect=fake_sleep):
                rc = mon.run_job("path2", ["fake-cli"], directory=Path(td))
            self.assertEqual(rc, 0)
            self.assertNotIn("MONITOR TIME MARK",
                             (Path(td) / "path2.log").read_text())

    def test_two_window_launcher_scenarios(self):
        """Stateful fake tmux/sg; never connects to a real host/socket."""
        cases = [
            ([], ("path2", "path3"), 0),
            ([], ("path2", "path3"), 1),
            ([{"index": 0, "name": "overview", "panes": ["%1", "%2"]}], (), 0),
            ([{"index": 1, "name": "overview", "panes": ["%1", "%2"]}], (), 1),
            ([{"index": 1, "name": "overview", "panes": ["%1"]}], ("path3",), 1),
            ([{"index": 0, "name": "path2", "panes": ["%1"]}], ("path3",), 0),
            ([{"index": 1, "name": "path2", "panes": ["%1"]},
              {"index": 2, "name": "path3", "panes": ["%2"]}], (), 1),
        ]
        for windows, new_viewers, base in cases:
            with self.subTest(windows=windows, base=base):
                result = self._run_mock_launcher(windows, base=base, repeat=2)
                self.assertEqual(result["rc"], 0, result["stderr"])
                self.assertEqual(result["viewers"], new_viewers)
                self.assertEqual(
                    [(w["index"], w["name"], len(w["panes"]))
                     for w in result["windows"]],
                    [(1, "path2", 1), (2, "path3", 1)])
                if windows and windows[0]["name"] == "overview":
                    self.assertIn("%1", result["windows"][0]["panes"])
                    if len(windows[0]["panes"]) == 2:
                        self.assertIn("%2", result["windows"][1]["panes"])
                self.assertFalse(any(
                    "split-window" in cmd or "kill-" in cmd
                    for cmd in result["commands"]))

    def test_launcher_retains_window_on_immediate_viewer_exit(self):
        """An sg/view failure must remain visible, never race the tmux layout check."""
        cases = [([], "path2", ("path2", "path3")),
                 ([], "path3", ("path2", "path3")),
                 ([{"index": 1, "name": "path2", "panes": ["%1"]}],
                  "path3", ("path3",))]
        for windows, failing, new_viewers in cases:
            with self.subTest(windows=windows, failing=failing):
                result = self._run_mock_launcher(windows, fail_viewer=failing)
                self.assertEqual(result["rc"], 0, result["stderr"])
                self.assertEqual(result["viewers"], new_viewers)
                self.assertIn(
                    f"MONITOR_VIEWER_EXIT path={failing} exit=7",
                    result["stderr"])
                self.assertEqual(
                    [(w["index"], w["name"]) for w in result["windows"]],
                    [(1, "path2"), (2, "path3")])
                self.assertFalse(any(
                    "kill-" in cmd for cmd in result["commands"]))

    def test_two_window_launcher_fails_closed(self):
        cases = [
            ([], False, True),
            ([], True, False),
            ([{"index": 1, "name": "stranger", "panes": ["%1"]}], True, True),
            ([{"index": 1, "name": "overview",
               "panes": ["%1", "%2", "%3"]}], True, True),
        ]
        for windows, exists, member in cases:
            with self.subTest(windows=windows, exists=exists, member=member):
                result = self._run_mock_launcher(
                    windows, group_exists=exists, member=member)
                self.assertNotEqual(result["rc"], 0)
                self.assertFalse(result["viewers"])
                self.assertFalse(any(
                    cmd.startswith(("new-session", "new-window", "break-pane"))
                    for cmd in result["commands"]))

    def _run_mock_launcher(self, windows, *, base=1, repeat=1,
                           group_exists=True, member=True, fail_viewer=""):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            state_file, call_file, sg_file = (
                root / "state.json", root / "commands.log", root / "sg.log")
            state_file.write_text(json.dumps({"windows": windows, "base": base}))
            call_file.touch()
            sg_file.touch()

            def write_stub(name, code, python=False):
                f = bin_dir / name
                f.write_text(("#!/usr/bin/env python3\n" if python
                              else "#!/usr/bin/env bash\n") + code)
                f.chmod(0o755)

            write_stub("id", r'''
if [[ "$1" == "-un" ]]; then echo operator
elif [[ "$1" == "-nG" ]]; then
  if [[ "$TEST_MEMBER" == 1 ]]; then echo "operator plasma-monitor"
  else echo operator; fi
else exit 2; fi
''')
            write_stub("getent", r'''
if [[ "$TEST_GROUP" == 1 && "$1" == group &&
      "$2" == plasma-monitor ]]; then echo "plasma-monitor:x:998:operator"
else exit 2; fi
''')
            write_stub("sg", r'''
echo "$1 $2 $3" >> "$TEST_SG_LOG"
[[ "$1" == plasma-monitor && "$2" == -c &&
   "$3" == *"exec python3 -u"* ]] || exit 2
if [[ -n "$TEST_FAIL_VIEWER" &&
      "$3" == *"view $TEST_FAIL_VIEWER"* ]]; then
  echo "MOCK_SG_FAILURE" >&2
  exit 7
fi
''')
            write_stub("tmux", r'''
import json, os, subprocess, sys
args = sys.argv[1:]
p = os.environ["TEST_TMUX_STATE"]
with open(p) as f: state = json.load(f)
wins = state["windows"]
with open(os.environ["TEST_TMUX_LOG"], "a") as f:
    f.write(" ".join(args) + "\n")
def get(target):
    target = target.split(":")[-1]
    return next((w for w in wins if w["name"] == target or
                 str(w["index"]) == target), None)
def require(condition):
    if not condition: sys.exit(2)
op = args[0]
if op == "has-session":
    target = args[args.index("-t")+1]
    sys.exit(0 if wins else 1)
if op == "list-windows":
    for w in sorted(wins, key=lambda w:w["index"]): print(w["name"])
elif op == "list-panes":
    w = get(args[args.index("-t")+1])
    require(w is not None)
    for pane in w["panes"]: print(pane)
elif op == "display-message":
    w = get(args[args.index("-t")+1])
    require(w is not None)
    print(w["index"])
elif op == "new-session":
    require(not wins)
    wins.append({"index": state["base"],
                 "name": args[args.index("-n")+1], "panes":["%101"]})
elif op == "rename-window":
    w = get(args[args.index("-t")+1]); require(w is not None)
    w["name"] = args[-1]
elif op == "move-window":
    w = get(args[args.index("-s")+1])
    idx = int(args[args.index("-t")+1].split(":")[-1])
    require(w is not None and all(x["index"] != idx for x in wins))
    w["index"] = idx
elif op == "break-pane":
    pane = args[args.index("-s")+1]
    idx = int(args[args.index("-t")+1].split(":")[-1])
    origins = [w for w in wins if pane in w["panes"]]
    require(len(origins)==1 and all(w["index"] != idx for w in wins))
    origins[0]["panes"].remove(pane)
    wins.append({"index":idx,"name":args[args.index("-n")+1],
                 "panes":[pane]})
elif op == "new-window":
    idx = int(args[args.index("-t")+1].split(":")[-1])
    require(all(w["index"] != idx for w in wins))
    wins.append({"index":idx,"name":args[args.index("-n")+1],
                 "panes":["%102"]})
elif op == "send-keys":
    w = get(args[args.index("-t")+1])
    require(w is not None)
    if "-l" in args:
        require(args[-1].startswith("sg plasma-monitor -c "))
        require("MONITOR_VIEWER_EXIT" in args[-1])
        w["pending"] = args[-1]
    else:
        require(args[-1] == "Enter" and "pending" in w)
        # Only newly-created windows receive keys; emulate sg/exit without
        # using or stopping an existing tmux pane.
        subprocess.run(["bash", "-c", w.pop("pending")], check=True,
                       stdin=subprocess.DEVNULL, timeout=5)
elif op in ("select-window", "attach-session"):
    pass
else:
    sys.exit(2)
with open(p, "w") as f: json.dump(state, f)
if op in ("new-session", "new-window"):
    require(args[-2:] == ["bash", "-i"])
''', python=True)
            env = dict(os.environ)
            env.update({
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
                "TEST_TMUX_STATE": str(state_file),
                "TEST_TMUX_LOG": str(call_file),
                "TEST_SG_LOG": str(sg_file),
                "TEST_MEMBER": "1" if member else "0",
                "TEST_GROUP": "1" if group_exists else "0",
                "TEST_FAIL_VIEWER": fail_viewer,
            })
            proc = None
            for _ in range(repeat):
                proc = subprocess.run(
                    ["bash", str(ROOT / "scripts/plasma-engineering-monitor.sh")],
                    env=env, capture_output=True, text=True, timeout=15)
                if proc.returncode: break
            return {
                "rc": proc.returncode, "stderr": proc.stderr,
                "windows": sorted(json.loads(state_file.read_text())["windows"],
                                  key=lambda w:w["index"]),
                "commands": call_file.read_text().splitlines(),
                "viewers": tuple(
                    "path2" if "view path2" in x else "path3"
                    for x in sg_file.read_text().splitlines()),
            }

    @unittest.skipUnless(shutil.which("tmux"), "tmux executable not installed")
    def test_real_tmux_private_socket_retains_direct_argv_failure_window(self):
        """Use only an isolated socket: never touch any default tmux server."""
        with tempfile.TemporaryDirectory(prefix="plasma-tmux-argv-") as td:
            socket = str(Path(td) / "private.sock")

            def tmux(*args, check=True):
                return subprocess.run(
                    ["tmux", "-S", socket, *args],
                    text=True, capture_output=True, timeout=6,
                    check=check)

            started = False
            try:
                tmux("new-session", "-d", "-s", "test-monitor",
                     "-x", "80", "-y", "24", "-n", "path2",
                     "sleep", "12")
                started = True
                tmux("new-window", "-d", "-t", "test-monitor:2",
                     "-n", "path3", "bash", "-c",
                     'printf "MONITOR_VIEWER_EXIT path=path3 exit=7\n"; '
                     "exec bash -i")
                seen = ""
                for _ in range(30):
                    pane = tmux("capture-pane", "-p",
                                "-t", "test-monitor:2", check=False)
                    if pane.returncode == 0:
                        seen = pane.stdout
                    if "MONITOR_VIEWER_EXIT path=path3 exit=7" in seen:
                        break
                    time.sleep(0.1)
                self.assertIn("MONITOR_VIEWER_EXIT path=path3 exit=7", seen)
                result = tmux("list-windows", "-t", "test-monitor",
                              "-F", "#{window_index}:#{window_name}")
                self.assertIn("2:path3", result.stdout)
                # Private tmux inherits its own base-index (0 or 1).
                self.assertRegex(result.stdout, r"(?m)^[01]:path2$")
            finally:
                if started:
                    tmux("kill-server", check=False)

    @unittest.skipUnless(shutil.which("tmux"), "tmux executable not installed")
    def test_real_tmux_launcher_only_adds_missing_path3_on_private_socket(self):
        """Exercise the actual launcher; PATH 2 is preserved; PATH 3 fails visibly."""
        with tempfile.TemporaryDirectory(prefix="plasma-tmux-launcher-") as td:
            d = Path(td)
            sock = str(d / "private.sock")
            tmux_binary = shutil.which("tmux")
            bin_dir = d / "bin"
            bin_dir.mkdir()
            # Every tmux command made by the real launcher is redirected
            # into this private socket; interception of attach is deliberate.
            wrapper = bin_dir / "tmux"
            wrapper.write_text(
                '#!/bin/bash\n'
                'printf "%s\\n" "$*" >> "$TEST_TMUX_CALL_LOG"\n'
                'if [[ "$1" == attach-session ]]; then exit 0; fi\n'
                'exec "$TEST_REAL_TMUX" -S "$TEST_SOCKET" '
                '-f /dev/null "$@"\n')
            wrapper.chmod(0o755)
            for name, body in (
                ("id", '[[ "$1" == "-un" ]] && { echo operator; exit; }\n'
                 '[[ "$1" == "-nG" ]] && { echo "operator plasma-monitor"; exit; }\n'
                 'exit 2\n'),
                ("getent", '[[ "$1" == group && "$2" == plasma-monitor ]]\n'),
                ("sg", 'echo "STUB_PATH3_SG_FAILURE" >&2\nexit 7\n'),
            ):
                stub = bin_dir / name
                stub.write_text("#!/bin/bash\n" + body)
                stub.chmod(0o755)
            env = dict(os.environ, TEST_REAL_TMUX=tmux_binary,
                       TEST_SOCKET=sock,
                       TEST_TMUX_CALL_LOG=str(d / "calls.log"))
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

            def tmux(*args, check=True):
                return subprocess.run(
                    [tmux_binary, "-S", sock, "-f", "/dev/null", *args],
                    capture_output=True, text=True, timeout=8, check=check)

            started = False
            try:
                tmux("new-session", "-d", "-s", "plasma-monitor",
                     "-x", "80", "-y", "24", "-n", "path2",
                     "sleep", "30")
                started = True
                # Capture dead panes during diagnosis; assert they are alive
                # rather than accepting a retained-but-terminated window.
                tmux("set-option", "-g", "remain-on-exit", "on")
                # Existing private server was created before the launcher;
                # explicitly supply the fake sg PATH to only this socket.
                tmux("set-environment", "-g", "PATH", env["PATH"])
                tmux("move-window", "-d",
                     "-s", "plasma-monitor:0", "-t", "plasma-monitor:1")
                original = tmux(
                    "display-message", "-p", "-t", "plasma-monitor:1",
                    "#{pane_id}").stdout.strip()
                launch = subprocess.run(
                    ["bash", str(ROOT / "scripts/plasma-engineering-monitor.sh")],
                    env=env, capture_output=True, text=True, timeout=12)
                windows_snapshot = tmux(
                    "list-windows", "-t", "plasma-monitor",
                    "-F", "#{window_index}:#{window_name}", check=False)
                diagnostic = tmux(
                    "capture-pane", "-p", "-S", "-50",
                    "-t", "plasma-monitor:2", check=False)
                self.assertEqual(
                    launch.returncode, 0,
                    "Launcher stderr=" + launch.stderr +
                    " calls=" + (d / "calls.log").read_text() +
                    " windows=" + windows_snapshot.stdout +
                    " pane=" + diagnostic.stdout + diagnostic.stderr)
                last = ""
                for _ in range(30):
                    cap = tmux("capture-pane", "-p",
                               "-t", "plasma-monitor:2", check=False)
                    if cap.returncode == 0:
                        last = cap.stdout
                    if "MONITOR_VIEWER_EXIT path=path3 exit=7" in last:
                        break
                    time.sleep(0.1)
                self.assertIn("STUB_PATH3_SG_FAILURE", last)
                self.assertIn("MONITOR_VIEWER_EXIT path=path3 exit=7", last)
                self.assertEqual(tmux(
                    "display-message", "-p", "-t", "plasma-monitor:2",
                    "#{pane_dead}").stdout.strip(), "0",
                    "Diagnostic shell exited after viewer failure")
                self.assertEqual(tmux(
                    "display-message", "-p", "-t", "plasma-monitor:1",
                    "#{pane_id}").stdout.strip(), original)
                windows = tmux("list-windows", "-t", "plasma-monitor",
                               "-F", "#{window_index}:#{window_name}").stdout
                self.assertIn("1:path2", windows)
                self.assertIn("2:path3", windows)
            finally:
                if started:
                    tmux("kill-server", check=False)

    def test_one_shared_workflow_and_two_paths(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("plasma_engineering_monitor.py run path2 --", workflow)
        self.assertIn("plasma_engineering_monitor.py run path3 --", workflow)
        self.assertEqual(workflow.count("runs-on: [self-hosted, linux, x64, plasma-codex]"), 3)
        shell = ROOT / "scripts/plasma-engineering-monitor.sh"
        self.assertEqual(subprocess.run(["bash", "-n", str(shell)],
                                        check=False).returncode, 0)
        script = shell.read_text()
        self.assertIn("plasma-monitor", script)
        self.assertIn("tmux break-pane -d", script)
        self.assertIn('tmux new-window -d -t "$session:2"', script)
        self.assertIn("tmux move-window -d", script)
        self.assertIn('tmux select-window -t "$session:1"', script)
        self.assertEqual(workflow.count(
            "PLASMA_MONITOR_TASK: ${{ needs.development-authorize.outputs.task_id }}"), 3)
        self.assertEqual(workflow.count(
            "PLASMA_MONITOR_SUMMARY: ${{ needs.development-authorize.outputs.monitor_summary }}"), 3)
        self.assertEqual(workflow.count(
            "PLASMA_MONITOR_STAGE: ${{ needs.development-authorize.outputs.monitor_stage }}"), 1)
        self.assertIn(
            'monitor_summary: ${{ steps.approve.outputs.monitor_summary }}',
            workflow)
        self.assertNotIn("tmux split-window", script)
        self.assertNotIn("tmux kill-server", script)
        self.assertIn("MONITOR_VIEWER_EXIT", script)
        self.assertIn('tmux new-session -d -s "$session" -n path2 -c "$repo" bash -i', script)
        self.assertIn('tmux new-window -d -t "$session:2" -n path3 -c "$repo" bash -i', script)
        self.assertIn('tmux send-keys -l -t "$session:path3" "$right"', script)
        self.assertIn('tmux send-keys -t "$session:path3" Enter', script)
        self.assertNotIn("printf 'bash -c %q'", script)
        self.assertNotIn("tmux send-keys -t \"$session:1\"", script)



if __name__ == "__main__":
    unittest.main()

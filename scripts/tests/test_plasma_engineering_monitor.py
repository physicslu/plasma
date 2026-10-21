#!/usr/bin/env python3
"""Host-only tests for the non-authorizing Path 2/3 SSH tmux monitor."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_engineering_monitor as mon
import plasma_development_dispatch as dev

WORKFLOW = ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml"


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

    def test_real_codex_stream_preserves_evidence_and_live_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            live = directory / "path3.log"
            evidence = directory / "codex.log"
            live.touch()
            command = [sys.executable, "-c",
                       "import sys; sys.stdin.read(); "
                       "print('stdout marker',flush=True); "
                       "print('stderr marker',file=sys.stderr,flush=True)"]
            rc = dev._run_codex_with_live_log(
                command, b"tiny authorized test\n", directory,
                evidence, str(live))
            self.assertEqual(rc, 0)
            self.assertIn(b"stdout marker", live.read_bytes())
            self.assertIn(b"stderr marker", live.read_bytes())
            self.assertIn(b"stdout marker", evidence.read_bytes())
            self.assertIn(b"stderr marker", evidence.read_bytes())

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
                              sleep=fake_sleep)
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
                              sleep=fake_sleep)
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
            self.assertTrue(all(mon._clip_columns(line, 38) == line
                                for line in lines))
            self.assertIn("STATUS: IDLE", frame)
            self.assertIn("RECENT OUTPUT", frame)
            self.assertIn("line-059:", frame)
            self.assertNotIn("line-001:", frame)

    def test_one_shared_workflow_and_two_paths(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("plasma_engineering_monitor.py run path2 --", workflow)
        self.assertIn("plasma_engineering_monitor.py run path3 --", workflow)
        self.assertEqual(workflow.count("runs-on: [self-hosted, linux, x64, plasma-codex]"), 2)
        shell = ROOT / "scripts/plasma-engineering-monitor.sh"
        self.assertEqual(subprocess.run(["bash", "-n", str(shell)],
                                        check=False).returncode, 0)
        self.assertIn("split-window -d -h", shell.read_text())
        self.assertIn("plasma-monitor", shell.read_text())
        # Regression: operator tmux base-index may be 1 (SWPC uses :1),
        # so addressing :0 silently leaves a single Path 2 pane.
        script = shell.read_text()
        self.assertIn('window="$session:overview"', script)
        self.assertIn('tmux list-panes -t "$window"', script)
        self.assertIn('tmux split-window -d -h -t "$window"', script)
        self.assertNotIn('"=$session:0"', script)
        self.assertIn('if [ "$panes" -eq 1 ]; then', script)
        self.assertIn('elif [ "$panes" -ne 2 ]; then', script)


if __name__ == "__main__":
    unittest.main()

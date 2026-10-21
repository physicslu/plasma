#!/usr/bin/env python3
"""Host-only tests for the non-authorizing Path 2/3 SSH tmux monitor."""
from __future__ import annotations

import datetime as dt
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
            original = "old Codex message\\n"
            log.write_text(original)
            output = io.StringIO()
            keys = iter([None, "C", None])
            polls = [0]

            def fake_sleep(_seconds):
                polls[0] += 1
                if polls[0] == 2:
                    with log.open("a") as f:
                        f.write("new Codex message\\n")
                if polls[0] >= 3:
                    raise StopIteration

            with self.assertRaises(StopIteration):
                mon.view_loop(
                    "path3", directory=directory, output=output,
                    get_size=lambda: os.terminal_size((80, 24)),
                    sleep=fake_sleep, get_now=lambda: FIXED_NOW,
                    get_key=lambda: next(keys))
            frames = output.getvalue().split("\\x1b[H")[1:]
            self.assertEqual(len(frames), 3)
            self.assertIn("old Codex message", frames[0])
            self.assertNotIn("old Codex message", frames[1])
            self.assertNotIn("old Codex message", frames[2])
            self.assertIn("new Codex message", frames[2])
            self.assertEqual(log.read_text(),
                             original + "new Codex message\\n")
            self.assertFalse((directory / "path3.json").exists())
            self.assertNotIn("\\x1b[2J", output.getvalue())

    def test_clear_does_not_hide_next_jobs_first_message(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            log = directory / "path2.log"
            state = directory / "path2.json"
            state.write_text(json.dumps({
                "status": "IDLE", "run_id": "100", "started": "before"}))
            log.write_text("old first line\\n")
            clear_from = mon._clear_point(directory, "path2")
            self.assertNotIn("old first line", mon.render_snapshot(
                directory, "path2", clear_from=clear_from))
            # The same log inode is truncated when run_job starts anew.
            log.write_text("new job first line\\n")
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
            self.assertTrue(all(mon._clip_columns(line, 38) == line
                                for line in lines))
            self.assertIn("STATUS: IDLE", frame)
            self.assertIn("RECENT OUTPUT", frame)
            self.assertIn("line-059:", frame)
            self.assertNotIn("line-001:", frame)

    def test_path3_clock_is_pinned_to_minute_and_has_timezone(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            before = mon.render_snapshot(directory, "path3", now=FIXED_NOW)
            same_minute = mon.render_snapshot(
                directory, "path3", now=FIXED_NOW.replace(second=59))
            next_minute = mon.render_snapshot(
                directory, "path3", now=FIXED_NOW + dt.timedelta(minutes=1))
            self.assertEqual(before, same_minute)
            self.assertNotEqual(before, next_minute)
            self.assertIn("NOW: 2026-10-21T16:10+08:00", before)
            self.assertIn("NOW: 2026-10-21T16:11+08:00", next_minute)
            self.assertNotIn("NOW:", mon.render_snapshot(
                directory, "path2", now=FIXED_NOW))

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
            self.assertIn("NOW: 2026-10-21T16:10+08:00", output.getvalue())
            self.assertIn("NOW: 2026-10-21T16:11+08:00", output.getvalue())

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
                           group_exists=True, member=True):
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
elif op in ("select-window", "attach-session"):
    pass
else:
    sys.exit(2)
with open(p, "w") as f: json.dump(state, f)
if op in ("new-session", "new-window"):
    subprocess.run(["bash", "-c", args[-1]], check=True)
''', python=True)
            env = dict(os.environ)
            env.update({
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
                "TEST_TMUX_STATE": str(state_file),
                "TEST_TMUX_LOG": str(call_file),
                "TEST_SG_LOG": str(sg_file),
                "TEST_MEMBER": "1" if member else "0",
                "TEST_GROUP": "1" if group_exists else "0",
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

    def test_one_shared_workflow_and_two_paths(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("plasma_engineering_monitor.py run path2 --", workflow)
        self.assertIn("plasma_engineering_monitor.py run path3 --", workflow)
        self.assertEqual(workflow.count("runs-on: [self-hosted, linux, x64, plasma-codex]"), 2)
        shell = ROOT / "scripts/plasma-engineering-monitor.sh"
        self.assertEqual(subprocess.run(["bash", "-n", str(shell)],
                                        check=False).returncode, 0)
        script = shell.read_text()
        self.assertIn("plasma-monitor", script)
        self.assertIn("tmux break-pane -d", script)
        self.assertIn('tmux new-window -d -t "$session:2"', script)
        self.assertIn("tmux move-window -d", script)
        self.assertIn('tmux select-window -t "$session:1"', script)
        self.assertNotIn("tmux split-window", script)
        self.assertNotIn("tmux kill-server", script)



if __name__ == "__main__":
    unittest.main()

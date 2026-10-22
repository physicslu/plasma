#!/usr/bin/env python3
"""Offline, synthetic-only tests. No real Codex session files are opened."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_codex_benchmark_usage as usage

START = "2026-10-22T11:17:20Z"
END = "2026-10-22T11:18:59.994904Z"
ID = "c91fc279-388d-4fda-b81c-2a05978d908b"


def row(time, kind, **extra):
    return {"timestamp": time, "type": "event_msg", "payload": {"type": kind, **extra}}


def count(time, a, b, c):
    d = {"input_tokens": a, "cached_input_tokens": b, "output_tokens": c}
    return row(time, "token_count", info={"total_token_usage": d,
                                          "last_token_usage": d})


class TestDesktopUsage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rollout = Path(self.temp.name) / f"rollout-2026-10-22T11-00-00-{ID}.jsonl"

    def write(self, events):
        self.rollout.write_text("\n".join(json.dumps(event) for event in events) + "\n")
        return self.rollout

    def base(self):
        return [
            count("2026-10-22T11:16:00Z", 1000, 800, 100),
            row("2026-10-22T11:17:21Z", "task_started", turn_id="turn-123"),
            {"timestamp": "2026-10-22T11:17:21Z", "type": "turn_context",
             "payload": {"model": "gpt-6", "reasoning_effort": "high"}},
            count("2026-10-22T11:17:45Z", 1100, 875, 114),
            count("2026-10-22T11:17:46Z", 1100, 875, 114),
            count("2026-10-22T11:18:58Z", 1250, 950, 145),
            row("2026-10-22T11:18:59Z", "task_complete", turn_id="turn-123",
                last_agent_message="PRIVATE PROMPT NEVER PRINTED"),
        ]

    def run_extract(self, events):
        return usage.extract(self.write(events), usage.clock(START), usage.clock(END))

    def test_cumulative_delta_deduplicates_repeated_snapshot_and_outputs_no_text(self):
        result = self.run_extract(self.base() + [row("2026-10-22T11:18:59.2Z",
                                                     "agent_message", message="SECRET")])
        self.assertEqual(result["status"], "REPORTED")
        self.assertEqual([result[k] for k in usage.FIELDS], [250, 150, 45])
        self.assertEqual(result["session_id"], ID)
        self.assertEqual(result["turn_id"], "turn-123")
        self.assertEqual(result["model"], "gpt-6")
        self.assertEqual(result["reasoning_effort"], "high")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("PRIVATE PROMPT", json.dumps(result))

    def test_request_records_prefer_over_cumulative_and_dedup(self):
        events = self.base()
        rec = {"timestamp": "2026-10-22T11:18:30Z",
               "type": "token_usage_record", "payload": {
                   "response_id": "resp-abc", "usage": {"input_tokens": 88,
                   "cached_input_tokens": 44, "output_tokens": 12}}}
        events.insert(5, rec)
        events.insert(6, dict(rec))
        r = self.run_extract(events)
        self.assertEqual(r["accounting"], "deduplicated_response_records")
        self.assertEqual([r[k] for k in usage.FIELDS], [88, 44, 12])

    def test_request_records_no_legacy_baseline_needed(self):
        events = self.base()[1:]
        events.insert(3, {"timestamp": "2026-10-22T11:18:30Z",
                          "type": "token_usage_record", "payload": {
                              "response_id": "resp-def", "usage": {
                                  "input_tokens": 9, "cached_input_tokens": 8,
                                  "output_tokens": 1}}})
        r = self.run_extract(events)
        self.assertEqual([r[k] for k in usage.FIELDS], [9, 8, 1])

    def test_request_conflict_refused(self):
        events = self.base()
        events.insert(4, {"timestamp": "2026-10-22T11:17:50Z",
                          "type": "token_usage_record", "payload": {
                              "response_id": "resp-abc", "usage": {
                                  "input_tokens": 88, "cached_input_tokens": 44,
                                  "output_tokens": 12}}})
        events.insert(5, {"timestamp": "2026-10-22T11:17:51Z",
                          "type": "token_usage_record", "payload": {
                              "response_id": "resp-abc", "usage": {
                                  "input_tokens": 89, "cached_input_tokens": 44,
                                  "output_tokens": 12}}})
        self.assertEqual(self.run_extract(events)["reason"], "REQUEST_RECORD_CONFLICT")

    def test_no_baseline_fails_closed(self):
        r = self.run_extract(self.base()[1:])
        self.assertEqual((r["status"], r["reason"]),
                         ("NOT_AVAILABLE", "PRE_TURN_CUMULATIVE_BASELINE_MISSING"))
        self.assertIsNone(r["input_tokens"])

    def test_no_token_events(self):
        r = self.run_extract([self.base()[0], self.base()[1], self.base()[-1]])
        self.assertEqual(r["reason"], "TURN_USAGE_SNAPSHOT_MISSING")

    def test_cumulative_reset_refused(self):
        events = self.base()
        events[5] = count("2026-10-22T11:18:58Z", 11, 9, 4)
        r = self.run_extract(events)
        self.assertEqual(r["reason"], "COUNTER_RESET_OR_INCONSISTENCY")

    def test_ambiguous_turns(self):
        events = self.base()
        events.insert(3, row("2026-10-22T11:17:30Z", "task_started", turn_id="turn-456"))
        r = self.run_extract(events)
        self.assertEqual(r["reason"], "TURN_BOUNDARY_AMBIGUOUS")

    def test_missing_completion_and_aborted(self):
        events = self.base()
        self.assertEqual(self.run_extract(events[:-1])["reason"], "TURN_COMPLETION_NOT_FOUND")
        events[-1] = row("2026-10-22T11:18:59Z", "turn_aborted", turn_id="turn-123")
        self.assertEqual(self.run_extract(events)["status"], "NOT_AVAILABLE")

    def test_missing_effort_is_null_not_default(self):
        events = self.base()
        events[2]["payload"].pop("reasoning_effort")
        self.assertIsNone(self.run_extract(events)["reasoning_effort"])

    def test_nonnegative_and_cache_bounds(self):
        self.assertIsNone(usage.counters({"input_tokens": 1, "cached_input_tokens": 2,
                                          "output_tokens": 0}))
        self.assertIsNone(usage.counters({"input_tokens": True, "cached_input_tokens": 0,
                                          "output_tokens": 0}))
        self.assertIsNone(usage.delta({"input_tokens": 5, "cached_input_tokens": 1,
                                       "output_tokens": 0},
                                      {"input_tokens": 10, "cached_input_tokens": 1,
                                       "output_tokens": 0}))

    def test_compare_keeps_scope_difference_explicit(self):
        desktop = self.run_extract(self.base())
        receipt = {"github_run_id": "39768663770", "codex_usage": {
            "status": "reported", "input_tokens": 251614,
            "cached_input_tokens": 192896, "output_tokens": 2664}}
        comparison = usage.compare(desktop, receipt)
        self.assertFalse(comparison["like_for_like"])
        self.assertEqual(comparison["path3"]["input_tokens"], 251614)
        self.assertEqual(comparison["raw_token_difference_desktop_minus_path3"]["input_tokens"], 250 - 251614)

    def test_cli_json_output_is_allowlisted(self):
        self.write(self.base())
        run = subprocess.run([sys.executable, str(ROOT / "scripts/plasma_codex_benchmark_usage.py"),
                              "--session", str(self.rollout), "--start", START, "--end", END],
                             check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(run.stdout)["input_tokens"], 250)
        self.assertNotIn("PRIVATE PROMPT", run.stdout)

    def test_explicit_timezone(self):
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            usage.clock("2026-10-22T11:17:20")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Host-only synthetic negative tests; no Codex, GitHub write, SWPC or hardware."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parents[1] / "plasma-codex-pilot-acceptance.py"
spec = importlib.util.spec_from_file_location("plasma_pilot_acceptance", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

A = "Verified exact owner comment authorization in this source fixture with isolated runtime."
B = "The named source component demonstrates the guard and evidence handling contract."
C = "The tmux component launches a bounded process and waits for its completion receipt."
D = "The other program provides a separate control on session cleanup and process status."
E = "The evidence producer verifies SHA256 checksums before reporting successful completion."
F = "The workflow uploads a restricted receipt but does not claim hardware was tested."
WORDS = "This analysis cites both fixed source excerpts and explains their concrete relationship. "

QUOTES = {
    mod.FILES[0]: A,
    mod.FILES[1]: F,
    mod.FILES[2]: C + "\n" + E,
    mod.FILES[3]: D,
    mod.FILES[4]: B,
    mod.FILES[5]: A,
}


class PilotAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        self.root.mkdir()
        self.out = base / "out"
        self.out.mkdir()
        for path, content in QUOTES.items():
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        mod.prepare(self.root, self.out)
        self.response = {
            "status": "completed",
            "summary": WORDS * 2,
            "findings": [
                {
                    "topic": topic,
                    "file": sorted(paths)[0],
                    "quote": QUOTES[sorted(paths)[0]].split("\n")[0],
                    "related_file": sorted(paths)[1],
                    "related_quote": QUOTES[sorted(paths)[1]].split("\n")[0],
                    "analysis": WORDS * 2,
                } for topic, paths in mod.TOPICS.items()
            ],
        }
        self.save_response()
        self.save_trace()

    def save_response(self, payload=None):
        (self.out / "last-message.txt").write_text(
            json.dumps(self.response if payload is None else payload), encoding="utf-8"
        )

    def save_trace(self, tool=False, completed=True):
        events = [
            {"type": "thread.started", "thread_id": "fake"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "simulated"}},
        ]
        if tool:
            events.append({"type": "item.started", "item": {"type": "command_execution", "command": "pwd"}})
        if completed:
            events.append({"type": "turn.completed", "usage": {}})
        (self.out / "codex.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )

    def assert_denied(self, code):
        with self.assertRaises(mod.Rejected) as err:
            mod.verify(self.root, self.out, 0)
        self.assertEqual(str(err.exception), code)

    def test_grounded_guard_tmux_evidence_success(self):
        report = mod.verify(self.root, self.out, 0)
        self.assertEqual(report["source_file_count"], 6)
        self.assertEqual(report["topics"], ["evidence", "guard", "tmux"])
        self.assertFalse(report["hardware_verified"])
        self.assertFalse(report["os_file_isolation_verified"])
        self.assertTrue((self.out / "assessment.json").exists())

    def test_no_actual_source_read_cannot_pass(self):
        self.save_response({"status": "completed", "summary": WORDS * 2, "findings": []})
        self.assert_denied("FINDING_COUNT_DENIED")

    def test_model_refusal_cannot_pass(self):
        self.save_response({"status": "blocked", "summary": "Cannot read source files", "findings": []})
        self.assert_denied("RESPONSE_INCOMPLETE")

    def test_hallucinated_quote_denied(self):
        self.response["findings"][0]["quote"] = "This text does not exist anywhere in the checked-in source."
        self.save_response()
        self.assert_denied("SOURCE_QUOTE_UNGROUNDED")

    def test_wrong_source_pair_denied(self):
        self.response["findings"][0]["related_file"] = mod.FILES[0]
        self.save_response()
        self.assert_denied("TOPIC_SOURCE_PAIR_DENIED")

    def test_short_generic_analysis_denied(self):
        self.response["findings"][1]["analysis"] = "looks good"
        self.save_response()
        self.assert_denied("FINDING_ANALYSIS_TOO_SHORT")

    def test_duplicate_topic_denied(self):
        self.response["findings"][2]["topic"] = "guard"
        self.save_response()
        self.assert_denied("TOPIC_DENIED")

    def test_extra_response_field_denied(self):
        self.response["hardware_pass"] = True
        self.save_response()
        self.assert_denied("RESPONSE_SCHEMA_DENIED")

    def test_duplicate_json_keys_denied(self):
        (self.out / "last-message.txt").write_text('{"status":"completed","status":"completed"}')
        self.assert_denied("JSON_DUPLICATE_KEY")

    def test_tool_attempt_denied_even_if_output_grounded(self):
        self.save_trace(tool=True)
        self.assert_denied("CODEX_TOOL_OR_UNKNOWN_ITEM_DENIED")

    def test_missing_completed_event_denied(self):
        self.save_trace(completed=False)
        self.assert_denied("CODEX_TURN_NOT_COMPLETED")

    def test_nonzero_codex_exit_denied(self):
        with self.assertRaisesRegex(mod.Rejected, "CODEX_NONZERO_EXIT"):
            mod.verify(self.root, self.out, 1)

    def test_changed_source_denied(self):
        (self.root / mod.FILES[0]).write_text("changed after snapshot", encoding="utf-8")
        self.assert_denied("INPUT_SOURCE_CHANGED")

    def test_tampered_input_prompt_denied(self):
        (self.out / "prompt.txt").write_text("prompt tampered", encoding="utf-8")
        self.assert_denied("INPUT_SOURCE_CHANGED")

    def test_symlink_source_denied(self):
        p = self.root / mod.FILES[0]
        p.unlink()
        p.symlink_to(self.root / mod.FILES[1])
        with self.assertRaises(OSError):
            mod.source_snapshot(self.root)

    def test_missing_source_denied(self):
        (self.root / mod.FILES[0]).unlink()
        with self.assertRaises(FileNotFoundError):
            mod.source_snapshot(self.root)

    def test_not_really_executing_codex(self):
        self.assertFalse(hasattr(mod, "launch_codex"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

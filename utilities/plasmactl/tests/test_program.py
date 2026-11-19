"""Host-only `plasmactl program` tests against an in-process fake Manager.

The fake implements only the canonical Manager start/Batch/reconcile/void/stop
contract. No PPU, Z2, FPGA, SWD or DUT is involved; a PASS here is a CLI
contract PASS, never a physical programming PASS.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from plasma_cli import programming
from plasma_cli.main import main

STOP = "STOP_QUEUING"
VOID = "VOID_UNSTARTED_START"


class FakeManager:
    """Canonical Manager programming routes with injectable faults."""

    def __init__(self):
        self.starts: dict[str, str] = {}
        self.batches: dict[str, dict] = {}
        self.posts: list[tuple[str, dict]] = []
        self.outcomes: dict[tuple[str, int], str] = {}
        self.fault: str | None = None  # lose_after_admit | lose_before_admit | refuse | reconcile_down
        self.polls_until_finished = 1
        self.never_finish = False
        self.lock = threading.Lock()

    # -- model ---------------------------------------------------------------
    def admit(self, body: dict) -> dict:
        units = [{"ppu_alias": t["ppu_alias"], "site_id": s, "status": "RUNNING",
                  "outcome": None, "reason": None, "failure_domain": None, "attempts": [],
                  "progress": {"stage": "program", "progress_percent": 40.0}}
                 for t in body["targets"] for s in t["site_ids"]]
        batch = {"batch_id": secrets.token_hex(16), "start_id": body["start_id"],
                 "targets": body["targets"], "operations": body["operations"],
                 "state": "running", "execution_status": "RUNNING", "outcome": None,
                 "reason": None, "stop_requested": False, "journal_persisted": True,
                 "units": units, "polls": 0, "created_at": "2026-11-18T01:00:00+00:00",
                 "finished_at": None}
        self.starts[body["start_id"]] = "CONSUMED"
        self.batches[batch["batch_id"]] = batch
        return batch

    def advance(self, batch: dict) -> None:
        batch["polls"] += 1
        if self.never_finish or batch["polls"] <= self.polls_until_finished \
                or batch["state"] == "finished":
            return
        outcomes = []
        for unit in batch["units"]:
            outcome = self.outcomes.get((unit["ppu_alias"], unit["site_id"]), "PASS")
            executed = outcome != "BLOCKED"
            unit.update(outcome=outcome, status="FINISHED" if executed else "NOT_RUN",
                        attempts=[{"attempt": 1, "run_id": "r" * 32,
                                   "job_id": f"job-{unit['site_id']}", "outcome": outcome,
                                   "safe_off": True}] if executed else [], progress=None)
            outcomes.append(outcome)
        order = ["OUTCOME_UNKNOWN", "FAIL"]
        if any(o in order for o in outcomes):
            agg = next(o for o in order if o in outcomes)
        elif set(outcomes) == {"PASS"}:
            agg = "PASS"
        elif set(outcomes) == {"BLOCKED"}:
            agg = "BLOCKED"
        else:
            agg = "PARTIAL"
        batch.update(state="finished", execution_status="COMPLETED", outcome=agg,
                     finished_at="2026-11-18T01:00:12+00:00")

    @staticmethod
    def view(batch: dict) -> dict:
        return {k: v for k, v in batch.items() if k != "polls"}

    def reconcile(self, start_id: str) -> dict:
        batch = next((b for b in self.batches.values() if b["start_id"] == start_id), None)
        rec = {"start_id": start_id, "read_only": True, "batch": None, "reason": None}
        if batch is not None:
            rec.update(state="TERMINAL_CONFIRMED" if batch["outcome"] else "ACCEPTED_RUNNING",
                       batch=self.view(batch))
        elif self.starts.get(start_id) == "ISSUED":
            rec.update(state="ACCEPTANCE_PENDING", reason="START_STILL_ADMISSIBLE")
        elif self.starts.get(start_id) == "VOIDED":
            rec.update(state="NOT_ACCEPTED", reason="START_VOIDED_BEFORE_ADMISSION")
        else:
            rec.update(state="OUTCOME_UNKNOWN", reason="START_NOT_RECORDED")
        return rec

    def count(self, route: str) -> int:
        return sum(1 for path, _ in self.posts if path == route)

    def continue_site(self, batch: dict, body: dict) -> tuple[int, dict]:
        refuse = lambda code: (409, {"ok": False, "error": {"code": code, "message": code}})
        return refuse("programming_continue_stale")


def make_handler(manager: FakeManager):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status: int, payload: dict) -> None:
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def refuse(self, status: int, code: str) -> None:
            self.reply(status, {"ok": False, "error": {"code": code, "message": code}})

        def do_GET(self):  # noqa: N802
            with manager.lock:
                if m := re.fullmatch(r"/api/programming/batches/([0-9a-f]{32})", self.path):
                    batch = manager.batches.get(m.group(1))
                    if batch is None:
                        return self.refuse(404, "programming_batch_not_found")
                    manager.advance(batch)
                    return self.reply(200, {"ok": True, "batch": manager.view(batch)})
                if m := re.fullmatch(r"/api/programming/starts/([0-9a-f]{32})", self.path):
                    if manager.fault == "reconcile_down":
                        return self.reply(503, {"ok": False})
                    return self.reply(200, {"ok": True,
                                            "reconciliation": manager.reconcile(m.group(1))})
            self.refuse(404, "not_found")

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with manager.lock:
                manager.posts.append((self.path, body))
                if self.path == "/api/programming/starts":
                    assert body == {"kind": "batch"}
                    start = secrets.token_hex(16)
                    manager.starts[start] = "ISSUED"
                    return self.reply(200, {"ok": True, "start": {"start_id": start}})
                if self.path == "/api/programming/batches":
                    if manager.starts.get(body.get("start_id")) != "ISSUED":
                        return self.refuse(409, "programming_start_not_startable")
                    if manager.fault == "refuse":
                        return self.refuse(422, "programming_route_not_found")
                    if manager.fault == "lose_before_admit":
                        return self.reply(502, {"ok": False})
                    batch = manager.admit(body)
                    if manager.fault in ("lose_after_admit", "reconcile_down"):
                        return self.reply(500, {"ok": False})
                    return self.reply(202, {"ok": True, "batch": manager.view(batch)})
                if m := re.fullmatch(r"/api/programming/starts/([0-9a-f]{32})/void", self.path):
                    assert body == {"void": VOID}
                    if manager.starts.get(m.group(1)) != "ISSUED":
                        return self.refuse(409, "programming_start_not_voidable")
                    manager.starts[m.group(1)] = "VOIDED"
                    return self.reply(200, {"ok": True})
                if m := re.fullmatch(r"/api/programming/batches/([0-9a-f]{32})/continue", self.path):
                    status, payload = manager.continue_site(manager.batches[m.group(1)], body)
                    return self.reply(status, payload)
                if m := re.fullmatch(r"/api/programming/batches/([0-9a-f]{32})/stop", self.path):
                    assert body == {"stop": STOP}
                    batch = manager.batches[m.group(1)]
                    batch["stop_requested"] = True
                    return self.reply(200, {"ok": True, "batch": manager.view(batch)})
            self.refuse(404, "not_found")
    return Handler


@pytest.fixture
def manager():
    fake = FakeManager()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(fake))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield fake
    server.shutdown()
    server.server_close()


@pytest.fixture
def image(tmp_path) -> Path:
    path = tmp_path / "fw.bin"
    path.write_bytes(b"\x00\x20\x00\x20" * 64)
    return path


def submit(manager, tmp_path, image, *extra, targets=("z2:1,2", "ppu-b:3")):
    argv = ["program", "submit", "--manager-url", manager.url, "--icpn", "STM32F103C8T6",
            "--image", str(image), "--journal", str(tmp_path / "journal.json"), "--quiet"]
    for target in targets:
        argv += ["--target", target]
    return main([*argv, *extra])


def output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# --- P0: multi-PPU / multi-Site, one start, one Batch -------------------------

def test_multi_ppu_multi_site_pass_uses_one_start_and_one_batch(manager, tmp_path, image, capsys):
    assert submit(manager, tmp_path, image) == programming.EXIT_PASS
    result = output(capsys)
    assert manager.count("/api/programming/starts") == 1
    assert manager.count("/api/programming/batches") == 1
    _, body = manager.posts[1]
    assert body["targets"] == [{"ppu_alias": "z2", "site_ids": [1, 2]},
                               {"ppu_alias": "ppu-b", "site_ids": [3]}]
    assert body["operations"] == ["erase", "program", "verify"]
    assert body["start_id"] == result["start_id"]
    assert base64.b64decode(body["image_base64"]) == image.read_bytes()
    assert body["retry_limit"] == 0 and body["stop_policy"] == {"kind": "never"}
    assert result["batch"]["outcome"] == "PASS"
    assert [(s["ppu_alias"], s["site_id"]) for s in result["batch"]["sites"]] == [
        ("z2", 1), ("z2", 2), ("ppu-b", 3)]
    journal = json.loads((tmp_path / "journal.json").read_text())
    assert journal["submission"] == "ACCEPTED" and journal["batch_post_count"] == 1
    assert journal["source"]["sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
    assert "image_base64" not in json.dumps(journal)  # never the payload


@pytest.mark.parametrize(("outcomes", "expected", "code"), [
    ({("z2", 2): "FAIL"}, "FAIL", programming.EXIT_NOT_PASS),
    ({("ppu-b", 3): "BLOCKED"}, "PARTIAL", programming.EXIT_NOT_PASS),
    ({("z2", 1): "BLOCKED", ("z2", 2): "BLOCKED", ("ppu-b", 3): "BLOCKED"},
     "BLOCKED", programming.EXIT_NOT_PASS),
    ({("z2", 1): "OUTCOME_UNKNOWN"}, "OUTCOME_UNKNOWN", programming.EXIT_UNKNOWN),
])
def test_non_pass_outcomes_are_reported_and_never_resubmitted(
        manager, tmp_path, image, capsys, outcomes, expected, code):
    manager.outcomes = outcomes
    assert submit(manager, tmp_path, image) == code
    result = output(capsys)
    assert result["batch"]["outcome"] == expected
    # One Site's FAIL/UNKNOWN never makes the CLI stop, retry or resend anything.
    assert [path for path, _ in manager.posts] == [
        "/api/programming/starts", "/api/programming/batches"]
    # Peer Sites keep their own Manager result.
    peers = {(s["ppu_alias"], s["site_id"]): s["outcome"] for s in result["batch"]["sites"]}
    assert all(peers[key] == outcomes.get(key, "PASS") for key in peers)


def test_erase_only_range_and_failed_sites_policy(manager, tmp_path, capsys):
    code = main(["program", "submit", "--manager-url", manager.url, "--icpn", "STM32F103C8T6",
                 "--target", "z2:1", "--operations", "erase", "--address", "0x08000000",
                 "--length", "1024", "--stop-after-failed-sites", "1", "--retry-limit", "2",
                 "--journal", str(tmp_path / "j.json"), "--quiet"])
    assert code == 0
    _, body = manager.posts[1]
    assert body["address"] == 0x08000000 and body["length"] == 1024
    assert "image_base64" not in body and "bundle_base64" not in body
    assert body["stop_policy"] == {"kind": "failed_sites", "threshold": 1}
    assert body["retry_limit"] == 2


def test_bundle_source_is_sent_as_bundle(manager, tmp_path, capsys):
    bundle = tmp_path / "b.zip"
    bundle.write_bytes(b"PK\x03\x04bundle")
    code = main(["program", "submit", "--manager-url", manager.url, "--icpn", "STM32F103C8T6",
                 "--target", "z2:2", "--bundle", str(bundle), "--journal",
                 str(tmp_path / "j.json"), "--no-wait"])
    assert code == 0
    _, body = manager.posts[1]
    assert base64.b64decode(body["bundle_base64"]) == bundle.read_bytes()
    assert "image_filename" not in body
    assert output(capsys)["submission"] == "ACCEPTED"


# --- Start ID, reconciliation, no duplicate submission -----------------------

def test_lost_answer_after_admission_is_reconciled_not_resent(manager, tmp_path, image, capsys):
    manager.fault = "lose_after_admit"
    assert submit(manager, tmp_path, image) == programming.EXIT_PASS
    result = output(capsys)
    assert result["submission"] == "ACCEPTED" and result["batch"]["outcome"] == "PASS"
    assert manager.count("/api/programming/batches") == 1
    assert len(manager.batches) == 1


def test_lost_answer_before_admission_voids_start_and_reports_not_accepted(
        manager, tmp_path, image, capsys):
    manager.fault = "lose_before_admit"
    assert submit(manager, tmp_path, image) == programming.EXIT_NOT_ACCEPTED
    result = output(capsys)
    assert result["submission"] == "NOT_ACCEPTED"
    assert result["reason"] == "START_VOIDED_BEFORE_ADMISSION"
    assert manager.count("/api/programming/batches") == 1
    assert manager.batches == {}


def test_unreconcilable_answer_is_outcome_unknown_without_resend(manager, tmp_path, image, capsys):
    manager.fault = "reconcile_down"
    assert submit(manager, tmp_path, image) == programming.EXIT_UNKNOWN
    result = output(capsys)
    assert result["submission"] == "UNKNOWN" and result["batch_post_count"] == 1
    assert manager.count("/api/programming/batches") == 1


def test_definite_refusal_is_not_accepted(manager, tmp_path, image, capsys):
    manager.fault = "refuse"
    assert submit(manager, tmp_path, image) == programming.EXIT_NOT_ACCEPTED
    result = output(capsys)
    assert result["submission"] == "REFUSED" and "programming_route_not_found" in result["reason"]


def test_existing_journal_refuses_a_second_submission_before_io(manager, tmp_path, image, capsys):
    assert submit(manager, tmp_path, image) == 0
    capsys.readouterr()
    posts = list(manager.posts)
    assert submit(manager, tmp_path, image) == programming.EXIT_USAGE
    assert "reconcile" in json.loads(capsys.readouterr().err)["error"]
    assert manager.posts == posts


def test_reconcile_from_journal_is_read_only(manager, tmp_path, image, capsys):
    manager.fault = "reconcile_down"
    assert submit(manager, tmp_path, image) == programming.EXIT_UNKNOWN
    capsys.readouterr()
    manager.fault = None
    posts = list(manager.posts)
    code = main(["program", "reconcile", "--manager-url", manager.url,
                 "--journal", str(tmp_path / "journal.json")])
    result = output(capsys)
    assert manager.posts == posts  # no POST, no void, no resend
    assert result["read_only"] is True and result["auto_retry"] == "DISABLED"
    assert result["state"] in ("ACCEPTED_RUNNING", "TERMINAL_CONFIRMED")
    assert code in (programming.EXIT_PASS, programming.EXIT_IN_PROGRESS)
    journal = json.loads((tmp_path / "journal.json").read_text())
    assert journal["submission"] == "ACCEPTED" and journal["batch_id"] == result["batch"]["batch_id"]


def test_reconcile_unknown_start_is_outcome_unknown(manager, capsys):
    code = main(["program", "reconcile", "--manager-url", manager.url, "--start-id", "e" * 32])
    assert code == programming.EXIT_UNKNOWN
    assert output(capsys)["state"] == "OUTCOME_UNKNOWN"


# --- status / receipt / stop --------------------------------------------------

def test_wait_timeout_reports_in_progress_and_never_stops(manager, tmp_path, image, capsys):
    manager.never_finish = True
    assert submit(manager, tmp_path, image, "--wait-timeout", "0") == programming.EXIT_IN_PROGRESS
    result = output(capsys)
    assert result["batch"]["state"] == "running"
    assert manager.count("/api/programming/batches") == 1
    assert not any(path.endswith("/stop") for path, _ in manager.posts)
    code = main(["program", "status", "--manager-url", manager.url,
                 "--batch-id", result["batch_id"]])
    assert code == programming.EXIT_IN_PROGRESS
    assert output(capsys)["batch"]["sites"][0]["progress"]["stage"] == "program"


def test_receipt_and_status_after_completion(manager, tmp_path, image, capsys):
    manager.outcomes = {("ppu-b", 3): "FAIL"}
    assert submit(manager, tmp_path, image) == programming.EXIT_NOT_PASS
    batch_id = output(capsys)["batch_id"]
    assert main(["program", "receipt", "--manager-url", manager.url,
                 "--batch-id", batch_id, "--target", "z2:1,2"]) == programming.EXIT_NOT_PASS
    receipt = output(capsys)
    # A filtered projection can never hide the peer FAIL.
    assert receipt["manager_reported_pass"] is False
    assert main(["program", "status", "--manager-url", manager.url,
                 "--batch-id", batch_id]) == programming.EXIT_NOT_PASS


def test_stop_queuing_uses_existing_token_only(manager, tmp_path, image, capsys):
    manager.never_finish = True
    submit(manager, tmp_path, image, "--no-wait")
    batch_id = output(capsys)["batch_id"]
    assert main(["program", "stop", "--manager-url", manager.url, "--batch-id", batch_id]) == 0
    result = output(capsys)
    assert result["stop"] == "STOP_QUEUING_RECORDED" and result["batch"]["stop_requested"]
    assert manager.posts[-1] == (f"/api/programming/batches/{batch_id}/stop", {"stop": STOP})


# --- input validation fails closed before any I/O ----------------------------

@pytest.mark.parametrize("extra", [
    ["--operations", "verify,program"],
    ["--operations", "erase,erase"],
    ["--operations", "read"],
    ["--operations", "erase", "--address", "0"],          # missing length
    ["--target", "z2:1"],                                  # duplicate PPU entry
])
def test_invalid_requests_fail_before_any_manager_io(manager, tmp_path, image, capsys, extra):
    assert submit(manager, tmp_path, image, *extra) == programming.EXIT_USAGE
    assert manager.posts == []
    assert not (tmp_path / "journal.json").exists()


def test_program_without_source_or_with_symlink_source_fails_closed(manager, tmp_path, image):
    link = tmp_path / "link.bin"
    link.symlink_to(image)
    for source in ([], ["--image", str(link)]):
        code = main(["program", "submit", "--manager-url", manager.url, "--icpn", "X",
                     "--target", "z2:1", "--journal", str(tmp_path / "j.json"), *source])
        assert code == programming.EXIT_USAGE
    assert manager.posts == []


def test_unreachable_manager_never_reports_pass(tmp_path, image, capsys):
    code = main(["program", "submit", "--manager-url", "http://127.0.0.1:9", "--icpn", "X",
                 "--target", "z2:1", "--image", str(image),
                 "--journal", str(tmp_path / "j.json"), "--timeout", "1"])
    assert code == programming.EXIT_NOT_ACCEPTED
    assert output(capsys)["submission"] == "NOT_SUBMITTED"


def test_journal_in_missing_directory_fails_before_any_io(manager, tmp_path, image, capsys):
    code = main(["program", "submit", "--manager-url", manager.url, "--icpn", "X",
                 "--target", "z2:1", "--image", str(image),
                 "--journal", str(tmp_path / "absent" / "j.json")])
    assert code == programming.EXIT_USAGE
    assert manager.posts == []


def test_accepted_answer_without_batch_identity_is_unknown_not_pass(manager, tmp_path, image,
                                                                   capsys, monkeypatch):
    original = FakeManager.view
    monkeypatch.setattr(FakeManager, "view", staticmethod(
        lambda batch: {**original(batch), "batch_id": None}))
    assert submit(manager, tmp_path, image) == programming.EXIT_UNKNOWN
    assert output(capsys)["reason"] == "BATCH_IDENTITY_MISMATCH"
    assert manager.count("/api/programming/batches") == 1


# ------------------------------------------------------------------ Manual Repeat

class RepeatManager(FakeManager):
    """The Manager's Manual Repeat contract: Cycles, pauses and Continue.

    ``cycles[(alias, site)]`` scripts each Cycle's outcome ("PASS"/"FAIL").
    A settled Cycle pauses (replace-IC, or any FAIL); a Debug PASS proceeds.
    """

    def __init__(self):
        super().__init__()
        self.cycles: dict[tuple[str, int], list[str]] = {}
        self.continues: list[dict] = []
        self.lose_continue = False

    def admit(self, body):
        batch = super().admit(body)
        repeat = body.get("repeat", 1)
        batch["policy"] = {"repeat": repeat, "retry_limit": body.get("retry_limit", 0),
                           "replace_ic_before_next_cycle": body.get("replace_ic_before_next_cycle", True),
                           "stop_policy": body.get("stop_policy")}
        for unit in batch["units"]:
            unit["cycle"] = {"planned": repeat, "index": 1, "state": "ACTIVE", "disposition": None,
                             "settled": 0, "pass": 0, "fail": 0, "retry_attempts": 0,
                             "remaining": repeat, "continue_seq": 0, "continued_seq": 0,
                             "wait_reason": None, "last": None}
        return batch

    def advance(self, batch):
        if batch.get("policy", {}).get("repeat", 1) == 1:
            return super().advance(batch)
        batch["polls"] += 1
        if batch["state"] == "finished":
            return
        for unit in batch["units"]:
            c = unit["cycle"]
            if c["state"] != "ACTIVE":
                continue
            script = self.cycles.get((unit["ppu_alias"], unit["site_id"]), [])
            outcome = script[c["settled"]] if c["settled"] < len(script) else "PASS"
            c["settled"] += 1
            c["pass" if outcome == "PASS" else "fail"] += 1
            c["remaining"] = c["planned"] - c["settled"]
            c["last"] = {"cycle_index": c["index"], "outcome": outcome, "reason": None,
                         "attempts": 1, "receipt": {"job_id": f"job-{unit['site_id']}-{c['index']}",
                                                    "job_state": "success" if outcome == "PASS" else "failed",
                                                    "safe_off": True}}
            unit["attempts"] = [{"attempt": 1, "job_id": c["last"]["receipt"]["job_id"],
                                 "outcome": outcome, "safe_off": True}]
            if c["settled"] >= c["planned"]:
                c.update(state="ENDED", disposition="COMPLETED_WITH_FAILURES" if c["fail"] else "COMPLETED")
                unit.update(outcome="FAIL" if c["fail"] else "PASS", status="FINISHED")
            elif outcome == "PASS" and not batch["policy"]["replace_ic_before_next_cycle"]:
                c["index"] += 1
            else:
                c.update(state="AWAITING_CONTINUE", continue_seq=c["continue_seq"] + 1,
                         wait_reason="REPLACE_IC" if outcome == "PASS" else "FAIL_REVIEW")
                unit["status"] = "AWAITING_CONTINUE"
        if all(u["cycle"]["state"] == "ENDED" for u in batch["units"]):
            outcomes = [u["outcome"] for u in batch["units"]]
            batch.update(state="finished", execution_status="COMPLETED",
                         outcome="FAIL" if "FAIL" in outcomes else "PASS")
        batch["cycles"] = {k: sum(u["cycle"][k] for u in batch["units"])
                           for k in ("planned", "settled", "pass", "fail", "remaining")}

    def continue_site(self, batch, body):
        refuse = lambda code: (409, {"ok": False, "error": {"code": code, "message": code}})
        self.continues.append(dict(body))
        unit = next(u for u in batch["units"]
                    if u["ppu_alias"] == body["ppu_alias"] and u["site_id"] == body["site_id"])
        c = unit["cycle"]
        if body["continue_seq"] == c["continued_seq"] and c["continued_seq"]:
            return 200, {"ok": True, "duplicate": True, "batch": self.view(batch)}
        if c["state"] != "AWAITING_CONTINUE" or body["continue_seq"] != c["continue_seq"]:
            return refuse("programming_continue_stale")
        if batch["stop_requested"]:
            return refuse("programming_batch_stopping")
        c.update(continued_seq=body["continue_seq"], state="ACTIVE", wait_reason=None,
                 index=c["index"] + 1)
        unit["status"] = "RUNNING"
        if self.lose_continue:
            return 500, {"ok": False}
        return 200, {"ok": True, "duplicate": False, "batch": self.view(batch)}


@pytest.fixture
def repeat_manager():
    fake = RepeatManager()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(fake))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield fake
    server.shutdown()
    server.server_close()


def cont(manager, batch_id, *extra):
    return main(["program", "continue", "--manager-url", manager.url, "--batch-id", batch_id, *extra])


def batch_post(manager):
    return next(body for path, body in manager.posts if path == "/api/programming/batches")


def test_repeat_one_request_and_output_are_unchanged(repeat_manager, tmp_path, image, capsys):
    assert submit(repeat_manager, tmp_path, image, targets=("z2:1",)) == 0
    out = output(capsys)
    body = batch_post(repeat_manager)
    assert body["repeat"] == 1 and "replace_ic_before_next_cycle" not in body
    assert "repeat" not in out["batch"] and "awaiting_continue" not in out["batch"]
    assert "cycle" not in out["batch"]["sites"][0]
    journal = json.loads((tmp_path / "journal.json").read_text())
    assert journal["policy"] == {"repeat": 1, "retry_limit": 0, "stop_policy": {"kind": "never"}}


@pytest.mark.parametrize("value", ["0", "10001", "-3"])
def test_illegal_repeat_submits_nothing(repeat_manager, tmp_path, image, capsys, value):
    assert submit(repeat_manager, tmp_path, image, "--repeat", value) == 2
    assert repeat_manager.posts == [] and not (tmp_path / "journal.json").exists()


def test_repeat_and_replace_ic_reach_the_manager_and_the_journal(repeat_manager, tmp_path, image, capsys):
    assert submit(repeat_manager, tmp_path, image, "--repeat", "10000", "--replace-ic", "no",
                  "--no-wait", targets=("z2:1",)) == 0
    body = batch_post(repeat_manager)
    assert body["repeat"] == 10000 and body["replace_ic_before_next_cycle"] is False
    journal = json.loads((tmp_path / "journal.json").read_text())
    assert journal["policy"]["repeat"] == 10000
    assert journal["policy"]["replace_ic_before_next_cycle"] is False


def test_submit_returns_6_when_a_site_waits_and_names_each_continue(repeat_manager, tmp_path, image, capsys):
    code = submit(repeat_manager, tmp_path, image, "--repeat", "3", targets=("z2:1,2",))
    out = output(capsys)
    assert code == 6
    batch = out["batch"]
    assert [(w["site_id"], w["wait_reason"], w["continue_seq"]) for w in batch["awaiting_continue"]] \
        == [(1, "REPLACE_IC", 1), (2, "REPLACE_IC", 1)]
    bid = out["batch_id"]
    assert batch["next"] == [f"plasmactl program continue --batch-id {bid} --site z2:1",
                             f"plasmactl program continue --batch-id {bid} --site z2:2",
                             f"plasmactl program status --batch-id {bid} --wait"]
    assert batch["sites"][0]["cycle"]["settled"] == 1 and batch["repeat"]["repeat"] == 3
    assert repeat_manager.count("/api/programming/batches") == 1


def test_continue_only_the_named_site(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "3", targets=("z2:1,2",))
    bid = output(capsys)["batch_id"]
    assert cont(repeat_manager, bid, "--site", "z2:1") == 0
    out = output(capsys)
    assert [(s["site_id"], s["result"], s["post_count"]) for s in out["sites"]] == [(1, "ACCEPTED", 1)]
    assert [c["site_id"] for c in repeat_manager.continues] == [1]
    assert out["actor"].startswith("plasmactl-local:") and out["actor_verified"] is False
    assert repeat_manager.continues[0]["actor"] == out["actor"]
    batch = repeat_manager.batches[bid]
    assert batch["units"][1]["cycle"]["state"] == "AWAITING_CONTINUE"  # Site 2 untouched


def test_multi_site_batch_requires_explicit_sites(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "2", targets=("z2:1,2",))
    bid = output(capsys)["batch_id"]
    assert cont(repeat_manager, bid) == 2
    assert repeat_manager.continues == []


def test_one_site_batch_may_omit_site(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "2", targets=("z2:1",))
    bid = output(capsys)["batch_id"]
    assert cont(repeat_manager, bid) == 0
    assert [c["site_id"] for c in repeat_manager.continues] == [1]


def test_two_sites_named_separately(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "2", targets=("z2:1,2",))
    bid = output(capsys)["batch_id"]
    assert cont(repeat_manager, bid, "--site", "z2:1", "--site", "z2:2") == 0
    assert [c["site_id"] for c in repeat_manager.continues] == [1, 2]
    assert cont(repeat_manager, bid, "--site", "z2:1", "--site", "z2:1") == 2


def test_site_not_waiting_is_refused_without_a_post(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "2", targets=("z2:1,2",))
    bid = output(capsys)["batch_id"]
    assert cont(repeat_manager, bid, "--site", "z2:1") == 0
    capsys.readouterr()
    assert cont(repeat_manager, bid, "--site", "z2:1") == 4
    out = output(capsys)
    assert out["sites"][0]["result"] == "NOT_AWAITING_CONTINUE" and out["sites"][0]["post_count"] == 0
    assert len(repeat_manager.continues) == 1
    assert cont(repeat_manager, bid, "--site", "z2:9") == 2


def test_repeated_and_stale_seq_follow_the_manager(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "3", targets=("z2:1",))
    bid = output(capsys)["batch_id"]
    assert cont(repeat_manager, bid, "--seq", "1") == 0
    capsys.readouterr()
    # A double click / re-run with the same pause: idempotent, nothing new runs.
    assert cont(repeat_manager, bid, "--seq", "1") == 0
    assert output(capsys)["sites"][0]["result"] == "ALREADY_ACCEPTED"
    assert cont(repeat_manager, bid, "--seq", "7") == 4
    assert "programming_continue_stale" in output(capsys)["sites"][0]["result"]
    assert cont(repeat_manager, bid, "--site", "z2:1", "--site", "z2:2", "--seq", "1") == 2


def test_lost_continue_answer_is_unknown_and_never_resent(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "2", targets=("z2:1",))
    bid = output(capsys)["batch_id"]
    repeat_manager.lose_continue = True
    assert cont(repeat_manager, bid) == 3
    out = output(capsys)
    assert out["sites"][0]["result"].startswith("OUTCOME_UNKNOWN")
    assert len(repeat_manager.continues) == 1


def test_stop_wins_over_continue(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "2", targets=("z2:1",))
    bid = output(capsys)["batch_id"]
    assert main(["program", "stop", "--manager-url", repeat_manager.url, "--batch-id", bid]) == 0
    capsys.readouterr()
    assert cont(repeat_manager, bid) == 4
    assert "programming_batch_stopping" in output(capsys)["sites"][0]["result"]


def test_debug_fail_pauses_and_status_wait_returns_6_then_finishes(repeat_manager, tmp_path, image, capsys):
    repeat_manager.cycles[("z2", 1)] = ["PASS", "FAIL", "PASS"]
    code = submit(repeat_manager, tmp_path, image, "--repeat", "3", "--replace-ic", "no",
                  targets=("z2:1",))
    out = output(capsys)
    assert code == 6
    assert out["batch"]["awaiting_continue"][0]["wait_reason"] == "FAIL_REVIEW"
    site = out["batch"]["sites"][0]["cycle"]
    assert (site["settled"], site["pass"], site["fail"]) == (2, 1, 1)
    bid = out["batch_id"]
    assert cont(repeat_manager, bid) == 0
    capsys.readouterr()
    status = main(["program", "status", "--manager-url", repeat_manager.url, "--batch-id", bid,
                   "--wait", "--quiet"])
    out = output(capsys)
    assert status == 1 and out["batch"]["outcome"] == "FAIL"
    assert out["batch"]["repeat"]["cycles"]["settled"] == 3 and out["batch"]["next"] == []


def test_progress_line_shows_cycle_counters(repeat_manager, tmp_path, image, capsys):
    submit(repeat_manager, tmp_path, image, "--repeat", "2", targets=("z2:1",))
    bid = output(capsys)["batch_id"]
    line = programming._progress_line(repeat_manager.view(repeat_manager.batches[bid]))
    assert "z2:1 c1/2 P1 F0 R0 WAITING REPLACE_IC" in line

#!/usr/bin/env python3
"""One bounded Manual Repeat HIL step over the canonical Manager API only.

start (issue) -> exactly ONE Batch POST -> poll -> (H2) per-Site Continue.
Never resends a Batch; any non-PASS Cycle -> Stop Queuing, no Continue.
Evidence-only helper (not a product path); see README.md in this directory.
"""
import argparse, base64, hashlib, json, sys, time, urllib.error, urllib.request
from pathlib import Path

MANAGER = "http://127.0.0.1:18280"
PPU = "http://192.168.2.99:18080"
IMAGE_SHA = "e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c"


def call(method, url, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--image", required=True)
    ap.add_argument("--repeat", type=int, required=True)
    ap.add_argument("--replace-ic", choices=["true", "false"], required=True)
    ap.add_argument("--isolation-hold-s", type=float, default=30.0)
    a = ap.parse_args()
    out = Path(__file__).parent / a.label
    out.mkdir(exist_ok=False)
    log = (out / "progress.txt").open("a")

    def note(msg):
        line = f"{time.strftime('%H:%M:%SZ', time.gmtime())} {msg}"
        print(line, flush=True); log.write(line + "\n"); log.flush()

    image = Path(a.image).read_bytes()
    assert hashlib.sha256(image).hexdigest() == IMAGE_SHA
    rep = {"label": a.label, "repeat": a.repeat, "replace_ic": a.replace_ic == "true",
           "batch_post_count": 0, "continue_posts": [], "physical_ic_replaced": False}
    save = lambda: (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n")

    code, issued = call("POST", f"{MANAGER}/api/programming/starts", {"kind": "batch"})
    assert code == 200, issued
    start_id = rep["start_id"] = issued["start"]["start_id"]
    save()
    body = {"icpn": "STM32F103C8T6", "targets": [{"ppu_alias": "z2", "site_ids": [1, 2]}],
            "operations": ["erase", "program", "verify"],
            "image_base64": base64.b64encode(image).decode(), "image_filename": Path(a.image).name,
            "retry_limit": 0, "stop_policy": {"kind": "never"},
            "repeat": a.repeat, "replace_ic_before_next_cycle": a.replace_ic == "true",
            "start_id": start_id}
    rep["batch_post_count"] = 1
    save()
    try:
        code, answer = call("POST", f"{MANAGER}/api/programming/batches", body, timeout=60)
    except Exception as exc:  # lost answer: reconcile read-only, never resend
        rep["submission"] = f"OUTCOME_UNKNOWN_{type(exc).__name__}"
        rep["reconcile"] = call("GET", f"{MANAGER}/api/programming/starts/{start_id}")[1]
        save(); note("BATCH POST OUTCOME UNKNOWN; reconciled read-only; nothing resent"); return 2
    if code != 202:
        rep["submission"] = f"REFUSED_{code}"; rep["refusal"] = answer; save()
        note(f"BATCH REFUSED {code} {answer}"); return 3
    batch_id = rep["batch_id"] = answer["batch"]["batch_id"]
    rep["submission"] = "ACCEPTED"; save()
    note(f"batch {batch_id} start {start_id} repeat {a.repeat} replace_ic {a.replace_ic}")

    stopped = False
    phase = "both_paused" if a.replace_ic == "true" else None
    hold_until = None
    site2_jobs_at_continue = None
    last = None
    while True:
        code, payload = call("GET", f"{MANAGER}/api/programming/batches/{batch_id}")
        if code != 200:
            note(f"poll HTTP {code}; nothing resubmitted"); time.sleep(1); continue
        b = payload["batch"]
        units = {u["site_id"]: u for u in b["units"]}
        state = " | ".join(
            f"S{s} {u['cycle']['state']} c{u['cycle']['index']}/{u['cycle']['planned']} "
            f"P{u['cycle']['pass']} F{u['cycle']['fail']} seq{u['cycle']['continue_seq']}/{u['cycle']['continued_seq']}"
            f" {u['cycle']['wait_reason'] or ''}".rstrip()
            for s, u in sorted(units.items()))
        if state != last:
            note(state); last = state
        if b["outcome"] is not None:
            break
        bad = [u for u in units.values() if u["cycle"]["state"] == "AWAITING_CONTINUE"
               and u["cycle"]["wait_reason"] != "REPLACE_IC"]
        if bad and not stopped:
            note(f"non-PASS pause {[(u['site_id'], u['cycle']['wait_reason']) for u in bad]}: STOP QUEUING, no Continue")
            call("POST", f"{MANAGER}/api/programming/batches/{batch_id}/stop", {"stop": "STOP_QUEUING"})
            stopped = True
        if phase == "both_paused" and all(
                u["cycle"]["state"] == "AWAITING_CONTINUE" and u["cycle"]["continue_seq"] == 1
                for u in units.values()) and not stopped:
            site2_jobs_at_continue = units[2]["cycle"]["settled"]
            code, ans = call("POST", f"{MANAGER}/api/programming/batches/{batch_id}/continue",
                             {"ppu_alias": "z2", "site_id": 1, "continue_seq": 1, "actor": "hil-operator-test"})
            rep["continue_posts"].append({"site_id": 1, "seq": 1, "http": code,
                                          "duplicate": ans.get("duplicate"), "at": time.time()})
            save(); note(f"CONTINUE Site 1 only -> HTTP {code}")
            phase = "isolation"; hold_until = time.monotonic() + a.isolation_hold_s
        elif phase == "isolation" and time.monotonic() >= hold_until:
            u2 = units[2]["cycle"]
            rep["isolation"] = {"site2_state": u2["state"], "site2_settled": u2["settled"],
                                "site2_settled_at_continue": site2_jobs_at_continue,
                                "site2_continued_seq": u2["continued_seq"],
                                "site1_index": units[1]["cycle"]["index"],
                                "site1_state": units[1]["cycle"]["state"],
                                "site1_settled": units[1]["cycle"]["settled"]}
            save(); note(f"isolation check {rep['isolation']}")
            code, ans = call("POST", f"{MANAGER}/api/programming/batches/{batch_id}/continue",
                             {"ppu_alias": "z2", "site_id": 2, "continue_seq": 1, "actor": "hil-operator-test"})
            rep["continue_posts"].append({"site_id": 2, "seq": 1, "http": code,
                                          "duplicate": ans.get("duplicate"), "at": time.time()})
            save(); note(f"CONTINUE Site 2 -> HTTP {code}")
            phase = "done"
        time.sleep(1.0)

    (out / "batch-final.json").write_text(json.dumps(b, indent=1) + "\n")
    code, cyc = call("GET", f"{MANAGER}/api/programming/batches/{batch_id}/cycles?offset=0&limit=1000")
    (out / "cycles.json").write_text(json.dumps(cyc, indent=1) + "\n")
    jobs = []
    for r in cyc.get("records", []):
        if r["type"] != "cycle":
            continue
        for at in r["attempts"]:
            _c, job = call("GET", f"{PPU}/api/status?job={at['job_id']}")
            (out / f"{at['job_id']}.json").write_text(json.dumps(job, indent=1) + "\n")
            j = job.get("job", job)
            jobs.append({"site": r["site_id"], "cycle": r["cycle_index"], "outcome": r["outcome"],
                         "job_id": at["job_id"], "run_id": at["run_id"], "plan_id": at["plan_id"],
                         "safe_off": at["safe_off"], "started": j.get("started_at"),
                         "finished": j.get("finished_at")})
    rep.update(outcome=b["outcome"], execution_status=b["execution_status"], reason=b["reason"],
               cycles=b["cycles"], jobs=jobs,
               units={s: {k: u["cycle"][k] for k in ("planned", "settled", "pass", "fail",
                                                      "retry_attempts", "disposition")}
                      for s, u in units.items()})
    save()
    note(f"FINAL {b['outcome']} {b['execution_status']} cycles={b['cycles']} jobs={len(jobs)}")
    return 0 if b["outcome"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

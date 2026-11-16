"""SWD clock 2-Site HIL (copied from WP-07 run_batch.py; adds --allow-activation, --samplerate). One canonical Manager Batch on Z2 Sites, with passive LA2016 capture.

One POST per invocation. A lost POST response is reconciled read-only via
GET /api/programming/starts/{start_id}; it is never resent.

usage: run_batch.py LABEL --sites 1,2 --image v01|v02 [--ops erase,program,verify]
                    [--stop-threshold N] [--la-seconds S] [--expect-max-jobs N]
"""
import argparse, base64, hashlib, json, subprocess, threading, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANAGER = "http://127.0.0.1:18280"
GATEWAY = "http://192.168.2.99:18080"
LA_APP = "/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage"
LA_APP_SHA = "b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475"
IMAGES = {"v01": "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d",
          "v02": "e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c"}
FILENAMES = {"v01": "plasma-blue-pill-cdc.bin", "v02": "plasma-blue-pill-cdc-v0.2.bin"}
TERMINAL = {"PASS", "FAIL", "PARTIAL", "OUTCOME_UNKNOWN", "BLOCKED"}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(method, url, body=None, timeout=15):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def la_conn():
    for d in Path("/sys/bus/usb/devices").iterdir():
        try:
            if (d / "idVendor").read_text().strip() == "77a1" and (d / "idProduct").read_text().strip() == "01a2":
                return f"{int((d / 'busnum').read_text())}.{int((d / 'devnum').read_text())}"
        except FileNotFoundError:
            continue
    raise RuntimeError("LA2016_NOT_FOUND")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--sites", required=True)
    ap.add_argument("--image", required=True, choices=IMAGES)
    ap.add_argument("--ops", default="erase,program,verify")
    ap.add_argument("--stop-threshold", type=int, default=1)
    ap.add_argument("--la-seconds", type=int, default=60)
    ap.add_argument("--expect-max-jobs", type=int, required=True)
    ap.add_argument("--channels", default="CH0,CH1,CH2,CH3,CH4,CH5")
    ap.add_argument("--z2-sample-seconds", type=int, default=0)
    ap.add_argument("--retry-limit", type=int, default=0)
    ap.add_argument("--allow-activation", action="store_true")
    ap.add_argument("--samplerate", default="20m")
    a = ap.parse_args()
    sites = [int(s) for s in a.sites.split(",")]
    ops = a.ops.split(",")
    out = HERE / a.label
    out.mkdir(exist_ok=False)
    rep = {"schema": "plasma.wp07.hil-step.v1", "label": a.label, "sites": sites, "operations": ops,
           "image": a.image, "image_sha256": IMAGES[a.image], "post_count": 0,
           "retry_limit": a.retry_limit}

    def save():
        (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n")

    image = (HERE / "img" / f"{a.image}.bin").read_bytes()
    assert hashlib.sha256(image).hexdigest() == IMAGES[a.image]
    assert hashlib.sha256(Path(LA_APP).read_bytes()).hexdigest() == LA_APP_SHA

    # Preconditions: PPU idle, no lease, all target Sites idle openocd.
    code, st = http("GET", GATEWAY + "/api/status")
    assert code == 200 and st["ok"] and st["ppu"]["ppu_id"] == "z2-hil", st
    ex = st["ppu"]["execution"]
    assert ex["busy"] is False and ex["active_job_count"] == 0, ex
    by = {s["site_id"]: s for s in st["sites"]}
    for s in sites:
        assert by[s]["enabled"] and by[s]["state"] == "idle" and by[s]["interface"] == "openocd", by[s]
    (out / "pre-status.json").write_text(json.dumps(st, indent=1))
    code, boot = http("GET", MANAGER + "/api/registry/z2/bootstrap")
    assert code == 200 and boot["pairing"]["device_authenticated"] is True
    rep["runtime_release"] = boot["bootstrap"]["runtime"]["release_id"]
    rep["active_set_before"] = ((boot["bootstrap"].get("deployment") or {}).get("result") or {}).get("active_asset_set")

    # Read-only plan preview per Site: must reuse the Active Resource Set, no activation, no FPGA.
    rep["plans"] = {}
    for s in sites:
        code, p = http("POST", MANAGER + "/api/registry/z2/bootstrap/programming/plans", {
            "icpn": "STM32F103C8T6", "site_id": s, "operations": ops,
            "image_base64": base64.b64encode(image).decode(), "image_filename": FILENAMES[a.image]}, timeout=30)
        (out / f"plan-site{s}.json").write_text(json.dumps(p, indent=1))
        assert code == 200 and "plan" in p, (code, p)
        plan = p["plan"]
        assert plan["fpga_load"] is False, plan
        if not a.allow_activation:
            assert plan["activation_required"] is False and plan["resource"]["reuse"] is True, plan["resource"]
        rep.setdefault("plan_activation", {})[s] = {"activation_required": plan["activation_required"], "reuse": plan["resource"]["reuse"]}
        assert plan["image_asset"]["sha256"] == IMAGES[a.image]
        rep["plans"][s] = {"plan_id": plan["plan_id"], "route": plan["route"]["route_id"],
                           "resource_set_sha256": plan["resource"]["resource_set_sha256"],
                           "job_binding_sha256": plan["job_binding_sha256"],
                           "active_generation": (plan["resource"].get("ppu_reported") or {}).get("generation")}

    code, issued = http("POST", MANAGER + "/api/programming/starts", {"kind": "batch"})
    start_id = issued.get("start_id") or (issued.get("start") or {}).get("start_id")
    assert code in (200, 201) and issued.get("ok") and len(start_id) == 32, issued
    rep["start_id"] = start_id
    body = {"icpn": "STM32F103C8T6", "operations": ops, "image_base64": base64.b64encode(image).decode(),
            "image_filename": FILENAMES[a.image], "start_id": start_id,
            "targets": [{"ppu_alias": "z2", "site_ids": sites}], "repeat": 1, "retry_limit": a.retry_limit,
            "stop_policy": {"kind": "failed_sites", "threshold": a.stop_threshold}}
    save()

    # Arm passive LA2016 before the single POST.
    wave = out / "la.sr"
    argv = [LA_APP, "--appimage-extract-and-run", "--loglevel", "3", "--driver", "kingst-la2016:conn=" + la_conn(),
            "--config", "samplerate=" + a.samplerate, "--config", "voltage_threshold=1.4-1.4",
            "--channels", a.channels, "--samples", str(int(float(a.samplerate.rstrip("m")) * 1_000_000) * a.la_seconds),
            "--output-file", str(wave)]
    ready = threading.Event()
    la_log = (out / "la.log").open("w")
    cap = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def drain():
        for line in cap.stdout:
            la_log.write(f"{time.monotonic_ns()} {line}"); la_log.flush()
            if "session: Starting." in line:
                rep["la_session_starting_mono_ns"] = time.monotonic_ns()
                rep["la_session_starting_wall_ns"] = time.time_ns()
                ready.set()
    threading.Thread(target=drain, daemon=True).start()
    if not ready.wait(20) or cap.poll() is not None:
        rep["error"] = "LA_NOT_ARMED"; save(); cap.kill(); return 2

    # Z2 500 ms CPU/RAM/OpenOCD sampler over the pinned SSH helper (read-only).
    sampler = None
    if a.z2_sample_seconds:
        import sys as _sys
        _sys.path.insert(0, "/storage/projects/plasma-wt-wp07-root/scripts")
        import plasma_wordport_program as _w
        creds, hosts = _w.z2_login_credentials(Path.home())
        code = (HERE / "z2_sampler.py").read_text()

        def sample():
            rc, txt = _w.password_ssh_z2(["/opt/plasma/python/3.12.13/bin/python3", "-I", "-c", code,
                                          str(a.z2_sample_seconds)], creds, hosts,
                                         timeout=a.z2_sample_seconds + 60)
            rows = [l for l in txt.splitlines() if l.startswith("mono_s,") or (l[:1].isdigit() and l.count(",") == 9)]
            (out / "z2-resources.csv").write_text("\n".join(rows) + "\n")
            rep["z2_sampler_rc"] = rc
        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        time.sleep(4)  # SSH + sudo login before the POST

    # PPU observer: per-Site Job state from SWPC, monotonic + wall, every 100 ms.
    stop_obs = threading.Event()
    samples = []

    def observe():
        while not stop_obs.is_set():
            t0 = time.monotonic_ns()
            try:
                c, s2 = http("GET", GATEWAY + "/api/status", timeout=3)
                row = {"mono_ns": t0, "wall_ns": time.time_ns(), "ok": c == 200,
                       "execution": s2.get("ppu", {}).get("execution"),
                       "sites": {x["site_id"]: {"state": x["state"], "job": x["current_job_id"]}
                                 for x in s2.get("sites", []) if x["site_id"] in sites}}
            except Exception as exc:  # observation only
                row = {"mono_ns": t0, "error": type(exc).__name__}
            samples.append(row)
            stop_obs.wait(0.1)
    obs = threading.Thread(target=observe, daemon=True); obs.start()

    rep["post_count"] = 1
    rep["post_mono_ns"] = time.monotonic_ns(); rep["post_wall_ns"] = time.time_ns()
    save()
    try:
        code, resp = http("POST", MANAGER + "/api/programming/batches", body, timeout=20)
        rep["post_http"] = code
        (out / "batch-start-response.json").write_text(json.dumps(resp, indent=1))
        batch_id = (resp.get("batch") or {}).get("batch_id")
    except Exception as exc:
        rep["post_error"] = "RESPONSE_UNKNOWN:" + type(exc).__name__
        batch_id = None
        c, rec = http("GET", MANAGER + f"/api/programming/starts/{start_id}")
        (out / "start-reconcile.json").write_text(json.dumps(rec, indent=1))
        batch_id = (rec.get("start") or rec).get("batch_id") if c == 200 else None
    rep["batch_id"] = batch_id
    save()

    final = None
    deadline = time.monotonic() + a.la_seconds + 60
    while batch_id and time.monotonic() < deadline:
        c, p = http("GET", MANAGER + f"/api/programming/batches/{batch_id}")
        if c == 200 and p.get("batch", {}).get("outcome") in TERMINAL:
            final = p; break
        time.sleep(0.5)
    rep["batch_terminal_mono_ns"] = time.monotonic_ns()
    stop_obs.set(); obs.join(5)
    (out / "ppu-observations.json").write_text(json.dumps(samples))
    cap.wait(a.la_seconds + 60); la_log.close()
    if sampler is not None:
        sampler.join(a.z2_sample_seconds + 90)
    rep["la_exit"] = cap.returncode
    if final is None:
        rep["error"] = "BATCH_NOT_TERMINAL_IN_WINDOW"; save(); return 3
    (out / "batch-final.json").write_text(json.dumps(final, indent=1))
    batch = final["batch"]
    rep["outcome"] = batch["outcome"]; rep["counts"] = batch.get("counts")
    c, rec = http("GET", MANAGER + f"/api/programming/starts/{start_id}")
    (out / "start-reconcile.json").write_text(json.dumps(rec, indent=1))
    rep["units"] = {}
    for unit in batch["units"]:
        s = unit["site_id"]
        attempts = unit.get("attempts") or []
        info = {"outcome": unit.get("outcome"), "reason": unit.get("reason"), "attempts": len(attempts)}
        last = attempts[-1] if attempts else {}
        run_id = last.get("run_id")
        info.update({"run_id": run_id, "job_id": last.get("job_id"), "safe_off": last.get("safe_off"),
                     "attempt_started_at": last.get("started_at"), "attempt_finished_at": last.get("finished_at")})
        if run_id:
            c, run = http("GET", MANAGER + f"/api/registry/z2/bootstrap/programming/runs/{run_id}")
            (out / f"run-site{s}.json").write_text(json.dumps(run, indent=1))
            info["run_http"] = c
            if info["job_id"]:
                c, j = http("GET", GATEWAY + "/api/status?job=" + info["job_id"])
                (out / f"ppu-job-site{s}.json").write_text(json.dumps(j, indent=1))
                jj = j.get("job") or {}
                info["ppu_job"] = {k: jj.get(k) for k in ("state", "created_at", "started_at", "updated_at")}
        info["attempt_runs"] = []
        for n, att in enumerate(attempts, 1):
            rid = att.get("run_id")
            entry = {"n": n, "run_id": rid, "job_id": att.get("job_id"), "outcome": att.get("outcome"),
                     "safe_off": att.get("safe_off"), "retry": att.get("retry")}
            if rid:
                c, r = http("GET", MANAGER + f"/api/registry/z2/bootstrap/programming/runs/{rid}")
                (out / f"run-site{s}-a{n}.json").write_text(json.dumps(r, indent=1))
                rc = (r.get("run") or {}).get("receipt") or {}
                entry.update(run_http=c, reason=(r.get("run") or {}).get("reason"),
                             receipt_safe_off=rc.get("safe_off"),
                             safe_off_source=rc.get("safe_off_source"),
                             flash_result=rc.get("flash_result"))
            if att.get("job_id"):
                c, j = http("GET", GATEWAY + "/api/status?job=" + att["job_id"])
                (out / f"ppu-job-site{s}-a{n}.json").write_text(json.dumps(j, indent=1))
            info["attempt_runs"].append(entry)
        rep["units"][s] = info
    code, boot = http("GET", MANAGER + "/api/registry/z2/bootstrap")
    rep["active_set_after"] = ((boot["bootstrap"].get("deployment") or {}).get("result") or {}).get("active_asset_set")
    code, st = http("GET", GATEWAY + "/api/status")
    (out / "post-status.json").write_text(json.dumps(st, indent=1))
    rep["post_execution"] = st["ppu"]["execution"]
    save()
    print(json.dumps({k: rep.get(k) for k in ("label", "outcome", "batch_id", "start_id", "units", "post_execution", "la_exit")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

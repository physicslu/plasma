"""Passive LA2016 capture of a WHOLE Z2 OpenOCD flow (no crop), then analysis.

usage: la_full.py <z2-script.py> <outdir> [seconds=8]
LA: 50 MHz, CH0..CH3, trigger CH0 rising (first SWCLK edge), <seconds> total.
The flow is split at SWCLK-idle gaps >= 250 ms (the Z2 session's 300 ms
markers). Per segment: duration, SWCLK rises, modal period, clock-on fraction.
"""
import hashlib, json, os, signal, stat, subprocess, sys, threading, time, zipfile
from pathlib import Path
import numpy as np

z2script, outdir = Path(sys.argv[1]), Path(sys.argv[2])
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
outdir.mkdir(parents=True, exist_ok=True)
full = outdir / "flow-full.sr"; report = outdir / "flow-la-report.json"
assert not full.exists() and not report.exists(), "EVIDENCE_ALREADY_EXISTS"
RATE = 50_000_000; TOTAL = int(secs * RATE); GAP = RATE // 4
app = Path("/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage")
assert hashlib.sha256(app.read_bytes()).hexdigest() == \
    "b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475", "APPIMAGE_SHA_CHANGED"
conns = []
for e in Path("/sys/bus/usb/devices").iterdir():
    try:
        if ((e / "idVendor").read_text().strip(), (e / "idProduct").read_text().strip()) != ("77a1", "01a2"):
            continue
    except OSError:
        continue
    bus, dev = int((e / "busnum").read_text()), int((e / "devnum").read_text())
    node = Path(f"/dev/bus/usb/{bus:03}/{dev:03}")
    assert stat.S_ISCHR(node.stat().st_mode) and os.access(node, os.R_OK | os.W_OK), "LA_USB_ACCESS_DENIED"
    conns.append(f"{bus}.{dev}")
assert len(conns) == 1, "LA_NOT_UNIQUE"
argv = [str(app), "--appimage-extract-and-run", "--loglevel", "3",
        "--driver", "kingst-la2016:conn=" + conns[0],
        "--config", "samplerate=50m:captureratio=1", "--channels", "CH0,CH1,CH2,CH3",
        "--triggers", "CH0=r", "--samples", str(TOTAL), "--output-file", str(full)]
la = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                      bufsize=1, start_new_session=True)
lines = []
threading.Thread(target=lambda: [lines.append(l) for l in la.stdout], daemon=True).start()
time.sleep(4.0)  # let the LA arm its trigger
rep = {"la_argv": argv[3:], "seconds": secs}
z2 = None
try:
    if la.poll() is None:
        rep["z2_start_unix_ns"] = time.time_ns()
        z2 = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "abi5_openocd_dpidr" / "z2run.py"), str(z2script), "960"],
                            capture_output=True, text=True, timeout=1000)
        rep["z2_end_unix_ns"] = time.time_ns()
    la.wait(timeout=300)
finally:
    if la.poll() is None:
        os.killpg(la.pid, signal.SIGTERM)
        try: la.wait(timeout=5)
        except subprocess.TimeoutExpired: os.killpg(la.pid, signal.SIGKILL); la.wait(timeout=3)
rep["la_exit"] = la.returncode; rep["la_log_tail"] = "".join(lines)[-1500:]
if z2 is not None:
    rep["z2_exit"] = z2.returncode
    js = [l for l in z2.stdout.splitlines() if l.startswith("Z2JSON=")]
    rep["z2"] = json.loads(js[-1][7:]) if js else {"raw": z2.stdout[-3000:] + z2.stderr[-1000:]}
if full.is_file():
    rep["full_sha256"] = hashlib.sha256(full.read_bytes()).hexdigest(); rep["full_bytes"] = full.stat().st_size
    with zipfile.ZipFile(full) as z:
        meta = z.read("metadata").decode()
        unit = int([l for l in meta.splitlines() if l.startswith("unitsize=")][0].split("=")[1])
        names = sorted((n for n in z.namelist() if n.startswith("logic-1-")), key=lambda n: int(n.rsplit("-", 1)[1]))
        s = np.frombuffer(b"".join(z.read(n) for n in names), dtype=np.uint16 if unit == 2 else np.uint8)
    rep["samples"] = int(s.size)
    c = (s & 1).astype(np.int8)
    r = np.flatnonzero((c[1:] == 1) & (c[:-1] == 0)) + 1
    rep["rises"] = int(r.size)
    segs = []
    if r.size > 1:
        p = np.diff(r)
        cut = np.flatnonzero(p >= GAP)
        bounds = np.concatenate(([0], cut + 1, [r.size]))
        for a, b in zip(bounds[:-1], bounds[1:]):
            rr = r[a:b]
            if rr.size < 2:
                segs.append({"start_ms": round(rr[0] / RATE * 1e3, 3), "rises": int(rr.size)}); continue
            pp = np.diff(rr); mode = int(np.bincount(pp).argmax()); span = int(rr[-1] - rr[0])
            segs.append({"start_ms": round(rr[0] / RATE * 1e3, 3), "dur_ms": round(span / RATE * 1e3, 3),
                         "rises": int(rr.size), "period_us": round(mode / RATE * 1e6, 3),
                         "clock_on": round(float(np.minimum(pp, mode).sum()) / span, 3),
                         "max_gap_us": round(float(pp.max()) / RATE * 1e6, 1)})
    rep["segments"] = segs
report.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
z = rep.get("z2", {})
print(json.dumps({k: rep.get(k) for k in ("la_exit", "z2_exit", "samples", "rises", "full_bytes")}, sort_keys=True))
for i, sg in enumerate(rep.get("segments", [])): print("seg", i, sg)
print("Z2:", json.dumps({k: z.get(k) for k in ("result", "action_ms", "clock_khz", "dpidr", "readback_sha256",
                                               "safe_off", "journal_unchanged")}))

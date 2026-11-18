"""Passive LA2016 capture of ONE Z2 OpenOCD action session, then a 200 ms crop.

usage: la_action.py <action> <z2-script.py> <outdir>
LA: 50 MHz, CH0..CH3, trigger CH0 rising (first SWCLK edge of the session),
3 s total. The Z2 session puts >=300 ms SWCLK-idle gaps before/after the
action; the crop starts 1 ms before the first CH0 edge after the first gap
of >= 250 ms and lasts exactly 200 ms. The full capture is kept locally.
"""
import hashlib, io, json, os, signal, stat, subprocess, sys, threading, time, zipfile
from pathlib import Path
import numpy as np

action, z2script, outdir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
outdir.mkdir(parents=True, exist_ok=True)
full = outdir / f"{action}-full.sr"; crop = outdir / f"{action}-200ms.sr"
report = outdir / f"{action}-la-report.json"
assert not full.exists() and not crop.exists() and not report.exists(), "EVIDENCE_ALREADY_EXISTS"
RATE = 50_000_000; TOTAL = 3 * RATE; WIN = RATE // 5; PRE = RATE // 1000; GAP = RATE // 4
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
lines, armed = [], threading.Event()
def drain():
    for line in la.stdout:
        lines.append(line)
        if "session: Starting." in line or "Acquisition" in line:
            armed.set()
threading.Thread(target=drain, daemon=True).start()
armed.wait(10); time.sleep(1.0)  # trigger armed; the session cannot start sooner than SSH
rep = {"action": action, "la_argv": argv[3:], "la_armed_log": armed.is_set()}
z2 = None
try:
    if la.poll() is None:
        rep["z2_start_unix_ns"] = time.time_ns()
        z2 = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "abi5_openocd_dpidr" / "z2run.py"), str(z2script), "960"],
                            capture_output=True, text=True, timeout=1000)
        rep["z2_end_unix_ns"] = time.time_ns()
    la.wait(timeout=120)
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
        raw = b"".join(z.read(n) for n in names)
    s = np.frombuffer(raw, dtype=np.uint16 if unit == 2 else np.uint8)
    rep["samples"] = int(s.size); rep["unitsize"] = unit
    ch = [(s >> i) & 1 for i in range(4)]
    rep["edges"] = {f"CH{i}": int(np.count_nonzero(np.diff(c))) for i, c in enumerate(ch)}
    e0 = np.flatnonzero(np.diff(ch[0])) + 1
    gaps = np.flatnonzero(np.diff(e0) >= GAP) if e0.size > 1 else np.array([], dtype=int)
    if gaps.size:
        start = int(e0[gaps[0] + 1]); lo = max(0, start - PRE); hi = min(s.size, lo + WIN)
        seg = s[lo:hi]
        rep["crop"] = {"first_gap_end_sample": start, "from_sample": lo, "to_sample": hi,
                       "ms": round((hi - lo) / RATE * 1e3, 3),
                       "edges": {f"CH{i}": int(np.count_nonzero(np.diff((seg >> i) & 1))) for i in range(4)}}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("version", "2"); z.writestr("metadata", meta)
            b = seg.tobytes(); step = 4 * 1024 * 1024
            for k, off in enumerate(range(0, len(b), step), 1):
                z.writestr(f"logic-1-{k}", b[off:off + step])
        crop.write_bytes(buf.getvalue())
        rep["crop_sha256"] = hashlib.sha256(crop.read_bytes()).hexdigest()
    else:
        rep["crop"] = None
report.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
z = rep.get("z2", {})
print(json.dumps({k: rep.get(k) for k in ("la_exit", "z2_exit", "samples", "edges", "crop", "crop_sha256")}, sort_keys=True))
print("Z2:", json.dumps({k: z.get(k) for k in ("result", "action_ms", "openocd_s", "dpidr_connect", "dpidr_dpreg0",
                                               "readback_sha256", "safe_off", "journal_unchanged")}))

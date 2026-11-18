"""Analyze one sigrok .sr capture: per-channel SWCLK activity, frequency, and 2-Site overlap.
usage: la_analyze.py la.sr OUT.json   (Site1 SWCLK=CH3 SWDIO=CH4, Site2 SWCLK=CH0 SWDIO=CH1)"""
import json, sys, zipfile, configparser
import numpy as np
z = zipfile.ZipFile(sys.argv[1])
meta = configparser.ConfigParser(); meta.read_string(z.read("metadata").decode())
dev = meta["device 1"]
rate = dev["samplerate"].split()
sr = float(rate[0]) * {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}[rate[1]]
unit = int(dev["unitsize"])
probes = {dev[k]: int(k[5:]) - 1 for k in dev if k.startswith("probe")}
chunks = sorted((n for n in z.namelist() if n.startswith("logic-1")), key=lambda n: int(n.rsplit("-", 1)[1]))
CH = {"CH3": [], "CH0": [], "CH4": 0, "CH1": 0}  # rising-edge indices for clocks, edge counts for data
prev = None; total = 0; carry = b""
for n in chunks:
    buf = carry + z.read(n); usable = len(buf) - len(buf) % unit; carry = buf[usable:]
    d = np.frombuffer(buf[:usable], dtype="<u2" if unit == 2 else np.uint8)
    if prev is not None: d2 = np.r_[np.array([prev], dtype=d.dtype), d]
    else: d2 = d
    off = total - (1 if prev is not None else 0)
    for ch in CH:
        b = ((d2 >> probes[ch]) & 1).astype(np.int8); df = np.diff(b)
        if ch in ("CH3", "CH0"): CH[ch].append(np.where(df == 1)[0] + 1 + off)
        else: CH[ch] += int(np.count_nonzero(df))
    prev = d[-1]; total += len(d)
for ch in ("CH3", "CH0"): CH[ch] = np.concatenate(CH[ch]) if CH[ch] else np.array([], dtype=np.int64)
out = {"samplerate_hz": sr, "samples": int(total), "duration_s": total / sr, "channels": {}}
def bursts(edges, gap):
    if len(edges) == 0: return []
    br = np.where(np.diff(edges) > gap)[0]
    starts = np.r_[edges[0], edges[br + 1]]; ends = np.r_[edges[br], edges[-1]]
    return list(zip(starts, ends))
active = {}
for site, clk, dio in ((1, "CH3", "CH4"), (2, "CH0", "CH1")):
    rise = CH[clk]; dedges = CH[dio]
    info = {"swclk": clk, "swdio": dio, "swclk_rising_edges": int(len(rise)), "swdio_edges": int(dedges)}
    if len(rise) > 2:
        per = np.diff(rise)
        inb = per[per < sr * 2e-6]  # periods inside a burst (< 2 us)
        if len(inb):
            info["period_samples_median"] = float(np.median(inb))
            info["swclk_freq_median_hz"] = sr / float(np.median(inb))
            info["swclk_freq_p5_p95_hz"] = [sr / float(np.percentile(inb, 95)), sr / float(np.percentile(inb, 5))]
            hist = dict(zip(*np.unique(inb, return_counts=True)))
            info["period_hist_top"] = {str(int(k)): int(v) for k, v in sorted(hist.items(), key=lambda x: -x[1])[:6]}
        # duty from high time of in-burst cycles
        b = bursts(rise, int(sr * 0.01))
        info["active_first_s"] = float(rise[0] / sr); info["active_last_s"] = float(rise[-1] / sr)
        info["bursts_10ms_gap"] = [[round(s / sr, 4), round(e / sr, 4)] for s, e in b][:20]
        win = set((rise // int(sr / 1000)).tolist())
        active[site] = win
        info["active_1ms_windows"] = len(win)
    out["channels"][f"site{site}"] = info
if 1 in active and 2 in active:
    a, bb = out["channels"]["site1"], out["channels"]["site2"]
    lo = max(a["active_first_s"], bb["active_first_s"]); hi = min(a["active_last_s"], bb["active_last_s"])
    out["overlap"] = {"interval_overlap_s": max(0.0, hi - lo), "both_active_1ms_windows": len(active[1] & active[2])}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out, indent=1))

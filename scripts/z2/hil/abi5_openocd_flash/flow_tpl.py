# Template (fill @DEST@/@BIN_SHA@). Root on Z2: ONE OpenOCD plasma_swd session on Site 2 running the
# whole Blue Pill flow; 300 ms SWCLK-idle gaps separate the actions for the LA2016 analysis.
import hashlib, json, os, re, subprocess, time
DEST = "@DEST@"; BIN_SHA = "@BIN_SHA@"; IMAGE_ID = "z2-independent-swd-v5-d0add58c"
FW = "/root/.plasma-bluepill-flash/plasma-blue-pill-cdc.bin"
FW_SHA = "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d"; FW_LEN = 18768
RB = "/root/.plasma-bluepill-flash/readback.bin"; J = "/var/lib/plasma-privileged/fpga-deployment-state.json"
B = DEST + "/bin/openocd"; S = DEST + "/share/openocd/scripts"
def F(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def procs(): return subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True).stdout.split()
def facts(): return {"manager": open("/sys/class/fpga_manager/fpga0/state").read().strip(),
                     "journal_sha256": F(J), "journal": json.load(open(J)), "openocd_pids": procs()}
G = ["-c", "sleep 300"]
def step(name, cmd):
    return G + ["-c", f"echo PLASMA_{name}_BEGIN=[clock milliseconds]", "-c", cmd,
                "-c", f"echo PLASMA_{name}_END=[clock milliseconds]"]
ARGS = ["-c", "adapter driver plasma_swd", "-c", "plasma_swd site 2", "-c", "transport select swd",
        "-c", "gdb port disabled", "-c", "tcl port disabled", "-c", "telnet port disabled",
        "-c", "source [find target/stm32f1x.cfg]", "-c", "adapter speed 500",
        "-c", "init", "-c", "reset halt", "-c", "poll off", "-c", "flash probe 0"]
ARGS += step("DPIDR", "echo PLASMA_DPREG0=[stm32f1x.dap dpreg 0]")
ARGS += step("ERASE", "flash erase_address 0x08000000 0x4c00")
ARGS += step("WRITE", f"flash write_image {FW} 0x08000000 bin")
ARGS += step("VERIFY", f"flash verify_image {FW} 0x08000000 bin")
ARGS += step("READ", f"dump_image {RB} 0x08000000 {FW_LEN}")
ARGS += step("RESET", "reset run") + ["-c", "shutdown"]
out = {"t_start": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
pre = out["pre"] = facts()
ok = (F(B) == BIN_SHA and pre["manager"] == "operating" and not pre["openocd_pids"]
      and pre["journal"]["status"] == "IMAGE" and pre["journal"]["image_id"] == IMAGE_ID and F(FW) == FW_SHA)
out["precheck"] = ok
if ok:
    if os.path.exists(RB): os.remove(RB)
    cmd = [B, "-s", S, "-d2"] + ARGS; out["openocd_argv"] = cmd; t0 = time.monotonic()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        log, _ = p.communicate(timeout=900); out["openocd"] = {"rc": p.returncode, "log": log[-30000:]}
    except subprocess.TimeoutExpired:
        p.kill(); log, _ = p.communicate(); out["openocd"] = {"rc": "TIMEOUT_KILLED_CHILD", "log": (log or "")[-30000:]}
    out["openocd_s"] = round(time.monotonic() - t0, 3)
post = out["post"] = facts()
log = out.get("openocd", {}).get("log", "")
t = {(a, b): int(v) for a, b, v in re.findall(r"PLASMA_([A-Z]+)_(BEGIN|END)=(\d+)", log)}
out["action_ms"] = {a: t[(a, "END")] - t[(a, "BEGIN")] for a in ("DPIDR", "ERASE", "WRITE", "VERIFY", "READ", "RESET")
                    if (a, "BEGIN") in t and (a, "END") in t}
out["clock_khz"] = re.findall(r"clock speed (\d+) kHz", log)
out["dpidr"] = re.findall(r"SWD DPIDR (0x[0-9a-fA-F]{8})", log) + re.findall(r"PLASMA_DPREG0=(0x[0-9a-fA-F]+)", log)
out["lines"] = [l for l in log.splitlines() if re.search(r"erased|wrote|verified|dumped|Error|plasma_swd", l)]
out["readback_sha256"] = F(RB) if os.path.exists(RB) else None
out["safe_off"] = "SAFE_OFF_MODE_OFF_VERIFIED" in log
out["journal_unchanged"] = post["journal_sha256"] == pre["journal_sha256"]
good = (out.get("openocd", {}).get("rc") == 0 and out["dpidr"] and all(int(x, 16) == 0x1BA01477 for x in out["dpidr"])
        and re.search(r"erased address 0x08000000 \(length 19456\)", log) and re.search(r"wrote 18768 bytes", log)
        and re.search(r"verified 18768 bytes", log) and out["readback_sha256"] == FW_SHA
        and "PLASMA_RESET_END" in log and out["safe_off"] and out["journal_unchanged"] and not post["openocd_pids"])
out["result"] = "FLOW_PASS" if good else "FLOW_FAIL"
out["t_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
print("Z2JSON=" + json.dumps(out))

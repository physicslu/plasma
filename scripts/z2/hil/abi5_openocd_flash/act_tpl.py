# Template (fill @...@, run via abi5_openocd_dpidr/z2run.py). Root on Z2: ONE OpenOCD
# plasma_swd session on Site 2 for ACTION=@ACTION@ (dpidr|erase|write|verify|read).
# Upload the firmware to FW first; IMAGE_ID / FW_SHA / FW_LEN are this HIL's values.
# Layout: init [+ reset halt, poll off] ; sleep GAP ; ACTION ; sleep GAP ; shutdown.
# reset halt (not halt): flashing while the application left its clocks and
# peripherals running made the stm32f1x write algorithm never start.
# The two SWCLK-idle gaps mark the action for the SWPC LA2016 crop.
import hashlib, json, os, re, subprocess, time
ACTION = "@ACTION@"; SITE = "2"; GAP = 300
DEST = "@DEST@"; BIN_SHA = "@BIN_SHA@"; IMAGE_ID = "z2-independent-swd-v5-d0add58c"
FW = "/root/.plasma-bluepill-flash/plasma-blue-pill-cdc.bin"
FW_SHA = "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d"; FW_LEN = 18768
RB = "/root/.plasma-bluepill-flash/readback.bin"
J = "/var/lib/plasma-privileged/fpga-deployment-state.json"
B = DEST + "/bin/openocd"; S = DEST + "/share/openocd/scripts"
def F(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def procs(): return subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True).stdout.split()
def facts(): return {"manager": open("/sys/class/fpga_manager/fpga0/state").read().strip(),
                     "journal_sha256": F(J), "journal": json.load(open(J)), "openocd_pids": procs()}
BASE = ["-c", "adapter driver plasma_swd", "-c", f"plasma_swd site {SITE}", "-c", "transport select swd",
        "-c", "gdb port disabled", "-c", "tcl port disabled", "-c", "telnet port disabled"]
# target/stm32f1x.cfg sets "adapter speed 1000": override to the 500 kHz default.
TGT = ["-c", "source [find target/stm32f1x.cfg]", "-c", "adapter speed 500",
       "-c", "init", "-c", "reset halt", "-c", "poll off"]
G = ["-c", f"sleep {GAP}"]
MARK = lambda n: ["-c", f"echo PLASMA_{n}_T=[clock milliseconds]"]
ACT = {
    "dpidr": ["-c", "swd newdap bp cpu", "-c", "dap create bp.dap -chain-position bp.cpu", "-c", "init"]
             + G + MARK("BEGIN") + ["-c", "echo PLASMA_DPREG0=[bp.dap dpreg 0]"] + MARK("END") + G,
    "erase": TGT + ["-c", "flash probe 0"] + G + MARK("BEGIN")
             + ["-c", "flash erase_address 0x08000000 0x4c00"] + MARK("END") + G,
    "write": TGT + ["-c", "flash probe 0"] + G + MARK("BEGIN")
             + ["-c", f"flash write_image {FW} 0x08000000 bin"] + MARK("END") + G,
    "verify": TGT + ["-c", "flash probe 0"] + G + MARK("BEGIN")
              + ["-c", f"flash verify_image {FW} 0x08000000 bin"] + MARK("END") + G,
    "read": TGT + G + MARK("BEGIN") + ["-c", f"dump_image {RB} 0x08000000 {FW_LEN}"] + MARK("END") + G
            + ["-c", "reset run", "-c", "echo PLASMA_RESET_RUN_DONE"],
}[ACTION] + ["-c", "shutdown"]
out = {"action": ACTION, "t_start": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
pre = out["pre"] = facts()
ok = (F(B) == BIN_SHA and pre["manager"] == "operating" and not pre["openocd_pids"]
      and pre["journal"]["status"] == "IMAGE" and pre["journal"]["image_id"] == IMAGE_ID
      and F(FW) == FW_SHA)
out["precheck"] = ok
if ok:
    if ACTION == "read" and os.path.exists(RB): os.remove(RB)
    cmd = [B, "-s", S, "-d2"] + BASE + ACT; out["openocd_argv"] = cmd
    t0 = time.monotonic(); out["openocd_start_unix_ns"] = time.time_ns()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        log, _ = p.communicate(timeout=900); out["openocd"] = {"rc": p.returncode, "log": log[-20000:]}
    except subprocess.TimeoutExpired:
        p.kill(); log, _ = p.communicate(); out["openocd"] = {"rc": "TIMEOUT_KILLED_CHILD", "log": (log or "")[-20000:]}
    out["openocd_s"] = round(time.monotonic() - t0, 3)
post = out["post"] = facts()
log = out.get("openocd", {}).get("log", "")
t = {k: int(v) for k, v in re.findall(r"PLASMA_(BEGIN|END)_T=(\d+)", log)}
out["action_ms"] = t["END"] - t["BEGIN"] if len(t) == 2 else None
m = re.findall(r"SWD DPIDR (0x[0-9a-fA-F]{8})", log)
out["clock_khz"] = re.findall(r"clock speed (\d+) kHz", log); out["dpidr_connect"] = m; out["dpidr_dpreg0"] = re.findall(r"PLASMA_DPREG0=(0x[0-9a-fA-F]+)", log)
out["safe_off"] = "SAFE_OFF_MODE_OFF_VERIFIED" in log
out["journal_unchanged"] = post["journal_sha256"] == pre["journal_sha256"]
clean = out["journal_unchanged"] and not post["openocd_pids"] and out["safe_off"]
dp_ok = bool(m) and all(int(x, 16) == 0x1BA01477 for x in m + out["dpidr_dpreg0"])
rc0 = out.get("openocd", {}).get("rc") == 0
if ACTION == "dpidr":
    good = dp_ok and bool(out["dpidr_dpreg0"])
elif ACTION == "erase":
    good = bool(re.search(r"erased address 0x08000000 \(length 19456\)", log))
elif ACTION == "write":
    good = bool(re.search(r"wrote 18768 bytes from file", log))
elif ACTION == "verify":
    good = bool(re.search(r"verified 18768 bytes from file", log))
else:
    out["readback_sha256"] = F(RB) if os.path.exists(RB) else None
    good = out["readback_sha256"] == FW_SHA and "PLASMA_RESET_RUN_DONE" in log
out["result"] = f"{ACTION.upper()}_PASS" if dp_ok and rc0 and clean and good else f"{ACTION.upper()}_FAIL"
out["t_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
print("Z2JSON=" + json.dumps(out))

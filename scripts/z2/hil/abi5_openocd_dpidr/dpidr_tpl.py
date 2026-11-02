# Template (fill @...@). Root on Z2: ONE bounded real DPIDR read on Site @SITE@ via OpenOCD plasma_swd.
# Admission -> OpenOCD (dap init + dpreg 0, no target, no flash) -> revoke.
import hashlib, json, os, re, subprocess, time
SITE="@SITE@"; DEST="@DEST@"; ADM_SHA="@ADM_SHA@"; BIN_SHA="@BIN_SHA@"
R="/root/plasma-path2-approved"; J=R+"/.plasma-fpga-image-deployment-state.json"
REC=f"/run/plasma-z2-swd05/swd-site{SITE}-admission"; PY="/opt/plasma/python/3.12.13/bin/python3"
ADM=DEST+"/libexec/plasma_swd_site_admission.py"; B=DEST+"/bin/openocd"; S=DEST+"/share/openocd/scripts"
def F(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def procs(): return subprocess.run(["pgrep","-x","openocd"],capture_output=True,text=True).stdout.split()
def facts(): return {"boot_id":open("/proc/sys/kernel/random/boot_id").read().strip(),
    "manager":open("/sys/class/fpga_manager/fpga0/state").read().strip(),
    "journal_sha256":F(J),"journal":json.load(open(J)),"openocd_pids":procs(),
    "record_present":os.path.exists(REC)}
out={"t_start":time.strftime("%Y-%m-%dT%H:%M:%S%z")}
pre=out["pre"]=facts()
ok=(F(B)==BIN_SHA and F(ADM)==ADM_SHA and pre["manager"]=="operating" and not pre["openocd_pids"]
    and not pre["record_present"] and pre["journal"]["status"]=="IMAGE"
    and pre["journal"]["image_id"]=="z2-independent-swd-v5-ab79b04e")
out["precheck"]=ok
if ok:
    a=subprocess.run([PY,"-I","-B",ADM,"admit",SITE],capture_output=True,text=True,timeout=120)
    out["admission"]={"rc":a.returncode,"out":(a.stdout+a.stderr)[-3000:]}
    try:
        if a.returncode==0 and "SITE_ADMISSION_RECORD_ISSUED" in a.stdout:
            cmd=[B,"-s",S,"-d2","-c","adapter driver plasma_swd","-c",f"plasma_swd site {SITE}",
                 "-c","transport select swd","-c","gdb port disabled","-c","tcl port disabled",
                 "-c","telnet port disabled","-c","swd newdap bp cpu",
                 "-c","dap create bp.dap -chain-position bp.cpu",
                 "-c","init","-c","echo PLASMA_DPREG0=[bp.dap dpreg 0]","-c","shutdown"]
            out["openocd_argv"]=cmd
            t0=time.monotonic()
            try:
                o=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
                out["openocd"]={"rc":o.returncode,"log":(o.stdout+o.stderr)[-12000:]}
            except subprocess.TimeoutExpired as e:
                out["openocd"]={"rc":"TIMEOUT_KILLED_CHILD","log":str((e.stdout or b"")[-6000:])+str((e.stderr or b"")[-6000:])}
            out["openocd_s"]=round(time.monotonic()-t0,3)
    finally:
        r=subprocess.run([PY,"-I","-B",ADM,"revoke",SITE],capture_output=True,text=True,timeout=60)
        out["revoke"]={"rc":r.returncode,"out":r.stdout[-500:]}
post=out["post"]=facts()
log=out.get("openocd",{}).get("log","")
m=re.findall(r"SWD DPIDR (0x[0-9a-fA-F]{8})",log); d=re.findall(r"PLASMA_DPREG0=(0x[0-9a-fA-F]+)",log)
out["dpidr_connect"]=m; out["dpidr_dpreg0"]=d
out["safe_off"]="SAFE_OFF_MODE_OFF_VERIFIED" in log
out["journal_unchanged"]=post["journal_sha256"]==pre["journal_sha256"]
out["dpidr_pass"]=bool(m) and all(int(x,16)==0x1BA01477 for x in m+d) and bool(d)
out["result"]=("DPIDR_PASS" if out["dpidr_pass"] and out["journal_unchanged"] and not post["openocd_pids"]
               and not post["record_present"] else "DPIDR_FAIL_OR_INCOMPLETE")
out["t_end"]=time.strftime("%Y-%m-%dT%H:%M:%S%z")
print("Z2JSON="+json.dumps(out))

# Template (fill @...@ and run via z2run.py). Root on Z2: side-by-side install of the CI-verified ARMv7 OpenOCD candidate.
# Never touches existing 5088db4c / 9ea7f3d installs, Root Entry or FPGA.
import hashlib, json, os, shutil, subprocess, tarfile, tempfile, io, pwd
TAR_SHA="@TAR_SHA@"; BIN_SHA="@BIN_SHA@"; ADM_SHA="@ADM_SHA@"
PLASMA_SHA="@PLASMA_SHA@"; RUN_ID="@RUN_ID@"
BASE="/opt/plasma/programming-engines/openocd"
DEST=f"{BASE}/0.12.0-5088db4c9154-plasma-swd-{BIN_SHA[:12]}"
KEEP={"0.12.0-5088db4c9154":"20690fc154bf7c76ad2ce46a33bee2e3038623a2f951c698425be13133f3b640",
      "0.12.0-9ea7f3d647c8":"70d638eb1fce16627188b7e73935d81f2fa34685ef206550c7b5d0e7af6a3513"}
ENTRY=("/usr/local/libexec/plasma/z2-path2-root-entry","7849ff02842c66f2242ade2b93f3707b84cd679720ea993b00ffa9a255990822")
def H(b): return hashlib.sha256(b).hexdigest()
def F(p): return H(open(p,"rb").read())
out={"dest":DEST}
def need(c,m):
    if not c:
        out["result"]="DENIED:"+m; print("Z2JSON="+json.dumps(out)); raise SystemExit(1)
need(os.geteuid()==0,"ROOT")
need({k:F(f"{BASE}/{k}/bin/openocd") for k in KEEP}==KEEP,"EXISTING_OPENOCD_CHANGED")
need(F(ENTRY[0])==ENTRY[1],"ROOT_ENTRY_CHANGED")
need(not os.path.lexists(DEST),"DEST_EXISTS")
UP="/root/.plasma-swd-upload/payload.tar.xz"  # written by upload.py
data=open(UP,"rb").read()
need(H(data)==TAR_SHA,"PAYLOAD_SHA_MISMATCH")
stage=tempfile.mkdtemp(prefix=".plasma-swd-stage-",dir=BASE)
try:
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:xz") as t:
        for m in t.getmembers():
            need(not m.name.startswith("/") and ".." not in m.name.split("/") and (m.isfile() or m.isdir()),"TAR_MEMBER_UNSAFE:"+m.name[:60])
        t.extractall(stage+"/x")
    x=stage+"/x"
    need(F(x+"/openocd")==BIN_SHA,"BIN_SHA_MISMATCH")
    need(F(x+"/plasma_swd_site_admission.py")==ADM_SHA,"ADMISSION_SHA_MISMATCH")
    elf=open(x+"/openocd","rb").read(20)
    need(elf[:4]==b"\x7fELF" and elf[4]==1 and elf[5]==1 and int.from_bytes(elf[18:20],"little")==40,"NOT_ELF32_ARM_LE")
    os.makedirs(stage+"/d/bin"); os.makedirs(stage+"/d/share/openocd"); os.makedirs(stage+"/d/libexec"); os.makedirs(stage+"/d/evidence")
    shutil.copy2(x+"/openocd",stage+"/d/bin/openocd")
    shutil.copytree(x+"/tcl",stage+"/d/share/openocd/scripts")
    shutil.copy2(x+"/plasma_swd_site_admission.py",stage+"/d/libexec/plasma_swd_site_admission.py")
    for n in os.listdir(x):
        if n.endswith((".log",".txt",".json",".sha256")): shutil.copy2(f"{x}/{n}",f"{stage}/d/evidence/{n}")
    rt={"schema":"plasma.openocd.runtime.v1","runtime_id":os.path.basename(DEST),"architecture":"armv7l",
        "openocd_source_commit":"5088db4c9154ca833c6d558381074b33672e127a","plasma_source_sha":PLASMA_SHA,
        "ci_run_id":RUN_ID,"transfer_payload_tar_xz_sha256":TAR_SHA,"deployment_route":"B_ENGINEERING_SSH","binary_sha256":BIN_SHA,"site_admission_sha256":ADM_SHA,
        "binary":DEST+"/bin/openocd","scripts_root":DEST+"/share/openocd/scripts",
        "hardware_runtime_ready":False,"qualification":"ENGINEERING_CANDIDATE_NOT_PRODUCTION",
        "starts_openocd_service":False}
    open(stage+"/d/runtime.json","w").write(json.dumps(rt,indent=1,sort_keys=True)+"\n")
    for r,ds,fs in os.walk(stage+"/d"):
        os.chown(r,0,0); os.chmod(r,0o755)
        for f in fs:
            p=os.path.join(r,f); os.chown(p,0,0); os.chmod(p,0o755 if p.endswith("/bin/openocd") else 0o644)
    os.rename(stage+"/d",DEST)
finally:
    shutil.rmtree(stage,ignore_errors=True)
need({k:F(f"{BASE}/{k}/bin/openocd") for k in KEEP}==KEEP,"EXISTING_OPENOCD_CHANGED_AFTER")
B=DEST+"/bin/openocd"; S=DEST+"/share/openocd/scripts"
NOPORT=["-c","gdb port disabled","-c","tcl port disabled","-c","telnet port disabled"]
def run(args,user=None,t=20):
    pre=["setpriv","--reuid=nobody","--regid=nogroup","--clear-groups"] if user else []
    r=subprocess.run(pre+[B,"-s",S]+args,capture_output=True,text=True,timeout=t)
    return {"rc":r.returncode,"out":(r.stdout+r.stderr)[-1500:]}
out["installed_bin_sha256"]=F(B)
out["ldd"]=subprocess.run(["ldd",B],capture_output=True,text=True).stdout
out["version"]=run(["--version"])
out["adapter_list"]=run(["-c","adapter list","-c","shutdown"])
need("plasma_swd" in out["adapter_list"]["out"],"PLASMA_SWD_NOT_LISTED")
rec="/run/plasma-z2-swd05/swd-site1-admission"
need(not os.path.exists(rec),"STALE_RECORD_PRESENT")
base=["-c","adapter driver plasma_swd"]+NOPORT
out["neg_no_site"]=run(base+["-c","transport select swd","-c","init","-c","shutdown"])
out["neg_site1_no_record"]=run(base+["-c","plasma_swd site 1","-c","transport select swd","-c","init","-c","shutdown"])
out["neg_nonroot"]=run(base+["-c","plasma_swd site 1","-c","transport select swd","-c","init","-c","shutdown"],user=True)
out["neg_site3"]=run(base+["-c","plasma_swd site 3","-c","transport select swd","-c","init","-c","shutdown"])
checks={"neg_no_site":"PS_OWNER_SITE_NOT_SELECTED","neg_site1_no_record":"PS_OWNER_ADMISSION_RECORD_INVALID","neg_nonroot":"PS_OWNER_ROOT_REQUIRED","neg_site3":""}
out["negatives"]={k:(out[k]["rc"]!=0 and v in out[k]["out"]) for k,v in checks.items()}
out["result"]="DEPLOYED_AND_UNADMITTED_DENIED" if all(out["negatives"].values()) else "DEPLOYED_NEGATIVE_CHECK_FAILED"
print("Z2JSON="+json.dumps(out))

os.remove(UP)

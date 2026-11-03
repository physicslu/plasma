# Root on Z2, READ-ONLY: #1252 contract state (privileged code root, Root journal,
# Root Entry, Owner Operation Authorization module, retired Bundle Authority v2
# leftover, OpenOCD installs, owner dir). No writes, no MMIO.
import hashlib, json, os, stat, subprocess
def sha(p):
    try: return hashlib.sha256(open(p,'rb').read()).hexdigest()
    except Exception as e: return "ERR:"+type(e).__name__
def perm(p):
    try: s=os.lstat(p); return [s.st_uid, oct(stat.S_IMODE(s.st_mode))]
    except Exception as e: return "ERR:"+type(e).__name__
CODE="/opt/plasma/privileged/fpga-root"; J="/var/lib/plasma-privileged/fpga-deployment-state.json"
LEGACY_AUTH="/etc/plasma/ppu-bundle-authority.json"; PY="/opt/plasma/python/3.12.13/bin/python3"
st={}
try: st=json.load(open(J))
except Exception as e: st={"err":type(e).__name__}
# Retired per-Bundle allowlist: report only presence/schema of a leftover file.
try:
    a=json.load(open(LEGACY_AUTH)); legacy={"present":True,"schema":a.get("schema")}
except FileNotFoundError: legacy={"present":False}
except Exception as e: legacy={"present":True,"err":type(e).__name__}
v=subprocess.run([PY,"-I","-B","/opt/plasma/bootstrap/ppu_privileged_source.py"],capture_output=True,text=True)
ps=subprocess.run(["ps","-eo","pid,comm,args"],capture_output=True,text=True).stdout
d={"boot_id":open("/proc/sys/kernel/random/boot_id").read().strip(),
 "manager":open("/sys/class/fpga_manager/fpga0/state").read().strip(),
 "journal":st,"journal_sha":sha(J),
 "journal_chain":{p:perm(p) for p in ("/","/var","/var/lib","/var/lib/plasma-privileged",J)},
 "entry_sha":sha("/usr/local/libexec/plasma/z2-path2-root-entry"),
 "code_manifest_sha":sha(CODE+"/.plasma-privileged-code.json"),
 "code_verify":{"rc":v.returncode,"out":v.stdout.strip()[-400:],"err":v.stderr.strip()[-300:]},
 "code":{p:sha(CODE+"/"+p) for p in ["pl/hil/fpga_image_admission.py","pl/hil/fpga_image_guard.py","pl/hil/fpga_image_root.py","software/python/plasma_interfaces/__init__.py","software/python/plasma_interfaces/linux_mmio.py"]},
 "owner_authorization_module_sha":sha("/opt/plasma/bootstrap/ppu_owner_authorization.py"),
 "legacy_bundle_authority_v2":legacy,
 "image_manifest_sha":sha("/lib/firmware/plasma-image-manifest.json"),
 "openocd_dirs":sorted(os.listdir("/opt/plasma/programming-engines/openocd")),
 "openocd_sha":{p:sha(f"/opt/plasma/programming-engines/openocd/{p}/bin/openocd") for p in os.listdir("/opt/plasma/programming-engines/openocd")},
 "openocd_procs":[l for l in ps.splitlines() if "openocd" in l and "python3" not in l],
 "owner_dir":sorted(os.listdir("/run/plasma-z2-swd05")) if os.path.isdir("/run/plasma-z2-swd05") else None,
 "electrical_dir":os.path.isdir("/root/plasma-swd-electrical"),
 "native_py":os.path.exists(PY),
 "lock":os.path.exists("/run/lock/plasma-mmio.lock"),
 "uname":os.uname().machine}
print("Z2JSON="+json.dumps(d))

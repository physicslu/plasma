import hashlib, json, os, subprocess
def sha(p):
    try: return hashlib.sha256(open(p,'rb').read()).hexdigest()
    except Exception as e: return "ERR:"+type(e).__name__
R="/root/plasma-path2-approved"
st={}
try: st=json.load(open(R+"/.plasma-fpga-image-deployment-state.json"))
except Exception as e: st={"err":type(e).__name__}
ps=subprocess.run(["ps","-eo","pid,comm,args"],capture_output=True,text=True).stdout
d={"boot_id":open("/proc/sys/kernel/random/boot_id").read().strip(),
 "manager":open("/sys/class/fpga_manager/fpga0/state").read().strip(),
 "journal":st,
 "pin":open(R+"/.plasma-path2-source-commit").read().strip(),
 "entry_sha":sha("/usr/local/libexec/plasma/z2-path2-root-entry"),
 "tree":{p:sha(R+"/"+p) for p in ["pl/hil/fpga_image_admission.py","pl/hil/fpga_image_guard.py","pl/hil/fpga_image_root.py","software/python/plasma_interfaces/linux_mmio.py",".plasma-path2-source-commit"]},
 "openocd_dirs":sorted(os.listdir("/opt/plasma/programming-engines/openocd")),
 "openocd_sha":{p:sha(f"/opt/plasma/programming-engines/openocd/{p}/bin/openocd") for p in os.listdir("/opt/plasma/programming-engines/openocd")},
 "openocd_procs":[l for l in ps.splitlines() if "openocd" in l and "python3" not in l],
 "owner_dir":sorted(os.listdir("/run/plasma-z2-swd05")) if os.path.isdir("/run/plasma-z2-swd05") else None,
 "electrical_dir":os.path.isdir("/root/plasma-swd-electrical"),
 "native_py":os.path.exists("/opt/plasma/python/3.12.13/bin/python3"),
 "lock":os.path.exists("/run/lock/plasma-mmio.lock"),
 "uname":os.uname().machine}
print("Z2JSON="+json.dumps(d))

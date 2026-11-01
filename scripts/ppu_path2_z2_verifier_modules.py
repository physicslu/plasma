#!/usr/bin/env python3
"""Read-only inventory of loaded Z2 Bootstrap verifier module provenance."""
import argparse,importlib.util,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import ast,hashlib,json,os,pathlib
pid=32533
out={"pid":pid,"listener_owned":False,"entrypoint_verified":False,"modules":[],"verifier":"NOT_ATTESTED"}
try:
 p=pathlib.Path("/proc")/str(pid)
 sockets=set()
 for name in ("/proc/net/tcp","/proc/net/tcp6"):
  try: lines=pathlib.Path(name).read_text().splitlines()[1:]
  except OSError: continue
  for line in lines:
   f=line.split()
   if len(f)>=10 and f[3]=="0A" and int(f[1].rsplit(":",1)[1],16)==18081:
    sockets.add("socket:["+f[9]+"]")
 out["listener_owned"]=any(os.readlink(fd) in sockets for fd in (p/"fd").iterdir())
 if not out["listener_owned"]: raise RuntimeError("PID_CHANGED")
 argv=[x.decode("utf8","replace") for x in (p/"cmdline").read_bytes().split(b"\0") if x]
 cwd=pathlib.Path(os.readlink(p/"cwd"))
 paths=[]
 for arg in argv[1:]:
  if arg in ("-m","-c"): break
  if arg.endswith(".py") and not arg.startswith("-"):
   candidate=pathlib.Path(arg)
   if not candidate.is_absolute(): candidate=cwd/candidate
   candidate=candidate.resolve(strict=True)
   if candidate.name=="ppu-bootstrap-service.py" and candidate.is_file():
    paths.append(candidate)
 if len(paths)!=1: raise RuntimeError("ENTRYPOINT_UNRESOLVED")
 entry=paths[0]
 data=entry.read_bytes()
 if hashlib.sha256(data).hexdigest()!="4a02f1ee23dd347fd25dd0a4b8da2f3312f3dc28fd745f12dc3a567cbdd18ca9":
  raise RuntimeError("ENTRYPOINT_SHA_CHANGED")
 out["entrypoint_verified"]=True
 # Inspect only explicitly referenced, adjacent Python source modules; no imports executed.
 tree=ast.parse(data.decode("utf8"))
 names=set()
 for node in ast.walk(tree):
  if isinstance(node,ast.Import):
   names.update(a.name.split(".")[0] for a in node.names)
  elif isinstance(node,ast.ImportFrom) and node.module:
   names.add(node.module.split(".")[0])
 names.update(("ppu_unified_deployment","ppu_deploy_api","ppu_package_contract"))
 for name in sorted(names):
  if not name.startswith(("ppu","plasma")): continue
  for base in (entry.parent,entry.parent/"scripts",cwd,cwd/"scripts"):
   path=base/(name+".py")
   try:
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024: continue
    raw=path.read_bytes()
    out["modules"].append({"name":name,"sha256":hashlib.sha256(raw).hexdigest(),
     "bytes":len(raw),"bundle_v3_literal":b"plasma.ppu.bundle.v3" in raw,
     "bundle_v2_literal":b"plasma.ppu.bundle.v2" in raw})
    break
   except OSError: continue
 out["verifier"]="SOURCE_CANDIDATES_ONLY"
except Exception as e: out["error_type"]=type(e).__name__
print("PLASMA_Z2_VERIFIER_MODULES_JSON="+json.dumps(out,sort_keys=True))
'''
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--host",required=True);p.add_argument("--source-sha",required=True)
 a=p.parse_args()
 out={"schema":"plasma.ppu.z2-verifier-modules.v1","status":"NOT_RUN","b2":"NOT_QUALIFIED"}
 try:
  actual=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True,timeout=5).stdout.strip()
  if not re.fullmatch(r"[0-9a-f]{40}",a.source_sha) or actual!=a.source_sha: raise RuntimeError("SOURCE_SHA_MISMATCH")
  spec=importlib.util.spec_from_file_location("ppu_modules_common",ROOT/"scripts/ppu_path2_hardware_baseline.py")
  m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
  m._private_ipv4(a.host)
  hs=importlib.util.spec_from_file_location("ppu_modules_ssh",ROOT/"scripts/plasma_wordport_program.py")
  helper=importlib.util.module_from_spec(hs);sys.modules[hs.name]=helper;hs.loader.exec_module(helper)
  credentials,known_hosts=helper.z2_login_credentials(Path.home())
  if credentials.get("ssh_host")!=a.host: raise RuntimeError("SSH_HOST_PIN_MISMATCH")
  rc,raw=helper.password_ssh_z2(["python3","-I","-c",REMOTE],credentials,known_hosts,timeout=45)
  if rc!=0: raise RuntimeError("REMOTE_INVENTORY_UNAVAILABLE")
  matches=re.findall(r"PLASMA_Z2_VERIFIER_MODULES_JSON=(\{[^\n]+\})",raw)
  if len(matches)!=1: raise RuntimeError("REMOTE_INVENTORY_UNAVAILABLE")
  out.update({"status":"READ_ONLY_COMPLETE","inventory":json.loads(matches[0])});code=0
 except Exception as e:
  out.update({"status":"BLOCKED","error_type":type(e).__name__});code=2
 print("PLASMA_PPU_Z2_VERIFIER_MODULES_JSON="+json.dumps(out,sort_keys=True))
 return code
if __name__=="__main__":raise SystemExit(main())

"""Upload one file to Z2 root-private staging via the pinned SSH/sudo helper,
in base64 chunks at explicit offsets; final SHA256 verified on Z2."""
import base64, hashlib, importlib.util, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("wp", REPO / "scripts/plasma_wordport_program.py")
wp = importlib.util.module_from_spec(spec); sys.modules["wp"] = wp; spec.loader.exec_module(wp)
src = Path(sys.argv[1]); data = src.read_bytes(); digest = hashlib.sha256(data).hexdigest()
creds, hosts = wp.z2_login_credentials(Path.home())
assert creds["ssh_host"] == "192.168.2.99"
DST = "/root/.plasma-swd-upload/payload.tar.xz"
CH = 66000
def z2(code):
    rc, out = wp.password_ssh_z2(["python3", "-I", "-B", "-c", code], creds, hosts, timeout=90)
    return rc, out
rc, out = z2(f"import os\nos.makedirs('/root/.plasma-swd-upload',mode=0o700,exist_ok=True)\nos.chmod('/root/.plasma-swd-upload',0o700)\nopen('{DST}','wb').close()\nos.chmod('{DST}',0o600)\nprint('INIT_OK')")
assert rc == 0 and "INIT_OK" in out, out[-500:]
t0 = time.time()
for off in range(0, len(data), CH):
    b = base64.b64encode(data[off:off+CH]).decode()
    code = (f"import base64,os\nf=open('{DST}','r+b')\nf.seek(0,2)\nassert f.tell()=={off},f.tell()\n"
            f"f.write(base64.b64decode('{b}'))\nf.close()\nprint('CHUNK_OK',{off})")
    for attempt in range(3):
        rc, out = z2(code)
        if rc == 0 and f"CHUNK_OK {off}" in out: break
    else:
        raise SystemExit(f"CHUNK_FAIL {off}: {out[-400:]}")
    print(f"{off+len(data[off:off+CH])}/{len(data)} {time.time()-t0:.0f}s", flush=True)
rc, out = z2(f"import hashlib\nprint('Z2SHA',hashlib.sha256(open('{DST}','rb').read()).hexdigest())")
print(out[-200:]); assert f"Z2SHA {digest}" in out, "SHA_MISMATCH"
print("UPLOAD_VERIFIED", digest)

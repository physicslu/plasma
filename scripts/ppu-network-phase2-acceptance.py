#!/usr/bin/env python3
"""One-command packaged ARMv7 acceptance for PPU Network Phase 2.

Docker owns a stable lab-only control address on the PPU namespace. A privileged
helper separately owns the management address under test on the same eth0. This
prevents Docker IPAM from owning the DUT property that Phase 2 mutates while
still exercising real Linux IPv4 add/delete, reconnect, commit, and rollback.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
BINFMT_IMAGE = "docker.io/tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0"
DEFAULT_WORK_REL = Path(".work/ppu-network-phase2-acceptance")
DEFAULT_REPORT_REL = Path(".work/reports/ppu-network-phase2-acceptance.json")
LAB_SUBNET = "192.168.77.0/24"
LAB_GATEWAY = "192.168.77.1"
INITIAL_IP = "192.168.77.10"
COMMITTED_IP = "192.168.77.21"
ROLLBACK_CANDIDATE_IP = "192.168.77.22"
PROBE_IP = "192.168.77.30"
PPU_CONTROL_IP = "192.168.77.40"
PPU_ID = "swpc-armv7-phase2"
PPU_PORT = 18080
ROLLBACK_TIMEOUT_S = 2
RESULT_MARKER = "PLASMA_PPU_NETWORK_PHASE2_RESULT="
CAP_NET_ADMIN = 12
MAX_HELPER_REQUEST = 1024 * 1024
NETLINK_ROUTE = 0
NLMSG_ERROR = 2
NLM_F_REQUEST = 0x0001
NLM_F_ACK = 0x0004
NLM_F_REPLACE = 0x0100
NLM_F_CREATE = 0x0400
RTM_NEWADDR = 20
RTM_DELADDR = 21
IFA_ADDRESS = 1
IFA_LOCAL = 2
RT_SCOPE_UNIVERSE = 0


class AcceptanceError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(command: Sequence[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), cwd=cwd, text=True, capture_output=True, check=check)


def _host_python(repo: Path) -> Path:
    venv = repo / "software/python/.venv/bin/python"
    if venv.is_file():
        return venv
    if sys.version_info < (3, 11):
        raise AcceptanceError(f"Python >=3.11 required, got {platform.python_version()}")
    return Path(sys.executable).resolve()


def _git_sha(repo: Path) -> str:
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    if len(sha) != 40:
        raise AcceptanceError(f"unexpected git SHA: {sha!r}")
    return sha


def _product_version(repo: Path) -> str:
    payload = json.loads((repo / "release/product.json").read_text(encoding="utf-8"))
    version = payload.get("product_version")
    if not isinstance(version, str) or not version:
        raise AcceptanceError("release/product.json missing product_version")
    return version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _docker_preflight() -> bool:
    if shutil.which("docker") is None:
        raise AcceptanceError("docker is not available on PATH")
    probe = ["docker", "run", "--rm", "--platform", "linux/arm/v7", ARM_IMAGE, "python3", "-c", "import platform; print(platform.machine())"]
    installed = False
    result = _run(probe, check=False)
    if result.returncode != 0:
        install = _run(["docker", "run", "--privileged", "--rm", BINFMT_IMAGE, "--install", "arm"], check=False)
        if install.returncode != 0:
            raise AcceptanceError("ARM binfmt installation failed: " + install.stdout + install.stderr)
        installed = True
        result = _run(probe, check=False)
    if result.returncode != 0 or result.stdout.strip().lower() not in {"armv7", "armv7l"}:
        raise AcceptanceError("ARMv7 Docker preflight failed: " + result.stdout + result.stderr)
    return installed


def _build_release(repo: Path, work: Path, python: Path, git_sha: str, version: str) -> tuple[Path, Path, str]:
    runtime = work / "build-runtime"
    release = work / "release"
    extracted = work / "extracted"
    _run([str(python), "scripts/ppu-runtime.py", "build", "--output-dir", str(runtime)], cwd=repo)
    _run([str(python), "scripts/ppu-runtime.py", "validate", str(runtime)], cwd=repo)
    _run([str(python), "scripts/ppu-release.py", "--runtime-dir", str(runtime), "--output-dir", str(release), "--git-sha", git_sha], cwd=repo)
    archive = release / f"plasma-ppu-{version}-linux-armv7l.tar.gz"
    sidecar = Path(str(archive) + ".sha256")
    if not archive.is_file() or not sidecar.is_file():
        raise AcceptanceError("canonical ARMv7 release was not produced")
    parts = sidecar.read_text(encoding="utf-8").strip().split()
    actual_sha = _sha256(archive)
    if len(parts) != 2 or parts[0] != actual_sha or parts[1] != archive.name:
        raise AcceptanceError("release SHA-256 sidecar mismatch")
    _run([
        str(python), "scripts/product-release.py", "verify", str(archive), "--sidecar", str(sidecar),
        "--extract-to", str(extracted), "--expect-role", "ppu", "--expect-platform", "linux",
        "--expect-architecture", "armv7l", "--expect-version", version,
    ], cwd=repo)
    clean_runtime = extracted / "plasma-release/runtime"
    _run([str(python), "scripts/ppu-runtime.py", "validate", str(clean_runtime)], cwd=repo)
    return clean_runtime, archive, actual_sha


def _write_ppu_config(work: Path) -> None:
    (work / "ppu.yaml").write_text(
        "ppu:\n"
        f"  id: {PPU_ID}\n"
        "  facility_id: swpc-qemu\n"
        "  model: qemu-armv7-phase2\n"
        "  display_name: Plasma Phase 2 ARMv7 Lab\n\n"
        "server:\n"
        "  host: 127.0.0.1\n"
        "  port: 9900\n"
        "  max_supported_sites: 8\n"
        "  max_concurrent_jobs: 1\n"
        "  max_queue_depth_per_site: 16\n"
        "  output_root: /work/server-output\n"
        "  log_root: /work/logs\n"
        "  max_metadata_bytes: 65536\n"
        "  max_map_bytes: 1048576\n"
        "  max_binary_bytes: 67108864\n\n"
        "sites: []\n",
        encoding="utf-8",
    )


def _docker_rm(name: str) -> None:
    _run(["docker", "rm", "-f", name], check=False)


def _docker_network_rm(name: str) -> None:
    _run(["docker", "network", "rm", name], check=False)


def _cap_eff(container: str) -> int:
    result = _run(["docker", "exec", container, "cat", "/proc/1/status"])
    for line in result.stdout.splitlines():
        if line.startswith("CapEff:"):
            return int(line.split()[1], 16)
    raise AcceptanceError(f"cannot read CapEff from {container}")


def _has_cap(value: int, cap: int) -> bool:
    return bool(value & (1 << cap))


PROBE_CODE = r'''
import json, sys, urllib.error, urllib.request
url, method, body_json = sys.argv[1:4]
data = None if body_json == "" else body_json.encode()
headers = {"Accept":"application/json"}
if data is not None: headers["Content-Type"] = "application/json"
req = urllib.request.Request(url, data=data, headers=headers, method=method)
try:
    with urllib.request.urlopen(req, timeout=1.2) as r:
        raw=r.read(); payload=json.loads(raw) if raw else None
        print(json.dumps({"reachable":True,"status":r.status,"payload":payload}, sort_keys=True))
except urllib.error.HTTPError as e:
    raw=e.read()
    try: payload=json.loads(raw) if raw else None
    except Exception: payload={"raw":raw.decode("utf-8","replace")}
    print(json.dumps({"reachable":True,"status":e.code,"payload":payload}, sort_keys=True))
except Exception as e:
    print(json.dumps({"reachable":False,"error":type(e).__name__+": "+str(e)}, sort_keys=True))
'''


def _probe(container: str, ip: str, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body_json = json.dumps(dict(body), separators=(",", ":"), sort_keys=True) if body is not None else ""
    result = _run(["docker", "exec", container, "python3", "-c", PROBE_CODE, f"http://{ip}:{PPU_PORT}{path}", method, body_json], check=False)
    if result.returncode != 0:
        raise AcceptanceError("probe process failed: " + result.stdout + result.stderr)
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"invalid probe output: {result.stdout!r}") from exc
    if not isinstance(payload, dict):
        raise AcceptanceError("probe output is not an object")
    return payload


def _expect_json(container: str, ip: str, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None, status: int = 200) -> dict[str, Any]:
    result = _probe(container, ip, path, method=method, body=body)
    if result.get("reachable") is not True or result.get("status") != status or not isinstance(result.get("payload"), dict):
        raise AcceptanceError(f"unexpected HTTP result for {ip}{path}: {result!r}")
    return result["payload"]


def _wait_reachable(container: str, ip: str, path: str = "/api/node", timeout_s: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = _probe(container, ip, path)
        if last.get("reachable") is True and last.get("status") == 200 and isinstance(last.get("payload"), dict):
            return last["payload"]
        time.sleep(0.1)
    raise AcceptanceError(f"endpoint {ip}{path} did not become reachable: {last!r}")


def _wait_unreachable(container: str, ip: str, path: str = "/api/node", timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _probe(container, ip, path).get("reachable") is not True:
            return
        time.sleep(0.1)
    raise AcceptanceError(f"endpoint {ip}{path} remained reachable")


def _wait_activation_state(container: str, ip: str, state: str, timeout_s: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_probe = None
    last_activation = None
    while time.monotonic() < deadline:
        last_probe = _probe(container, ip, "/api/settings/ppu-network/activation")
        if last_probe.get("reachable") is True and last_probe.get("status") == 200 and isinstance(last_probe.get("payload"), dict):
            activation = last_probe["payload"].get("activation")
            if isinstance(activation, dict):
                last_activation = activation
                if activation.get("state") == state:
                    return activation
        time.sleep(0.1)
    raise AcceptanceError(f"activation did not reach {state}: activation={last_activation!r} probe={last_probe!r}")


def _node_ppu_id(payload: Mapping[str, Any]) -> str:
    ppu = payload.get("ppu")
    ppu_id = ppu.get("ppu_id") if isinstance(ppu, dict) else None
    if not isinstance(ppu_id, str) or not ppu_id:
        raise AcceptanceError("/api/node missing canonical ppu_id")
    return ppu_id


def _desired(address: str) -> dict[str, Any]:
    return {"mode":"static","address":address,"prefix_length":24,"gateway":LAB_GATEWAY,"dns_servers":[LAB_GATEWAY]}


def _host_mode(args: argparse.Namespace) -> int:
    repo = _repo_root(); python = _host_python(repo); git_sha = _git_sha(repo); version = _product_version(repo)
    work = (repo / args.work_dir).resolve() if not args.work_dir.is_absolute() else args.work_dir.resolve()
    report = (repo / args.report).resolve() if not args.report.is_absolute() else args.report.resolve()
    if work.exists(): shutil.rmtree(work)
    work.mkdir(parents=True); report.parent.mkdir(parents=True, exist_ok=True)
    container_work = work / "container-work"; container_work.mkdir(); container_work.chmod(0o777)
    for directory in (container_work / "server-output", container_work / "gateway-output", container_work / "logs"):
        directory.mkdir(); directory.chmod(0o777)
    _write_ppu_config(container_work)
    installed_binfmt = _docker_preflight()
    runtime, archive, release_sha = _build_release(repo, work, python, git_sha, version)
    suffix = f"{os.getpid()}-{int(time.time())}"
    network = f"plasma-phase2-{suffix}"; ppu = f"plasma-phase2-ppu-{suffix}"; helper = f"plasma-phase2-helper-{suffix}"; probe = f"plasma-phase2-probe-{suffix}"
    script = Path(__file__).resolve(); checks: dict[str, str] = {}
    try:
        _run(["docker","network","create","--subnet",LAB_SUBNET,"--gateway",LAB_GATEWAY,network]); checks["isolated_network"]="PASS"
        _run(["docker","run","-d","--name",ppu,"--platform","linux/arm/v7","--network",network,"--ip",PPU_CONTROL_IP,"--cap-drop","ALL","--security-opt","no-new-privileges:true","-v",f"{runtime}:/runtime:ro","-v",f"{container_work}:/work","-v",f"{script}:/acceptance.py:ro",ARM_IMAGE,"python3","/acceptance.py","--inside-ppu","--runtime-dir","/runtime","--work-dir","/work"])
        _run(["docker","run","-d","--name",helper,"--platform","linux/arm/v7","--network",f"container:{ppu}","--cap-drop","ALL","--cap-add","NET_ADMIN","--security-opt","no-new-privileges:true","-v",f"{container_work}:/work","-v",f"{script}:/acceptance.py:ro",ARM_IMAGE,"python3","/acceptance.py","--helper","--helper-socket","/work/network-helper.sock","--managed-initial-address",INITIAL_IP,"--managed-prefix","24"])
        _run(["docker","run","-d","--name",probe,"--platform","linux/arm/v7","--network",network,"--ip",PROBE_IP,"--cap-drop","ALL","--security-opt","no-new-privileges:true",ARM_IMAGE,"python3","-c","import time; time.sleep(3600)"])
        helper_socket = container_work / "network-helper.sock"; deadline=time.monotonic()+8
        while time.monotonic()<deadline and not helper_socket.exists(): time.sleep(0.05)
        if not helper_socket.exists(): raise AcceptanceError("privileged helper Unix socket did not appear")
        checks["helper_socket_ready"]="PASS"
        if _has_cap(_cap_eff(ppu), CAP_NET_ADMIN): raise AcceptanceError("Gateway unexpectedly has CAP_NET_ADMIN")
        if not _has_cap(_cap_eff(helper), CAP_NET_ADMIN): raise AcceptanceError("helper missing CAP_NET_ADMIN")
        checks["gateway_no_net_admin"]="PASS"; checks["helper_has_net_admin"]="PASS"
        initial_node=_wait_reachable(probe, INITIAL_IP); initial_ppu_id=_node_ppu_id(initial_node)
        if initial_ppu_id != PPU_ID: raise AcceptanceError(f"unexpected initial ppu_id: {initial_ppu_id}")
        checks["initial_managed_endpoint"]="PASS"
        # The Docker-owned control address is intentionally outside the DUT management transaction.
        if _node_ppu_id(_wait_reachable(probe, PPU_CONTROL_IP)) != initial_ppu_id: raise AcceptanceError("lab control endpoint identity mismatch")
        checks["docker_control_plane_separated"]="PASS"
        net=_expect_json(probe, INITIAL_IP, "/api/settings/ppu-network")
        activation=net.get("activation")
        if not isinstance(activation,dict) or activation.get("supported") is not True: raise AcceptanceError("Phase 2 activation not supported")
        desired2=_expect_json(probe,INITIAL_IP,"/api/settings/ppu-network",method="POST",body=_desired(COMMITTED_IP)); rev2=desired2["ppu_network_settings"]["revision"]
        scheduled=_expect_json(probe,INITIAL_IP,"/api/settings/ppu-network/activation",method="POST",body={"action":"apply","expected_revision":rev2,"expected_ppu_id":initial_ppu_id,"rollback_timeout_s":ROLLBACK_TIMEOUT_S},status=202)
        activation_id=scheduled["activation"]["activation_id"]; checks["ack_before_mutation"]="PASS"
        candidate=_wait_reachable(probe,COMMITTED_IP); candidate_id=_node_ppu_id(candidate)
        if candidate_id != initial_ppu_id: raise AcceptanceError("candidate ppu_id changed")
        _wait_unreachable(probe,INITIAL_IP); waiting=_wait_activation_state(probe,COMMITTED_IP,"applied_waiting_commit")
        if waiting.get("revision") != rev2: raise AcceptanceError("candidate revision mismatch")
        checks["candidate_reconnect"]="PASS"; checks["same_ppu_id_revalidation"]="PASS"; checks["old_endpoint_removed"]="PASS"
        committed=_expect_json(probe,COMMITTED_IP,f"/api/settings/ppu-network/activation/{activation_id}/commit",method="POST",body={"expected_revision":rev2,"expected_ppu_id":candidate_id})["activation"]
        if committed.get("state") != "committed" or committed.get("committed_revision") != rev2: raise AcceptanceError("commit failed")
        time.sleep(ROLLBACK_TIMEOUT_S+0.4); _wait_reachable(probe,COMMITTED_IP); _wait_unreachable(probe,INITIAL_IP,timeout_s=1.5)
        checks["explicit_commit"]="PASS"; checks["commit_survives_deadline"]="PASS"
        desired3=_expect_json(probe,COMMITTED_IP,"/api/settings/ppu-network",method="POST",body=_desired(ROLLBACK_CANDIDATE_IP)); rev3=desired3["ppu_network_settings"]["revision"]
        second=_expect_json(probe,COMMITTED_IP,"/api/settings/ppu-network/activation",method="POST",body={"action":"apply","expected_revision":rev3,"expected_ppu_id":initial_ppu_id,"rollback_timeout_s":ROLLBACK_TIMEOUT_S},status=202)
        if second["activation"]["activation_id"] == activation_id: raise AcceptanceError("activation_id reused")
        if _node_ppu_id(_wait_reachable(probe,ROLLBACK_CANDIDATE_IP)) != initial_ppu_id: raise AcceptanceError("second candidate identity changed")
        _wait_unreachable(probe,COMMITTED_IP); _wait_activation_state(probe,ROLLBACK_CANDIDATE_IP,"applied_waiting_commit"); checks["second_candidate_reconnect"]="PASS"
        if _node_ppu_id(_wait_reachable(probe,COMMITTED_IP,timeout_s=ROLLBACK_TIMEOUT_S+5)) != initial_ppu_id: raise AcceptanceError("rollback identity changed")
        _wait_unreachable(probe,ROLLBACK_CANDIDATE_IP,timeout_s=2)
        rolled=_wait_activation_state(probe,COMMITTED_IP,"rolled_back")
        if rolled.get("reason") != "commit_deadline_expired" or rolled.get("committed_revision") != rev2: raise AcceptanceError(f"rollback state invalid: {rolled!r}")
        final=_expect_json(probe,COMMITTED_IP,"/api/settings/ppu-network")["ppu_network_settings"]
        if final.get("revision") != rev3 or final.get("address") != ROLLBACK_CANDIDATE_IP: raise AcceptanceError("rollback incorrectly rewrote desired settings")
        checks["automatic_rollback"]="PASS"; checks["committed_revision_preserved"]="PASS"; checks["desired_revision_preserved"]="PASS"
        if not (container_work/"gateway-output"/"ppu-network-activation.json").is_file(): raise AcceptanceError("activation journal missing")
        checks["durable_journal"]="PASS"
        result={"overall_result":"PASS","transaction_result":"PASS","evidence_level":"swpc-qemu-armv7-isolated-static-ipv4","git_sha":git_sha,"product_version":version,"architecture":"armv7l","release_artifact":archive.name,"release_sha256":release_sha,"arm_binfmt_installed_now":installed_binfmt,"docker_control_ipv4":PPU_CONTROL_IP,"initial_ipv4":INITIAL_IP,"committed_ipv4":COMMITTED_IP,"rollback_candidate_ipv4":ROLLBACK_CANDIDATE_IP,"ppu_id":initial_ppu_id,"committed_revision":rev2,"desired_revision_after_rollback":rev3,"checks":checks,"actual_network_mutation":"helper-owned-management-ipv4-on-eth0","privilege_separation":{"gateway_cap_net_admin":False,"helper_cap_net_admin":True},"not_claimed":["PYNQ-Z2 hardware","final Z2 Linux network-manager backend","primary-address replacement under Docker IPAM","DHCP activation","DNS mutation","default-route mutation","boot-time network persistence","Manager production integration","PS-to-PL","Site I/O","real IC programming"]}
        report.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8"); _print_summary(result,report); return 0
    finally:
        for name in (helper,probe,ppu): _docker_rm(name)
        _docker_network_rm(network)


def _print_summary(result: Mapping[str, Any], report: Path) -> None:
    print("="*72); print("Plasma PPU Network Phase 2 Acceptance"); print("="*72)
    print(f"Git SHA                    : {result['git_sha']}")
    print(f"Architecture               : {result['architecture']}")
    print(f"Docker control IPv4        : {result['docker_control_ipv4']}")
    for name,value in result["checks"].items(): print(f"[{value}] {name.replace('_',' ').title()}")
    print(f"PPU ID                     : {result['ppu_id']}")
    print(f"Initial IPv4               : {result['initial_ipv4']}")
    print(f"Committed IPv4             : {result['committed_ipv4']}")
    print(f"Rollback Candidate IPv4    : {result['rollback_candidate_ipv4']}")
    print("-"*72); print("PHASE 2 TRANSACTION RESULT : PASS"); print("ACTUAL NETWORK MUTATION     : LAB MANAGED IPV4"); print("PRIVILEGE SEPARATION        : PASS"); print("SAME PPU_ID REVALIDATION    : PASS"); print("AUTOMATIC ROLLBACK          : PASS"); print("Z2 NETWORK BACKEND CLAIM    : NONE"); print("OVERALL RESULT              : PASS"); print("-"*72)
    print(f"JSON report                 : {report}"); print("="*72); print(RESULT_MARKER+json.dumps(dict(result),sort_keys=True))


def _inside_ppu(args: argparse.Namespace) -> int:
    if platform.machine().lower() not in {"armv7","armv7l"}: raise AcceptanceError(f"inside PPU requires ARMv7, got {platform.machine()}")
    runtime=args.runtime_dir.resolve(); work=args.work_dir.resolve(); app=runtime/"ppu/ppu.pyz"
    manifest=json.loads((runtime/"ppu-runtime.json").read_text(encoding="utf-8")); catalog=runtime/str((manifest.get("data") or {}).get("device_catalog_manifest"))
    env=dict(os.environ); env["PYTHONUNBUFFERED"]="1"; env["PLASMA_DEVICE_CATALOG_MANIFEST"]=str(catalog)
    for directory in (work/"server-output",work/"gateway-output",work/"logs"): directory.mkdir(parents=True,exist_ok=True)
    server=gateway=None
    try:
        server=subprocess.Popen([sys.executable,str(app),"server","--config",str(work/"ppu.yaml")],cwd=work,env=env)
        gateway=subprocess.Popen([sys.executable,str(app),"gateway","--host","0.0.0.0","--port",str(PPU_PORT),"--plasma-host","127.0.0.1","--plasma-port","9900","--output-root",str(work/"gateway-output"),"--network-activation-socket",str(work/"network-helper.sock")],cwd=work,env=env)
        while True:
            if server.poll() is not None: raise AcceptanceError(f"Plasma Server exited: {server.returncode}")
            if gateway.poll() is not None: raise AcceptanceError(f"Gateway exited: {gateway.returncode}")
            time.sleep(0.2)
    finally:
        for process in (gateway,server):
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)


def _align4(length: int) -> int: return (length+3)&~3

def _rtattr(kind: int, payload: bytes) -> bytes:
    length=4+len(payload); return struct.pack("=HH",length,kind)+payload+b"\x00"*(_align4(length)-length)


def _netlink_ack(sock: socket.socket, seq: int) -> None:
    while True:
        packet=sock.recv(65535); offset=0
        while offset+16<=len(packet):
            length,msg_type,_flags,msg_seq,_pid=struct.unpack_from("=IHHII",packet,offset)
            if length<16 or offset+length>len(packet): raise AcceptanceError("malformed rtnetlink response")
            if msg_seq==seq and msg_type==NLMSG_ERROR:
                code=struct.unpack_from("=i",packet,offset+16)[0]
                if code==0: return
                err=-code; raise OSError(err,os.strerror(err))
            offset+=_align4(length)


def _address_message(interface: str,address: str,prefix: int,msg_type: int,*,create: bool=False) -> None:
    ipaddress.IPv4Address(address)
    if not 1<=prefix<=32: raise AcceptanceError("prefix must be 1..32")
    ifindex=socket.if_nametoindex(interface); ifaddr=struct.pack("=BBBBI",socket.AF_INET,prefix,0,RT_SCOPE_UNIVERSE,ifindex); packed=socket.inet_aton(address); attrs=_rtattr(IFA_LOCAL,packed)+_rtattr(IFA_ADDRESS,packed)
    seq=int(time.monotonic_ns()&0xFFFFFFFF) or 1; flags=NLM_F_REQUEST|NLM_F_ACK
    if create: flags|=NLM_F_CREATE|NLM_F_REPLACE
    header=struct.pack("=IHHII",16+len(ifaddr)+len(attrs),msg_type,flags,seq,0)
    with socket.socket(getattr(socket,"AF_NETLINK",16),getattr(socket,"SOCK_RAW",3),NETLINK_ROUTE) as sock:
        sock.bind((0,0)); sock.send(header+ifaddr+attrs); _netlink_ack(sock,seq)


class LabManagedAddress:
    def __init__(self, interface: str, address: str, prefix: int) -> None:
        self.interface=interface; self.address=address; self.prefix=prefix
        _address_message(interface,address,prefix,RTM_NEWADDR,create=True)
    def snapshot(self) -> dict[str,Any]: return {"interface":self.interface,"address":self.address,"prefix_length":self.prefix}
    def replace(self,address: str,prefix: int) -> dict[str,Any]:
        old_address,old_prefix=self.address,self.prefix
        if (old_address,old_prefix)==(address,prefix): return self.snapshot()
        _address_message(self.interface,old_address,old_prefix,RTM_DELADDR)
        try: _address_message(self.interface,address,prefix,RTM_NEWADDR,create=True)
        except Exception:
            try: _address_message(self.interface,old_address,old_prefix,RTM_NEWADDR,create=True)
            finally: raise
        self.address,self.prefix=address,prefix; return self.snapshot()


def _helper_mode(args: argparse.Namespace) -> int:
    if platform.machine().lower() not in {"armv7","armv7l"}: raise AcceptanceError("helper requires ARMv7")
    managed=LabManagedAddress(args.interface,args.managed_initial_address,args.managed_prefix)
    path=args.helper_socket.resolve(); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): path.unlink()
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(path)); path.chmod(0o600); server.listen(8)
        while True:
            connection,_=server.accept()
            with connection:
                raw=bytearray()
                while b"\n" not in raw:
                    chunk=connection.recv(65536)
                    if not chunk: break
                    raw.extend(chunk)
                    if len(raw)>MAX_HELPER_REQUEST: break
                try:
                    request=json.loads(bytes(raw).split(b"\n",1)[0].decode()); operation=request.get("operation")
                    if operation=="snapshot": result=managed.snapshot()
                    elif operation=="apply":
                        settings=request.get("settings")
                        if not isinstance(settings,dict) or settings.get("interface")!=args.interface or settings.get("mode")!="static": raise AcceptanceError("lab helper accepts static eth0 only")
                        result=managed.replace(str(settings["address"]),int(settings["prefix_length"]))
                    elif operation=="restore":
                        snapshot=request.get("snapshot")
                        if not isinstance(snapshot,dict) or snapshot.get("interface")!=args.interface: raise AcceptanceError("invalid restore snapshot")
                        result=managed.replace(str(snapshot["address"]),int(snapshot["prefix_length"]))
                    else: raise AcceptanceError(f"unsupported helper operation: {operation!r}")
                    response={"ok":True,"result":result}
                except Exception as exc: response={"ok":False,"error":{"error_type":"LAB_NETWORK_HELPER_ERROR","message":str(exc)}}
                connection.sendall((json.dumps(response,separators=(",",":"),sort_keys=True)+"\n").encode())


def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Plasma PPU Network Phase 2 acceptance")
    parser.add_argument("--inside-ppu",action="store_true"); parser.add_argument("--helper",action="store_true"); parser.add_argument("--runtime-dir",type=Path,default=Path("/runtime")); parser.add_argument("--work-dir",type=Path,default=DEFAULT_WORK_REL); parser.add_argument("--report",type=Path,default=DEFAULT_REPORT_REL); parser.add_argument("--helper-socket",type=Path,default=Path("/work/network-helper.sock")); parser.add_argument("--interface",default="eth0"); parser.add_argument("--managed-initial-address",default=INITIAL_IP); parser.add_argument("--managed-prefix",type=int,default=24)
    args=parser.parse_args(argv)
    try:
        if args.helper: return _helper_mode(args)
        if args.inside_ppu: return _inside_ppu(args)
        return _host_mode(args)
    except (AcceptanceError,OSError,subprocess.SubprocessError,json.JSONDecodeError,KeyError,ValueError) as exc:
        print(f"ppu-network-phase2-acceptance: {exc}",file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())

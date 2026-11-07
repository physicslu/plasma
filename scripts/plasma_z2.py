#!/usr/bin/env python3
"""PLASMA Z2 read-only deployment doctor (SWPC operator prototype).

No deployment, file writes to the device, privilege escalation, FPGA, DUT,
credential read, or mutable HTTP verbs. Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GIT_TIMEOUT = 5
NETWORK_TIMEOUT = 3
MAX_JSON = 256 * 1024
_HOST_RE = re.compile(r"(?=.{1,253}$)[A-Za-z0-9][A-Za-z0-9.-]*\Z")
_USER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
_REPO_FILES = (
    "AGENTS.md", "scripts/ppu-deploy", "scripts/ppu_deploy.py",
    "scripts/ppu_deploy_target.py", "scripts/ppu_deploy_api.py",
    "scripts/plasmactl", "scripts/plasmactl-z2-ps",
    "scripts/ppu-bootstrap-service.py", "scripts/ppu-bootstrap-deployment.py",
    "scripts/opf_platform_bundle_v3_build.py",
    "scripts/opf_site2_path2_bundle_deploy.py",
    "scripts/opf_site2_joint_acceptance.py",
)


def check(name: str, status: str, detail: str, **data: object) -> dict:
    return {"check": name, "status": status, "detail": detail, **data}


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, timeout=GIT_TIMEOUT, check=False)
    if p.returncode:
        raise RuntimeError("GIT_QUERY_FAILED")
    return p.stdout.strip()


def local_repo(repo: Path) -> list[dict]:
    items = []
    present = [x for x in _REPO_FILES if (repo / x).is_file()]
    missing = [x for x in _REPO_FILES if x not in present]
    items.append(check("source_entrypoints", "WARN" if missing else "PASS",
                       "Missing tracked entrypoints" if missing else "Existing deployment entrypoints found",
                       missing=missing))
    try:
        head = git(repo, "rev-parse", "HEAD")
        branch = git(repo, "branch", "--show-current")
        dirty = bool(git(repo, "status", "--porcelain", "--untracked-files=no"))
        items.append(check("local_git", "WARN" if dirty or branch != "main" else "PASS",
                           "Local source state (no fetch/pull performed)",
                           head=head, branch=branch, tracked_changes=dirty))
        upstream = git(repo, "rev-parse", "--verify", "refs/remotes/origin/main")
        items.append(check("cached_origin_main", "WARN" if upstream != head else "PASS",
                           "Cached origin/main only; remote freshness NOT_VERIFIED",
                           cached_sha=upstream, matches_head=upstream == head))
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        items.append(check("local_git", "WARN", "Git state unavailable; no changes made"))
    state = Path.home() / ".local/share/plasma/engineering/state.json"
    if state.is_symlink():
        items.append(check("engineering_state", "BLOCKED", "State path is a symlink; refused to inspect"))
    elif not state.exists():
        items.append(check("engineering_state", "WARN", "No engineering deployment state found"))
    else:
        try:
            if state.stat().st_size > 16384:
                raise ValueError("too large")
            data = json.loads(state.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != {"current", "previous"}:
                raise ValueError("unexpected state schema")
            for item in ("current", "previous"):
                value = data[item]
                if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)):
                    raise ValueError("invalid release id")
            items.append(check("engineering_state", "PASS", "Local release pointers parsed; Z2 parity NOT_VERIFIED",
                               current=data["current"], previous=data["previous"]))
        except (OSError, ValueError, UnicodeError):
            items.append(check("engineering_state", "BLOCKED", "Untrusted engineering state; no modification"))
    return items


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def fetch_status(host: str, endpoint: str) -> tuple[str, dict | None, str]:
    """Unauthenticated GET on explicitly selected private commissioning address."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    url = f"http://{host}:18081{endpoint}"
    try:
        with opener.open(urllib.request.Request(url, method="GET"), timeout=NETWORK_TIMEOUT) as r:
            body = r.read(MAX_JSON + 1)
        if len(body) > MAX_JSON:
            return "FAIL", None, "Oversized HTTP response"
        record = json.loads(body.decode("utf-8"))
        if not isinstance(record, dict):
            return "FAIL", None, "Unexpected JSON response"
        if endpoint == "/v1/health":
            if record.get("ok") is not True:
                return "FAIL", None, "Bootstrap health rejected request"
        elif endpoint == "/v1/status":
            # Status is a bare schema-v1 status_document, not an {ok:true} envelope.
            if (record.get("schema_version") != 1
                    or not isinstance(record.get("bootstrap"), dict)
                    or not isinstance(record.get("runtime"), dict)
                    or not isinstance(record.get("capabilities"), dict)):
                return "FAIL", None, "Bootstrap status schema invalid or unsupported"
        else:
            return "FAIL", None, "Unsupported diagnostic endpoint"
        return "PASS", record, "Bootstrap JSON response received (unauthenticated commissioning HTTP)"
    except urllib.error.HTTPError as e:
        return "WARN" if e.code in (401, 403) else "FAIL", None, f"Bootstrap HTTP {e.code}"
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, UnicodeError):
        return "FAIL", None, "Bootstrap HTTP unavailable or invalid"


def tcp_probe(host: str, port: int) -> dict:
    try:
        with socket.create_connection((host, port), timeout=NETWORK_TIMEOUT):
            return check(f"tcp_{port}", "PASS", "TCP listener reachable; application health NOT_VERIFIED")
    except OSError:
        return check(f"tcp_{port}", "WARN", "TCP listener not reachable (may be uninstalled/stopped)")


def remote(host: str, ssh_user: str, known_hosts: Path) -> list[dict]:
    if not known_hosts.is_file() or known_hosts.is_symlink():
        return [check("ssh", "BLOCKED", "Pinned known_hosts missing or symlink; refusing SSH")]
    if not _USER_RE.fullmatch(ssh_user):
        return [check("ssh", "BLOCKED", "Invalid SSH username")]
    common = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=no",
              "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
              "-o", "ConnectTimeout=4", "-o", "NumberOfPasswordPrompts=0",
              f"{ssh_user}@{host}"]
    probes = (("ssh_architecture", "uname -m"),
              ("ssh_bootstrap_service", "systemctl is-active plasma-bootstrap.service"),
              ("ssh_runtime_service", "systemctl is-active plasma-server.service"),
              ("ssh_gateway_service", "systemctl is-active plasma-web.service"))
    out = []
    for name, command in probes:
        try:
            p = subprocess.run([*common, command], capture_output=True, text=True,
                               timeout=9, check=False)
            if p.returncode == 255:
                out.append(check("ssh", "BLOCKED", "SSH authentication / pinned host key / connectivity failed; no password fallback"))
                break
            value = p.stdout.strip()[:80]
            if name == "ssh_architecture":
                good = p.returncode == 0 and value in ("armv7l", "armv7")
                out.append(check(name, "PASS" if good else "BLOCKED",
                                 "Expected ARMv7 target" if good else "Not verified as ARMv7 PYNQ-Z2", architecture=value))
                if not good:
                    break
            else:
                good = p.returncode == 0 and value == "active"
                out.append(check(name, "PASS" if good else "WARN", "Active" if good else "Not active / unavailable"))
        except (OSError, subprocess.TimeoutExpired):
            out.append(check("ssh", "BLOCKED", "SSH could not complete; no remote change"))
            break
    return out


def paired_host() -> str:
    """Read only the paired host from the existing owner-only SWPC config.

    Passwords are never used, returned or printed.
    """
    cfg = Path.home() / ".config/plasma/z2-login-smoke.json"
    if cfg.parent.is_symlink() or cfg.is_symlink():
        raise ValueError("PAIRED_TARGET_CONFIG_UNTRUSTED")
    fd = -1
    try:
        fd = os.open(cfg, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_mode & 0o077 or st.st_size > 8192):
            raise ValueError("PAIRED_TARGET_CONFIG_UNTRUSTED")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = json.loads(f.read(8193).decode("utf-8"))
        host = data.get("ssh_host") if isinstance(data, dict) else None
        if not isinstance(host, str) or not _HOST_RE.fullmatch(host):
            raise ValueError("PAIRED_TARGET_HOST_INVALID")
        return host
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("PAIRED_TARGET_CONFIG_UNAVAILABLE") from None
    finally:
        if fd >= 0:
            os.close(fd)


def doctor(args: argparse.Namespace) -> dict:
    rows = local_repo(args.repo.resolve())
    host = args.host
    if args.paired_host:
        try:
            host = paired_host()
            rows.append(check("paired_target", "PASS", "Paired host resolved from owner-only SWPC configuration (address hidden)"))
        except ValueError as exc:
            rows.append(check("paired_target", "BLOCKED", str(exc)))
    if host:
        rows.append(tcp_probe(host, 18081))
        status, payload, message = fetch_status(host, "/v1/health")
        good_identity = bool(payload and payload.get("service") == "plasma-ppu-bootstrap")
        rows.append(check("bootstrap_health", "FAIL" if status == "PASS" and not good_identity else status,
                          "Bootstrap service identified" if good_identity else message))
        status, payload, message = fetch_status(host, "/v1/status")
        if status == "PASS" and not isinstance(payload.get("bootstrap"), dict):
            status, message = "FAIL", "Bootstrap status missing required bootstrap object"
        rows.append(check("bootstrap_status", status, message))
        if payload:
            bootstrap = payload.get("bootstrap")
            runtime = payload.get("runtime")
            deployment = payload.get("deployment")
            caps = payload.get("capabilities")
            bs = bootstrap.get("state") if isinstance(bootstrap, dict) else None
            rt = runtime.get("state") if isinstance(runtime, dict) else None
            ds = deployment.get("state") if isinstance(deployment, dict) else None
            rows.append(check("deployment_guard", "BLOCKED" if ds == "recovery_required" else ("WARN" if ds in ("queued", "running") else "PASS" if ds in (None, "succeeded", "admitted", "failed") else "BLOCKED"),
                              "Recovery required: do NOT deploy" if ds == "recovery_required" else "Deployment transaction state observed",
                              bootstrap_state=bs, runtime_state=rt, deployment_state=ds,
                              capabilities={k: caps.get(k) for k in ("runtime_deployment", "bundle_v3_b3_install", "bundle_v3_b3_mode")}
                                            if isinstance(caps, dict) else {}))
        rows.append(tcp_probe(host, 18080))
        if args.ssh_user:
            rows.extend(remote(host, args.ssh_user, args.known_hosts.expanduser()))
        else:
            rows.append(check("ssh_services", "NOT_RUN", "Supply --ssh-user to enable key-only, host-key-pinned read-only SSH"))
    else:
        rows.append(check("z2_remote", "NOT_RUN", "Supply explicit --host to inspect the target; no network discovery"))
    rows.append(check("target_bundle_identity", "NOT_RUN", "No privileged target-profile or installed Bundle verification in this prototype"))
    rows.append(check("fpga_dut", "NOT_RUN", "FPGA Image/ABI, SWD, DUT and physical Flash deliberately untouched"))
    observed = [row["status"] for row in rows]
    overall = "BLOCKED" if "BLOCKED" in observed else "FAIL" if "FAIL" in observed else "WARN" if "WARN" in observed else "PASS"
    if not host and overall != "BLOCKED":
        overall = "INCOMPLETE"
    return {"schema": "plasma.z2.readonly-doctor.v0", "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "operation": "doctor", "read_only": True, "overall": overall, "checks": rows,
            "limitation": "SWPC/Z2 suitability not proven until real-world execution and privileged identity/version verification"}


def plan(args: argparse.Namespace) -> dict:
    route = args.route
    if route == "engineering":
        steps = ["python3 scripts/ppu-deploy plan <wordport|openocd-integration|abtest>",
                 "Compare SWPC engineering release and Z2 state; confirm idle/ownership and exact source SHA",
                 "Operator-authorized existing script: python3 scripts/ppu-deploy deploy <module>",
                 "Operator-authorized verification: python3 scripts/ppu-deploy verify"]
    else:
        steps = ["Verify same accepted-main Factory Bootstrap and Z2 PS kit artifact SHA sidecars",
                 "Use Console EMode -> PPU Sites -> Runtime Deployment -> Manager -> Bootstrap :18081",
                 "B1 upload; B2 admission; B3 explicit activate/stage_only and fpga_load authorization",
                 "Observe deployment receipt, journal, active runtime and independent reboot/recovery evidence"]
    return {"schema": "plasma.z2.readonly-doctor.v0", "operation": "plan", "route": route,
            "overall": "NOT_AUTHORIZED", "steps": steps,
            "note": "This prototype does not invoke an installer. A deployment must be individually authorized and executed via the existing reviewed backend."}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PLASMA Z2 read-only doctor and deployment plan")
    p.add_argument("action", choices=("doctor", "plan", "deploy"))
    p.add_argument("--repo", type=Path, default=Path.cwd(), help="Current local PLASMA repository root")
    p.add_argument("--host", help="Explicit Z2 LAN IP or DNS name; no auto-discovery")
    p.add_argument("--paired-host", action="store_true", help="Read only the paired host from a private SWPC config; never output credentials")
    p.add_argument("--ssh-user", help="Optional pinned-host-key, key-only SSH (e.g., xilinx)")
    p.add_argument("--known-hosts", type=Path, default=Path.home() / ".config/plasma/z2-login-known_hosts")
    p.add_argument("--route", choices=("product", "engineering"), default="product")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON (default is readable output)")
    args = p.parse_args(argv)
    if args.host and args.paired_host:
        p.error("Select either --host or --paired-host")
    if args.host and not _HOST_RE.fullmatch(args.host):
        p.error("--host requires a plain DNS name / IPv4 address, no scheme, port or path")
    if args.action == "doctor":
        result = doctor(args)
    elif args.action == "plan":
        result = plan(args)
    else:
        result = {"schema": "plasma.z2.readonly-doctor.v0", "operation": "deploy",
                  "overall": "BLOCKED", "reason": "DEPLOY_DISABLED_BY_DESIGN",
                  "detail": "This is a diagnostic-only prototype; use the existing approved deployment backend."}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PLASMA Z2 {result['operation'].upper()}: {result['overall']}")
        for c in result.get("checks", []):
            extra = {k: v for k, v in c.items() if k not in {"check", "status", "detail"}}
            print(f"  [{c['status']:<7}] {c['check']}: {c['detail']}")
            if extra:
                print("            " + json.dumps(extra, ensure_ascii=False, sort_keys=True))
        for step in result.get("steps", []):
            print("  - " + step)
        if "detail" in result:
            print("  " + result["detail"])
    return 2 if result["overall"] in ("BLOCKED", "FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
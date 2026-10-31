#!/usr/bin/env python3
"""PLASMA Path 2 physical PPU Package B1/B2 acceptance.

Owner-approved operator-cli / guarded-hardware ONLY. This script reaches physical Z2 mutations ONLY through the existing
SWPC loopback Manager; a separate read-only direct Bootstrap probe remains. It NEVER installs, activates, invokes SSH,
runs shell, loads FPGA, changes Site state or programs DUT. No token in argv,
stdout, Github Work Order or evidence. The Manager owns the device-bound credential and its Platform maintenance
gate; this CLI never reads, copies, prints, rotates or supplies a token.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile
from io import BytesIO
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,80}\Z")
SCHEMA = "plasma.ppu.hardware-package-baseline.v1"
HOST_ENV = "PLASMA_PPU_COMMISSIONING_ALLOWED_IP"
CLIENT_PATH = ROOT / "scripts/ppu_deploy_api.py"


class BaselineError(RuntimeError):
    pass


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_client():
    spec = importlib.util.spec_from_file_location("ppu_hardware_baseline_api", CLIENT_PATH)
    if spec is None or spec.loader is None:
        raise BaselineError("BASELINE_API_CLIENT_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _private_ipv4(host: str) -> str:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise BaselineError("PPU_IP_LITERAL_REQUIRED") from exc
    if (addr.version != 4 or not addr.is_private or addr.is_loopback
            or addr.is_link_local or addr.is_multicast or addr.is_unspecified):
        raise BaselineError("PPU_PRIVATE_LAN_ONLY")
    # The physically enrolled development Z2 is 192.168.2.99.
    # An explicit local operator-controlled env pin may override for a
    # separately enrolled PPU. Never accept an arbitrary Work Order URL.
    if host != os.environ.get(HOST_ENV, "192.168.2.99"):
        raise BaselineError("PPU_ALLOWED_IP_PIN_MISSING_OR_MISMATCH")
    return host



# Only the local Z2 process can access this file; Engineering Mode uses
# the pre-existing worker SSH/sudo enrollment and an exact trusted host key.
# Do not place the returned secret into any GitHub Work Order, log or file.
_TOKEN_REMOTE_READ = """
import base64, os, stat, sys
path = "/var/lib/plasma-bootstrap/control-token"
try:
    if os.geteuid() != 0:
        raise RuntimeError()
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o077 or not 32 <= metadata.st_size <= 512:
        raise RuntimeError()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        data = os.read(fd, 513)
    finally:
        os.close(fd)
    token = data.strip()
    if not 32 <= len(token) <= 256 or any(ch <= 32 or ch > 126 for ch in token):
        raise RuntimeError()
    sys.stdout.write("PLASMA_BOOTSTRAP_MATERIAL:" + base64.b64encode(token).decode("ascii") + "\\n")
except Exception:
    sys.stderr.write("PLASMA_BOOTSTRAP_MATERIAL_NOT_ACCESSIBLE\\n")
    sys.exit(77)
"""


def _existing_bootstrap_token_via_z2_ssh(host: str, *, helper=None) -> str:
    """Fetch existing token in memory, via pinned SSH and existing sudo route.

    The raw SSH output is private process data: never forward it, including
    on failure. No provisioning, rotation, copy or persistent SWPC token file.
    """
    host = _private_ipv4(host)
    if helper is None:
        spec = importlib.util.spec_from_file_location(
            "ppu_baseline_existing_z2_ssh", ROOT / "scripts/plasma_wordport_program.py"
        )
        if spec is None or spec.loader is None:
            raise BaselineError("Z2_EXISTING_SSH_HELPER_UNAVAILABLE")
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
    try:
        credentials, known_hosts = helper.z2_login_credentials(Path.home())
    except Exception:
        raise BaselineError("Z2_ENROLLED_SSH_CREDENTIAL_UNAVAILABLE") from None
    if credentials.get("ssh_host") != host:
        raise BaselineError("Z2_ENROLLED_SSH_HOST_NOT_APPROVED_TARGET")
    try:
        rc, output = helper.password_ssh_z2(
            ["python3", "-I", "-c", _TOKEN_REMOTE_READ],
            credentials, known_hosts, timeout=45,
        )
    except Exception:
        raise BaselineError("Z2_ENROLLED_SSH_OPERATION_UNAVAILABLE") from None
    if rc != 0:
        raise BaselineError("Z2_BOOTSTRAP_TOKEN_ACCESS_DENIED")
    matches = re.findall(r"PLASMA_BOOTSTRAP_MATERIAL:([A-Za-z0-9+/=]{44,360})", output)
    if len(matches) != 1:
        raise BaselineError("Z2_BOOTSTRAP_TOKEN_RESPONSE_INVALID")
    try:
        material = base64.b64decode(matches[0], validate=True)
        token = material.decode("ascii")
    except (ValueError, UnicodeError):
        raise BaselineError("Z2_BOOTSTRAP_TOKEN_RESPONSE_INVALID") from None
    if not (32 <= len(token) <= 256 and all(33 <= ord(c) <= 126 for c in token)):
        raise BaselineError("Z2_BOOTSTRAP_TOKEN_RESPONSE_INVALID")
    return token


class DirectSSHAuthenticatedBootstrap:
    """Private-LAN Z2 Bootstrap admission with SSH-acquired in-memory secret.

    This is explicitly commissioning HTTP, not production authenticated TLS.
    Never derives authorization from the package or a Manager pairing.
    """
    def __init__(self, host: str, *, module, token: str, connection_factory=None):
        self.host = _private_ipv4(host)
        self.module = module
        self._token = token
        self._connection_factory = connection_factory or http.client.HTTPConnection
        self._physical_direct_baseline = True

    def _call(self, method: str, path: str, body: Mapping[str, object] | None):
        if (method not in ("GET", "POST")
                or not re.fullmatch(
                    r"/v1/(status|deployment|uploads(?:/[0-9a-f]{32}/(?:chunks|commit))?|deployments)",
                    path)):
            raise BaselineError("DIRECT_BOOTSTRAP_ROUTE_DENIED")
        if method == "POST" and path not in ("/v1/uploads", "/v1/deployments") and not path.startswith("/v1/uploads/"):
            raise BaselineError("DIRECT_BOOTSTRAP_WRITE_DENIED")
        raw = (json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
               if body is not None else None)
        if raw is not None and len(raw) > 2 * 1024 * 1024:
            raise BaselineError("DIRECT_BOOTSTRAP_REQUEST_TOO_LARGE")
        conn = self._connection_factory(self.host, 18081, timeout=15)
        try:
            conn.request(method, path, body=raw, headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if raw is not None else {}),
            })
            response = conn.getresponse()
            data = response.read(2 * 1024 * 1024 + 1)
            status = response.status
        finally:
            conn.close()
        if len(data) > 2 * 1024 * 1024:
            raise BaselineError("DIRECT_BOOTSTRAP_RESPONSE_TOO_LARGE")
        if status < 200 or status >= 300:
            reason = ""
            if status == 409:
                try:
                    error = json.loads(data.decode("utf-8"))
                except (ValueError, UnicodeError):
                    error = None
                if type(error) is dict and error.get("error") == "bootstrap_request_rejected":
                    reasons = {
                        "chunk SHA-256 mismatch": "CHUNK_SHA256_MISMATCH",
                        "PACKAGE_FILE_SHA256_MISMATCH": "PACKAGE_FILE_SHA256_MISMATCH",
                        "PACKAGE_MANIFEST_CONTENT_DENIED": "PACKAGE_MANIFEST_CONTENT_DENIED",
                    }
                    message = error.get("message")
                    if type(message) is str:
                        reason = reasons.get(message, "")
            raise self.module.DeploymentAPIError(
                f"API_HTTP_REJECTED:{status}" + (":" + reason if reason else "")
            )
        try:
            response_data = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise BaselineError("DIRECT_BOOTSTRAP_RESPONSE_INVALID") from None
        if type(response_data) is not dict:
            raise BaselineError("DIRECT_BOOTSTRAP_RESPONSE_INVALID")
        if path == "/v1/status":
            # Existing physical Z2 status_document has no top-level ok flag.
            if (type(response_data.get("identity")) is not dict
                    or type(response_data.get("bootstrap")) is not dict
                    or type(response_data.get("runtime")) is not dict):
                raise BaselineError("DIRECT_BOOTSTRAP_STATUS_INVALID")
        elif response_data.get("ok") is not True:
            raise BaselineError("DIRECT_BOOTSTRAP_RESPONSE_INVALID")
        return response_data

    def status(self):
        return self._call("GET", "/v1/status", None)

    def upload(self, archive):
        return self.module.BootstrapAPIClient.upload(self, archive)

    def submit(self, *, kind, upload_id, **kwargs):
        return self.module.BootstrapAPIClient.submit(
            self, kind=kind, upload_id=upload_id, **kwargs,
        )

    def deployment_state(self, transaction_id):
        return self.module.BootstrapAPIClient.deployment_state(self, transaction_id)


class ManagerAdmissionClient:
    """Reuse Manager's existing device-paired Bootstrap routes, no credentials.

    The trusted Manager enforces alias -> live device identity, idle-state
    Platform gate, device-scoped credential, and upload/commit serialization.
    Not a new installer or bypass endpoint.
    """
    def __init__(self, *, alias: str, port: int, client_module):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", alias):
            raise BaselineError("MANAGER_ALIAS_INVALID")
        if type(port) is not int or port not in (18180, 18280):
            raise BaselineError("MANAGER_LOOPBACK_PORT_DENIED")
        self.alias = alias
        self.port = port
        self.module = client_module
        self.base_path = f"/api/registry/{alias}/bootstrap"

    def _call(self, method: str, path: str, body: Mapping[str, object] | None):
        if method not in ("GET", "POST") or not path.startswith("/v1/"):
            raise BaselineError("MANAGER_ACTION_DENIED")
        if path in ("/v1/status", "/v1/deployment"):
            if method != "GET" or body is not None:
                raise BaselineError("MANAGER_READ_ACTION_DENIED")
            manager_path, payload = self.base_path, None
        elif method == "POST" and path in ("/v1/uploads", "/v1/deployments"):
            manager_path, payload = self.base_path + path[3:], dict(body or {})
        else:
            match = re.fullmatch(
                r"/v1/uploads/([0-9a-f]{32})/(chunks|commit)", path
            )
            if method != "POST" or match is None:
                raise BaselineError("MANAGER_ACTION_NOT_ALLOWLISTED")
            uid, operation = match.groups()
            manager_path = f"{self.base_path}/uploads/{uid}/{operation}"
            payload = {"action": "commit"} if operation == "commit" else dict(body or {})
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
               if payload is not None else None)
        if raw is not None and len(raw) > 2 * 1024 * 1024:
            raise BaselineError("MANAGER_REQUEST_TOO_LARGE")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, manager_path, body=raw, headers={
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if raw else {}),
            })
            response = conn.getresponse()
            data = response.read(2 * 1024 * 1024 + 1)
            code = response.status
            if len(data) > 2 * 1024 * 1024:
                raise BaselineError("MANAGER_RESPONSE_TOO_LARGE")
            if code < 200 or code >= 300:
                # Negative tests must prove *content rejection*, not merely a
                # 409 from Manager's idle gate or missing pairing. Whitelist
                # static non-secret PPU verifier errors; never log upstream data.
                reason = ""
                if code == 409:
                    try:
                        rejected = json.loads(data.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        rejected = None
                    if (isinstance(rejected, dict)
                            and rejected.get("error") == "bootstrap_request_rejected"):
                        allowed = {
                            "chunk SHA-256 mismatch": "CHUNK_SHA256_MISMATCH",
                            "PACKAGE_FILE_SHA256_MISMATCH": "PACKAGE_FILE_SHA256_MISMATCH",
                            "PACKAGE_MANIFEST_CONTENT_DENIED": "PACKAGE_MANIFEST_CONTENT_DENIED",
                        }
                        message = rejected.get("message")
                        reason = allowed.get(message, "") if type(message) is str else ""
                raise self.module.DeploymentAPIError(
                    f"API_HTTP_REJECTED:{code}" + (f":{reason}" if reason else "")
                )
            result = json.loads(data.decode("utf-8"))
        finally:
            conn.close()
        if type(result) is not dict or result.get("ok") is not True:
            raise BaselineError("MANAGER_RESPONSE_INVALID")
        if path == "/v1/status":
            bootstrap = result.get("bootstrap")
            pairing = result.get("pairing")
            if (not isinstance(bootstrap, dict) or not isinstance(pairing, dict)
                    or result.get("ppu_alias") != self.alias
                    or result.get("bootstrap_endpoint_policy") != "z2-ps-same-host:18081"):
                raise BaselineError("MANAGER_BOOTSTRAP_STATUS_INVALID")
            self._last_pairing = dict(pairing)
            return bootstrap
        if path == "/v1/deployment":
            bootstrap = result.get("bootstrap")
            if not isinstance(bootstrap, dict):
                raise BaselineError("MANAGER_DEPLOYMENT_STATUS_INVALID")
            return {"ok": True, "deployment": bootstrap.get("deployment")}
        return result

    def status(self) -> dict[str, Any]:
        return self._call("GET", "/v1/status", None)

    def preflight(self, expected_device_id: str, *, expected_host: str) -> dict[str, Any]:
        # Require the configured Manager target to be the exact physical Z2.
        # A QEMU/surrogate or unrelated alias must never satisfy B1.
        host = _private_ipv4(expected_host)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/api/registry", headers={"Accept": "application/json"})
            response = conn.getresponse()
            raw = response.read(65537)
            if response.status != 200 or not raw or len(raw) > 65536:
                raise BaselineError("MANAGER_REGISTRY_UNAVAILABLE")
            registry = json.loads(raw.decode("utf-8"))
        finally:
            conn.close()
        if type(registry) is not dict or registry.get("ok") is not True:
            raise BaselineError("MANAGER_REGISTRY_INVALID")
        entries = registry.get("ppus")
        expected_endpoint = f"http://{host}:18080"
        if (type(entries) is not list or sum(
                type(item) is dict and item.get("alias") == self.alias
                and item.get("endpoint") == expected_endpoint
                for item in entries) != 1):
            raise BaselineError("MANAGER_PHYSICAL_TARGET_NOT_ENROLLED")
        status = self.status()
        pairing = self._last_pairing
        identity = status.get("identity")
        if (not isinstance(identity, dict)
                or identity.get("device_id") != expected_device_id):
            raise BaselineError("MANAGER_DEVICE_IDENTITY_MISMATCH")
        if pairing.get("paired") is not True:
            raise BaselineError("MANAGER_BOOTSTRAP_NOT_PAIRED")
        if (pairing.get("device_match") is not True
                or pairing.get("device_id") != expected_device_id):
            raise BaselineError("MANAGER_PAIRING_DEVICE_MISMATCH")
        return status

    def upload(self, archive: bytes) -> str:
        return self.module.BootstrapAPIClient.upload(self, archive)

    def submit(self, *, kind: str, upload_id: str, **kwargs):
        return self.module.BootstrapAPIClient.submit(
            self, kind=kind, upload_id=upload_id, **kwargs,
        )

    def deployment_state(self, transaction_id: str) -> dict[str, Any]:
        return self.module.BootstrapAPIClient.deployment_state(self, transaction_id)


def enroll_manager_real_z2(host: str, device_id: str, *,
                           alias: str = "z2", port: int = 18280,
                           probe=None, connection_factory=None) -> dict[str, Any]:
    """Owner-approved exact real Z2 registry ADD; never pair or rotate secrets.

    Fail closed on alias/endpoint conflict, immutable Manager, wrong real
    hardware identity. Registry registration alone is NOT pairing or B1.
    """
    host = _private_ipv4(host)
    if not re.fullmatch(r"ppu-device-[0-9a-f]{16,64}", device_id):
        raise BaselineError("ENROLL_DEVICE_ID_INVALID")
    if alias != "z2" or port != 18280:
        raise BaselineError("ENROLL_FIXED_MANAGER_ALIAS_AND_PORT_REQUIRED")
    observed = (probe(host) if probe is not None else probe_status(host))
    if observed.get("device_id_observed") != device_id:
        raise BaselineError("ENROLL_REAL_DEVICE_ID_MISMATCH")
    factory = connection_factory or http.client.HTTPConnection

    def request(method, body=None):
        conn = factory("127.0.0.1", port, timeout=10)
        try:
            raw = None if body is None else json.dumps(
                body, sort_keys=True, separators=(",", ":")).encode()
            conn.request(method, "/api/registry", body=raw, headers={
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if raw is not None else {}),
            })
            response = conn.getresponse()
            data = response.read(65537)
            if not data or len(data) > 65536:
                raise BaselineError("ENROLL_MANAGER_RESPONSE_INVALID")
            payload = json.loads(data.decode("utf-8"))
            if type(payload) is not dict:
                raise BaselineError("ENROLL_MANAGER_RESPONSE_INVALID")
            return response.status, payload
        finally:
            conn.close()

    endpoint = f"http://{host}:18080"
    code, registry = request("GET")
    if code != 200 or registry.get("ok") is not True:
        raise BaselineError("ENROLL_MANAGER_REGISTRY_UNAVAILABLE")
    if registry.get("mutable") is not True or type(registry.get("ppus")) is not list:
        raise BaselineError("ENROLL_REGISTRY_NOT_MUTABLE")
    entries = registry["ppus"]
    if any(type(x) is not dict for x in entries):
        raise BaselineError("ENROLL_REGISTRY_INVALID")
    if any(x.get("endpoint") == endpoint and x.get("alias") != alias for x in entries):
        raise BaselineError("ENROLL_ENDPOINT_ALREADY_OWNED")
    ours = [x for x in entries if x.get("alias") == alias]
    if len(ours) > 1 or (ours and ours[0].get("endpoint") != endpoint):
        raise BaselineError("ENROLL_ALIAS_CONFLICT")
    if ours:
        state = "ALREADY_ENROLLED"
        record = ours[0]
    else:
        status, added = request("POST", {"alias": alias, "endpoint": endpoint})
        if status != 201 or added.get("ok") is not True:
            raise BaselineError("ENROLL_MANAGER_ADD_REJECTED")
        record = added.get("entry")
        if (type(record) is not dict or record.get("endpoint") != endpoint
                or record.get("alias") != alias or record.get("lifecycle") != "pending"):
            raise BaselineError("ENROLL_ADD_RECEIPT_INVALID")
        state = "REGISTERED_PENDING"

    verify_code, verification = request("GET")
    valid = verification.get("ppus") if type(verification) is dict else None
    if verify_code != 200 or type(valid) is not list or not any(
            type(x) is dict and x.get("endpoint") == endpoint
            and x.get("alias") == alias for x in valid):
        raise BaselineError("ENROLL_POSTWRITE_REGISTRY_UNVERIFIED")
    return {
        "schema": SCHEMA, "phase": "MANAGER_PHYSICAL_Z2_REGISTRY_ENROLLMENT",
        "registration": state, "alias": alias, "manager_port": port,
        "endpoint": endpoint, "device_id_verified": device_id,
        "lifecycle": record.get("lifecycle"),
        "pairing": "NOT_VERIFIED",
        "b1": "NOT_RUN", "b2_v1": "NOT_RUN", "b2_v3": "NOT_RUN",
        "install": "NOT_RUN", "fpga": "NOT_RUN", "dut": "NOT_RUN",
    }


def inspect_swpc_manager_runtime(*, home: Path | None = None,
                                 systemctl=None) -> dict[str, Any]:
    """Read-only, fixed-path SWPC local-control-station owner inspection.

    No credential bytes, arbitrary paths, generic process command or config
    payloads enter stdout. Never runs a shell or privileged operation.
    """
    home = home or Path.home()
    config = home / ".config/plasma/local-control-station/manager.yaml"
    unit = home / ".config/systemd/user/plasma-local-manager.service"
    current = home / ".local/share/plasma/local-control-station/current"
    state = home / ".local/state/plasma/local-control-station"
    def inspected_file(path: Path) -> dict[str, Any]:
        if not path.exists() or path.is_symlink() or not path.is_file():
            return {"exists": False, "regular_owned": False}
        info = path.stat()
        return {"exists": True, "regular_owned": info.st_uid == os.geteuid(),
                "mode": oct(stat.S_IMODE(info.st_mode)), "sha256": _sha(path.read_bytes())}
    unit_meta = inspected_file(unit)
    config_meta = inspected_file(config)
    config_text = config.read_text(encoding="utf-8") if config_meta["exists"] else ""
    unit_text = unit.read_text(encoding="utf-8") if unit_meta["exists"] else ""
    expected_command = (
        str(current) + "/venv/bin/python -m plasma_manager.server --config " + str(config)
    )
    runtime_class = (
        "GENERIC_MANAGER"
        if "ExecStart=" + expected_command in unit_text
        else "BOOTSTRAP_MANAGER"
        if "ExecStart=" + expected_command.replace(
            "plasma_manager.server", "plasma_manager.bootstrap_server") in unit_text
        else "UNRECOGNIZED"
    )
    registry_values = re.findall(
        r"(?m)^\s{2}registry_state_path:\s*(.+?)\s*$", config_text
    )
    reg_configured = len(registry_values) == 1 and registry_values[0] not in ("null", "~", "")
    candidate_state_path = state / "registry.json"
    found_state = inspected_file(candidate_state_path)
    found_credentials = inspected_file(state / "bootstrap-credentials.json")
    found_credentials.pop("sha256", None)
    # Program availability via currently active release, no execution or secrets.
    bootstrap_module_available = bool(
        list((current / "venv/lib").glob("python*/site-packages/plasma_manager/bootstrap_server.py"))
    )
    manager_unit_active = "NOT_CHECKED"
    owner_can_manage_user_service = False
    ctl = systemctl or (lambda: subprocess.run(
        ["systemctl", "--user", "show", "plasma-local-manager.service",
         "--property=ActiveState,LoadState,MainPID", "--no-pager"],
        check=False, capture_output=True, text=True, timeout=8))
    try:
        info = ctl()
        if info.returncode == 0:
            fields = dict(line.split("=", 1) for line in info.stdout.splitlines()
                          if "=" in line and line.split("=", 1)[0] in (
                              "ActiveState", "LoadState", "MainPID"))
            manager_unit_active = fields.get("ActiveState", "UNKNOWN")
            owner_can_manage_user_service = fields.get("LoadState") == "loaded"
        else:
            manager_unit_active = "USER_SYSTEMD_NOT_AVAILABLE"
    except (OSError, subprocess.SubprocessError):
        manager_unit_active = "USER_SYSTEMD_NOT_AVAILABLE"
    return {
        "schema": SCHEMA, "phase": "READ_ONLY_SWPC_MANAGER_RUNTIME_INSPECTION",
        "manager_port": 18280,
        "manager_config": config_meta, "manager_unit": unit_meta,
        "manager_entrypoint": runtime_class,
        "registry_state_configured": reg_configured,
        "registry_candidate_state": found_state,
        "bootstrap_credential_file": {
            "exists": found_credentials.get("exists", False),
            "regular_owned": found_credentials.get("regular_owned", False),
            "mode": found_credentials.get("mode"),
            "content": "NEVER_READ",
        },
        "bootstrap_module_installed": bootstrap_module_available,
        "manager_service_state": manager_unit_active,
        "user_service_control_available": owner_can_manage_user_service,
        "b1": "NOT_RUN", "b2_v1": "NOT_RUN", "b2_v3": "NOT_RUN",
        "install": "NOT_RUN", "fpga": "NOT_RUN", "dut": "NOT_RUN",
    }


def probe_manager_registries(expected_host: str, *, ports=(18180, 18280)):
    """Read-only SWPC Manager profile inventory, never selects target or mutates.

    Reveal only aliases matching the independently known exact real PPU
    endpoint. A different alias still requires an owner-pinned Work Order.
    """
    host = _private_ipv4(expected_host)
    result = []
    for port in ports:
        if type(port) is not int or port not in (18180, 18280):
            raise BaselineError("MANAGER_LOOPBACK_PORT_DENIED")
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", "/api/registry", headers={"Accept": "application/json"})
            response = conn.getresponse()
            raw = response.read(65537)
            if response.status != 200 or not raw or len(raw) > 65536:
                result.append({"port": port, "status": "NOT_AVAILABLE"})
                continue
            registry = json.loads(raw.decode("utf-8"))
            ppus = registry.get("ppus") if isinstance(registry, dict) else None
            if not isinstance(registry, dict) or registry.get("ok") is not True or not isinstance(ppus, list):
                result.append({"port": port, "status": "INVALID_REGISTRY"})
                continue
            matches = sorted(
                entry["alias"] for entry in ppus
                if (isinstance(entry, dict)
                    and entry.get("endpoint") == f"http://{host}:18080"
                    and type(entry.get("alias")) is str
                    and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", entry["alias"]))
            )
            result.append({
                "port": port, "status": "MATCH" if matches else "NO_PHYSICAL_TARGET",
                "real_z2_aliases": matches,
            })
        except (OSError, ValueError, json.JSONDecodeError):
            result.append({"port": port, "status": "NOT_AVAILABLE"})
        finally:
            conn.close()
    return {"schema": SCHEMA, "phase": "READ_ONLY_MANAGER_REGISTRY_INVENTORY",
            "target_host": host, "managers": result, "b1": "NOT_RUN",
            "b2_v1": "NOT_RUN", "b2_v3": "NOT_RUN",
            "install": "NOT_RUN", "fpga": "NOT_RUN", "dut": "NOT_RUN"}


def probe_status(host: str, *, read_get=None) -> dict[str, Any]:
    """Read-only actual installed Bootstrap identity/version preflight.

    The returned identity is OBSERVED, not automatically an approved
    mutating-device pin. Only the later owner-reviewed Work Order can pin it.
    """
    host = _private_ipv4(host)
    def direct_get(path: str) -> dict[str, Any]:
        connection = http.client.HTTPConnection(host, 18081, timeout=10)
        try:
            connection.request("GET", path, headers={"Accept": "application/json"})
            response = connection.getresponse()
            raw = response.read(65537)
            if response.status != 200 or not raw or len(raw) > 65536:
                raise BaselineError("PPU_PROBE_HTTP_REJECTED")
            payload = json.loads(raw.decode("utf-8"))
            if type(payload) is not dict:
                raise BaselineError("PPU_PROBE_RESPONSE_INVALID")
            return payload
        finally:
            connection.close()

    reader = direct_get if read_get is None else read_get
    health = reader("/v1/health")
    status = reader("/v1/status")
    identity = status.get("identity")
    bootstrap = status.get("bootstrap")
    runtime = status.get("runtime")
    if (health.get("service") != "plasma-ppu-bootstrap"
            or type(identity) is not dict or type(bootstrap) is not dict
            or type(runtime) is not dict
            or bootstrap.get("state") != "bootstrap_ready"
            or type(identity.get("device_id")) is not str
            or not re.fullmatch(r"ppu-device-[0-9a-f]{16,64}", identity["device_id"])):
        raise BaselineError("PPU_PROBE_IDENTITY_INVALID")
    return {"schema": SCHEMA, "phase": "READ_ONLY_DEVICE_PROBE",
            "b1": "NOT_RUN", "b2_v1": "NOT_RUN", "b2_v3": "NOT_RUN",
            "device_id_observed": identity["device_id"],
            "bootstrap_version_observed": bootstrap.get("version"),
            "bootstrap_api_version_observed": bootstrap.get("api_version"),
            "runtime_state_observed": runtime.get("state"),
            "installed_verifier_source_sha": "NOT_ATTESTED",
            "install": "NOT_RUN", "fpga": "NOT_RUN", "dut": "NOT_RUN"}


def _git_head() -> str:
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True, timeout=5, check=True)
    return res.stdout.strip()


def _zipped(manifest: Mapping[str, Any], entries: Mapping[str, bytes]) -> bytes:
    result = BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as out:
        for path, data in [("manifest.json", json.dumps(
                manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")),
                *sorted(entries.items())]:
            info = zipfile.ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            out.writestr(info, data)
    return result.getvalue()


def _file(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "size": len(data), "sha256": _sha(data), "executable": False}


def sample_v1(source_sha: str, target: Mapping[str, str], *, corrupt_file_sha: bool = False,
              mismatch_target: bool = False) -> bytes:
    content = b"# PLASMA hardware baseline - data only, never executed\n"
    path = "payload/python/baseline.py"
    meta = _file(path, content)
    if corrupt_file_sha:
        meta["sha256"] = "0" * 64
    manifest = {
        "schema": "plasma.ppu.package.v1",
        "name": "hardware-baseline-b1",
        "kind": "python",
        "version": "1.0.0",
        "source_commit": source_sha,
        "target": dict(target),
        "files": [meta],
    }
    if mismatch_target:
        manifest["target"]["board"] = "mismatch-board"
    return _zipped(manifest, {path: content})


def sample_v3(source_sha: str, target: Mapping[str, str]) -> bytes:
    first_path = "payload/packages/catalog/data/ic.json"
    second_path = "payload/packages/profile/data/geometry.json"
    first = b'{"ic":"safe-host-only-fixture"}'
    second = b'{"flash_size":65536}'
    manifest = {
        "schema": "plasma.ppu.bundle.v3",
        "name": "hardware-baseline-bundle",
        "version": "1.0.0",
        "purpose": "diagnostics",
        "source_commit": source_sha,
        "target": dict(target),
        "packages": [
            {"id": "catalog", "kind": "ic-catalog", "version": "1.0.0",
             "requires": [], "files": [_file(first_path, first)]},
            {"id": "profile", "kind": "programming-profile", "version": "1.0.0",
             "requires": ["catalog"], "files": [_file(second_path, second)]},
        ],
    }
    return _zipped(manifest, {first_path: first, second_path: second})


def _expect_http_rejection(api, method: str, path: str, body: dict, error: str,
                           *, expected_reason: str | None = None) -> None:
    try:
        api._call(method, path, body)
    except Exception as exc:
        if not isinstance(exc, error):
            raise BaselineError("NEGATIVE_WRONG_ERROR_CLASS") from exc
        if "API_HTTP_REJECTED:409" not in str(exc):
            raise BaselineError("NEGATIVE_NOT_REJECTED_AS_409") from None
        if (expected_reason is not None
                and (isinstance(api, ManagerAdmissionClient)
                     or getattr(api, "_physical_direct_baseline", False))
                and not str(exc).endswith(":" + expected_reason)):
            raise BaselineError("NEGATIVE_REJECTION_CAUSE_UNPROVEN") from None
    else:
        raise BaselineError("NEGATIVE_UNEXPECTEDLY_ACCEPTED")


def b1_upload(api, client_module, data: bytes) -> dict[str, Any]:
    """Real upload, tampered-chunk denial and exact committed SHA256."""
    digest = _sha(data)
    created = api._call("POST", "/v1/uploads", {"size": len(data), "sha256": digest})
    upload = created.get("upload")
    uid = upload.get("upload_id") if isinstance(upload, dict) else None
    if type(uid) is not str or not HEX32.fullmatch(uid):
        raise BaselineError("B1_UPLOAD_ID_INVALID")
    first = data[:min(4096, len(data))]
    _expect_http_rejection(api, "POST", f"/v1/uploads/{uid}/chunks", {
        "offset": 0, "data_base64": base64.b64encode(first).decode(),
        "sha256": "0" * 64,
    }, client_module.DeploymentAPIError, expected_reason="CHUNK_SHA256_MISMATCH")
    offset = 0
    for start in range(0, len(data), 1024 * 1024):
        part = data[start:start + 1024 * 1024]
        reply = api._call("POST", f"/v1/uploads/{uid}/chunks", {
            "offset": offset, "data_base64": base64.b64encode(part).decode(),
            "sha256": _sha(part),
        })
        meta = reply.get("upload")
        offset += len(part)
        if not isinstance(meta, dict) or meta.get("received_bytes") != offset:
            raise BaselineError("B1_CHUNK_PROGRESS_INVALID")
    committed = api._call("POST", f"/v1/uploads/{uid}/commit", {}).get("upload")
    if (not isinstance(committed, dict)
            or committed.get("state") != "committed"
            or committed.get("upload_id") != uid
            or committed.get("sha256") != digest):
        raise BaselineError("B1_COMMIT_RECEIPT_INVALID")
    return {"status": "PASS", "upload_id": uid, "archive_sha256": digest,
            "bytes_received": len(data), "negative_chunk_sha256": "REJECTED"}


def b2_admission(api, uid: str, source_sha: str, target: Mapping[str, str],
                 digest: str, *, kind: str) -> dict[str, Any]:
    submission = api.submit(kind=kind, upload_id=uid)
    if submission.state != "admitted":
        raise BaselineError("B2_NOT_ADMITTED")
    r = api.deployment_state(submission.transaction_id)
    result = r["result"]
    plan = result["plan"]
    if (result["stage"] != "package_admission_only"
            or result["install_qualified"] is not False
            or plan["execution_permitted"] is not False
            or plan["source_commit"] != source_sha
            or plan["target"] != dict(target)
            or plan["archive_sha256"] != digest
            or plan["kind"] != kind):
        raise BaselineError("B2_INCORRECT_RECEIPT")
    return {"status": "PASS", "transaction_id": submission.transaction_id,
            "archive_sha256": digest, "stage": result["stage"],
            "execution_permitted": False, "install_qualified": False,
            "kind": kind}


def b2_negative(api, client_module, source_sha: str, target: Mapping[str, str]) -> dict[str, str]:
    failed = sample_v1(source_sha, target, corrupt_file_sha=True)
    uid = api.upload(failed)
    _expect_http_rejection(api, "POST", "/v1/deployments",
                           {"kind": "python", "upload_id": uid},
                           client_module.DeploymentAPIError,
                           expected_reason="PACKAGE_FILE_SHA256_MISMATCH")
    mismatched = sample_v1(source_sha, target, mismatch_target=True)
    uid2 = api.upload(mismatched)
    _expect_http_rejection(api, "POST", "/v1/deployments",
                           {"kind": "python", "upload_id": uid2},
                           client_module.DeploymentAPIError,
                           expected_reason="PACKAGE_MANIFEST_CONTENT_DENIED")
    return {"wrong_file_sha256": "REJECTED", "wrong_target": "REJECTED"}


def run(api, client_module, *, source_sha: str, target: Mapping[str, str],
        expected_device_id: str) -> dict[str, Any]:
    """Distinct B1, B2-v1, B2-v3 verdicts; no installation ever."""
    report: dict[str, Any] = {
        "schema": SCHEMA, "source_sha": source_sha, "target": dict(target),
        "device_id": None, "b1": {"status": "NOT_RUN"},
        "b2_v1": {"status": "NOT_RUN"}, "b2_v3": {"status": "NOT_RUN"},
        "b3_install": "NOT_RUN", "b4_activation_rollback": "NOT_RUN",
        "fpga": "NOT_RUN", "dut": "NOT_RUN",
        "transport_security": "PRIVATE_COMMISSIONING_HTTP_NOT_PRODUCTION_QUALIFIED",
        "baseline_qualification": "NOT_QUALIFIED",
    }
    status = api.status()
    info = status.get("identity")
    actual = info.get("device_id") if isinstance(info, dict) else None
    if (type(actual) is not str or actual != expected_device_id
            or status.get("bootstrap", {}).get("state") != "bootstrap_ready"):
        report["b1"] = {"status": "BLOCKED", "code": "PINNED_DEVICE_IDENTITY_MISMATCH"}
        return report
    report["device_id"] = actual
    report["bootstrap_version_observed"] = status["bootstrap"].get("version")
    report["bootstrap_api_version_observed"] = status["bootstrap"].get("api_version")
    report["installed_verifier_source_sha"] = "NOT_ATTESTED"
    if status.get("runtime", {}).get("state") == "recovery_required" or (
            isinstance(status.get("deployment"), dict) and
            status["deployment"].get("state") in ("queued", "running", "recovery_required")):
        report["b1"] = {"status": "BLOCKED", "code": "PPU_RECOVERY_OR_ACTIVE_DEPLOYMENT"}
        return report
    raw_v1 = sample_v1(source_sha, target)
    try:
        b1 = b1_upload(api, client_module, raw_v1)
        report["b1"] = b1
    except Exception as exc:
        report["b1"] = {"status": "FAIL", "code": type(exc).__name__}
        return report
    try:
        result = b2_admission(api, b1["upload_id"], source_sha, target,
                              b1["archive_sha256"], kind="python")
        result["negatives"] = b2_negative(api, client_module, source_sha, target)
        report["b2_v1"] = result
    except Exception as exc:
        report["b2_v1"] = {"status": "BLOCKED", "code": type(exc).__name__}
    # A missing v3 verifier on Z2 is an independent qualification gap,
    # not a failure of B1 or a reason to upgrade the installed Bootstrap.
    try:
        raw_v3 = sample_v3(source_sha, target)
        v3_uid = api.upload(raw_v3)
        report["b2_v3"] = b2_admission(
            api, v3_uid, source_sha, target, _sha(raw_v3), kind="bundle",
        )
    except Exception as exc:
        report["b2_v3"] = {"status": "NOT_QUALIFIED", "code": type(exc).__name__}
    if (report["b1"]["status"] == "PASS"
            and report["b2_v1"]["status"] == "PASS"
            and report["b2_v3"]["status"] == "PASS"):
        report["baseline_qualification"] = "B1_B2_V1_V2_PASS"
    elif (report["b1"]["status"] == "PASS"
          and report["b2_v1"]["status"] == "PASS"):
        report["baseline_qualification"] = "B1_B2_V1_PASS_V3_NOT_QUALIFIED"
    elif report["b1"]["status"] == "PASS":
        report["baseline_qualification"] = "B1_PASS_PARTIAL"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Z2 hardware Package receive/admission ONLY")
    parser.add_argument("--host", required=True)
    parser.add_argument("--probe", action="store_true",
                        help="read-only Z2 identity/version, no credential or writes")
    parser.add_argument("--manager-alias", default="z2")
    parser.add_argument("--manager-port", type=int, default=18280)
    parser.add_argument("--direct-bootstrap-ssh", action="store_true",
                        help="existing enrolled Z2 SSH token in memory; no Manager or installer")
    parser.add_argument("--inspect-swpc-manager", action="store_true",
                        help="read-only fixed-path SWPC Manager runtime config inspection")
    parser.add_argument("--enroll-manager", action="store_true",
                        help="owner-approved real Z2 registry add ONLY; no pairing or package")
    parser.add_argument("--manager-inventory", action="store_true",
                        help="read-only SWPC Manager profile registry scan")
    parser.add_argument("--manager-probe", action="store_true",
                        help="read-only paired Manager status, no writes")
    parser.add_argument("--device-id")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--platform")
    parser.add_argument("--board")
    parser.add_argument("--fpga-part")
    args = parser.parse_args(argv)
    try:
        if not SHA40.fullmatch(args.source_sha) or _git_head() != args.source_sha:
            raise BaselineError("SOURCE_SHA_PIN_MISMATCH")
        host = _private_ipv4(args.host)
        if args.inspect_swpc_manager:
            print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps(
                {**inspect_swpc_manager_runtime(), "source_sha": args.source_sha},
                sort_keys=True, separators=(",", ":"),
            ))
            return 0
        if args.enroll_manager:
            if not args.device_id:
                raise BaselineError("ENROLL_DEVICE_ID_REQUIRED")
            result = enroll_manager_real_z2(
                host, args.device_id, alias=args.manager_alias, port=args.manager_port,
            )
            print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps(
                {**result, "source_sha": args.source_sha},
                sort_keys=True, separators=(",", ":"),
            ))
            return 0
        if args.manager_inventory:
            print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps(
                {**probe_manager_registries(host), "source_sha": args.source_sha},
                sort_keys=True, separators=(",", ":"),
            ))
            return 0
        if args.probe:
            print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps(
                {**probe_status(host), "source_sha": args.source_sha},
                sort_keys=True, separators=(",", ":"),
            ))
            return 0
        if not all(type(v) is str for v in
                   (args.device_id, args.platform, args.board, args.fpga_part)):
            raise BaselineError("PINNED_DEVICE_AND_TARGET_REQUIRED")
        target = {"platform": args.platform, "board": args.board, "fpga_part": args.fpga_part}
        if any(not SAFE.fullmatch(v) for v in target.values()):
            raise BaselineError("TARGET_PROFILE_INPUT_DENIED")
        if not re.fullmatch(r"ppu-device-[0-9a-f]{16,64}", args.device_id):
            raise BaselineError("DEVICE_ID_PIN_INVALID")
        module = _load_client()
        if args.direct_bootstrap_ssh:
            token = _existing_bootstrap_token_via_z2_ssh(host)
            api = DirectSSHAuthenticatedBootstrap(host, module=module, token=token)
            report = run(api, module, source_sha=args.source_sha,
                         target=target, expected_device_id=args.device_id)
            print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps(
                report, sort_keys=True, separators=(",", ":"),
            ))
            return 0 if report["b1"]["status"] == "PASS" else 1
        api = ManagerAdmissionClient(alias=args.manager_alias,
                                     port=args.manager_port,
                                     client_module=module)
        status = api.preflight(args.device_id, expected_host=host)
        if args.manager_probe:
            print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps({
                "schema": SCHEMA, "phase": "READ_ONLY_MANAGER_PAIRING_PROBE",
                "source_sha": args.source_sha, "device_id": args.device_id,
                "manager_alias": args.manager_alias, "manager_port": args.manager_port,
                "paired": True, "device_match": True,
                "bootstrap_version_observed": status["bootstrap"].get("version"),
                "runtime_state_observed": status.get("runtime", {}).get("state"),
                "b1": "NOT_RUN", "b2_v1": "NOT_RUN", "b2_v3": "NOT_RUN",
                "install": "NOT_RUN", "fpga": "NOT_RUN", "dut": "NOT_RUN",
            }, sort_keys=True, separators=(",", ":")))
            return 0
        report = run(api, module, source_sha=args.source_sha, target=target,
                     expected_device_id=args.device_id)
        print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps(
            report, sort_keys=True, separators=(",", ":"),
        ))
        return 0 if report["b1"]["status"] == "PASS" else 1
    except Exception as exc:
        # Only print reviewed static errors; no response body or credentials.
        print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps({
            "schema": SCHEMA, "b1": "NOT_RUN",
            "b2_v1": "NOT_RUN", "b2_v3": "NOT_RUN",
            "code": str(exc) if isinstance(exc, BaselineError) else type(exc).__name__,
            "result": "NOT_RUN",
        }, sort_keys=True, separators=(",", ":")))
        return 69


if __name__ == "__main__":
    raise SystemExit(main())

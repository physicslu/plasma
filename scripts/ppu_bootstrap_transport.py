#!/usr/bin/env python3
"""Execution-path-neutral PPU Bootstrap credential acquisition and transport.

Shared by the Bundle programming/commissioning CLI (``plasma_program.py``) and
the Path 2 hardware baseline. Nothing here depends on Path 2, Path 3, a
GitHub Runner or a Work Order: the caller's own OS rights, the enrolled
owner-approved SSH route and the PPU's request authentication decide.

* ``existing_bootstrap_token_via_z2_ssh`` reads the EXISTING device-bound
  controller credential into memory over the pinned SSH/sudo route. It never
  provisions, rotates, copies, prints or persists it.
* ``DirectSSHAuthenticatedBootstrap`` is the private-LAN commissioning HTTP
  client: every request is MAC-signed, every response must carry a PPU proof.
"""
from __future__ import annotations

import base64
import http.client
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
HOST_ENV = "PLASMA_PPU_COMMISSIONING_ALLOWED_IP"


class BootstrapTransportError(RuntimeError):
    pass


def private_ipv4(host: str) -> str:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise BootstrapTransportError("PPU_IP_LITERAL_REQUIRED") from exc
    if (addr.version != 4 or not addr.is_private or addr.is_loopback
            or addr.is_link_local or addr.is_multicast or addr.is_unspecified):
        raise BootstrapTransportError("PPU_PRIVATE_LAN_ONLY")
    # The physically enrolled development Z2 is 192.168.2.99.
    # An explicit local operator-controlled env pin may override for a
    # separately enrolled PPU. Never accept an arbitrary Work Order URL.
    if host != os.environ.get(HOST_ENV, "192.168.2.99"):
        raise BootstrapTransportError("PPU_ALLOWED_IP_PIN_MISSING_OR_MISMATCH")
    return host



# Only the local Z2 process can access this file; Engineering Mode uses
# the pre-existing worker SSH/sudo enrollment and an exact trusted host key.
# Do not place the returned secret into any GitHub Work Order, log or file.
_TOKEN_REMOTE_READ = """
import base64, json, os, stat, sys
path = "/var/lib/plasma-bootstrap/controller/controller.json"
try:
    if os.geteuid() != 0:
        raise RuntimeError()
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o077 or not 32 <= metadata.st_size <= 65536:
        raise RuntimeError()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        data = os.read(fd, 65537)
    finally:
        os.close(fd)
    token = json.loads(data)["credential"].encode("ascii")
    if not 32 <= len(token) <= 256 or any(ch <= 32 or ch > 126 for ch in token):
        raise RuntimeError()
    sys.stdout.write("PLASMA_BOOTSTRAP_MATERIAL:" + base64.b64encode(token).decode("ascii") + "\\n")
except Exception:
    sys.stderr.write("PLASMA_BOOTSTRAP_MATERIAL_NOT_ACCESSIBLE\\n")
    sys.exit(77)
"""


def existing_bootstrap_token_via_z2_ssh(host: str, *, helper=None) -> str:
    """Fetch existing token in memory, via pinned SSH and existing sudo route.

    The raw SSH output is private process data: never forward it, including
    on failure. No provisioning, rotation, copy or persistent SWPC token file.
    """
    host = private_ipv4(host)
    if helper is None:
        spec = importlib.util.spec_from_file_location(
            "ppu_baseline_existing_z2_ssh", ROOT / "scripts/plasma_wordport_program.py"
        )
        if spec is None or spec.loader is None:
            raise BootstrapTransportError("Z2_EXISTING_SSH_HELPER_UNAVAILABLE")
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
    try:
        credentials, known_hosts = helper.z2_login_credentials(Path.home())
    except Exception:
        raise BootstrapTransportError("Z2_ENROLLED_SSH_CREDENTIAL_UNAVAILABLE") from None
    if credentials.get("ssh_host") != host:
        raise BootstrapTransportError("Z2_ENROLLED_SSH_HOST_NOT_APPROVED_TARGET")
    try:
        rc, output = helper.password_ssh_z2(
            ["python3", "-I", "-c", _TOKEN_REMOTE_READ],
            credentials, known_hosts, timeout=45,
        )
    except Exception:
        raise BootstrapTransportError("Z2_ENROLLED_SSH_OPERATION_UNAVAILABLE") from None
    if rc != 0:
        raise BootstrapTransportError("Z2_BOOTSTRAP_TOKEN_ACCESS_DENIED")
    matches = re.findall(r"PLASMA_BOOTSTRAP_MATERIAL:([A-Za-z0-9+/=]{44,360})", output)
    if len(matches) != 1:
        raise BootstrapTransportError("Z2_BOOTSTRAP_TOKEN_RESPONSE_INVALID")
    try:
        material = base64.b64decode(matches[0], validate=True)
        token = material.decode("ascii")
    except (ValueError, UnicodeError):
        raise BootstrapTransportError("Z2_BOOTSTRAP_TOKEN_RESPONSE_INVALID") from None
    if not (32 <= len(token) <= 256 and all(33 <= ord(c) <= 126 for c in token)):
        raise BootstrapTransportError("Z2_BOOTSTRAP_TOKEN_RESPONSE_INVALID")
    return token


class DirectSSHAuthenticatedBootstrap:
    """Private-LAN Z2 Bootstrap admission with SSH-acquired in-memory secret.

    This is explicitly commissioning HTTP, not production authenticated TLS.
    Never derives authorization from the package or a Manager pairing.
    """
    def __init__(self, host: str, *, module, token: str, connection_factory=None):
        self.host = private_ipv4(host)
        self.module = module
        self._token = token
        self._device = None
        self._auth = module._request_auth_module()
        self._connection_factory = connection_factory or http.client.HTTPConnection
        self._physical_direct_baseline = True

    def _send(self, method: str, path: str, raw: bytes | None, headers: Mapping[str, str]):
        conn = self._connection_factory(self.host, 18081, timeout=15)
        try:
            conn.request(method, path, body=raw, headers=dict(headers))
            response = conn.getresponse()
            data = response.read(2 * 1024 * 1024 + 1)
            status = response.status
            response_headers = dict(response.getheaders())
        finally:
            conn.close()
        if len(data) > 2 * 1024 * 1024:
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_RESPONSE_TOO_LARGE")
        return status, data, response_headers

    def _call(self, method: str, path: str, body: Mapping[str, object] | None):
        if (method not in ("GET", "POST")
                or not re.fullmatch(
                    r"/v1/(status|assets|deployment|uploads(?:/[0-9a-f]{32}/(?:chunks|commit))?|deployments)",
                    path)):
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_ROUTE_DENIED")
        if method == "POST" and path not in ("/v1/uploads", "/v1/deployments") and not path.startswith("/v1/uploads/"):
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_WRITE_DENIED")
        raw = (json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
               if body is not None else None)
        if raw is not None and len(raw) > 2 * 1024 * 1024:
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_REQUEST_TOO_LARGE")
        # Mutual request authentication: the in-memory credential never
        # crosses the wire; only a PPU-MACed response is accepted.
        header, context = self.module.BootstrapAPIClient._sign(self, method, path, raw)
        status, data, response_headers = self._send(method, path, raw, {
            "Authorization": header,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if raw is not None else {}),
        })
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
        proof = next((value for key, value in response_headers.items()
                      if key.lower() == self._auth.RESPONSE_HEADER.lower()), None)
        try:
            self._auth.verify_response(credential=self._token, context=context,
                                       status=status, body=data, header=proof)
        except self._auth.RequestAuthError:
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_RESPONSE_UNAUTHENTICATED") from None
        try:
            response_data = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_RESPONSE_INVALID") from None
        if type(response_data) is not dict:
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_RESPONSE_INVALID")
        if path == "/v1/status":
            # Existing physical Z2 status_document has no top-level ok flag.
            if (type(response_data.get("identity")) is not dict
                    or type(response_data.get("bootstrap")) is not dict
                    or type(response_data.get("runtime")) is not dict):
                raise BootstrapTransportError("DIRECT_BOOTSTRAP_STATUS_INVALID")
        elif response_data.get("ok") is not True:
            raise BootstrapTransportError("DIRECT_BOOTSTRAP_RESPONSE_INVALID")
        return response_data

    def status(self):
        return self._call("GET", "/v1/status", None)

    def upload(self, archive):
        return self.module.BootstrapAPIClient.upload(self, archive)

    def submit(self, *, kind, upload_id, **kwargs):
        return self.module.BootstrapAPIClient.submit(
            self, kind=kind, upload_id=upload_id, **kwargs,
        )

    # Direct paired client issues its own Owner Operation Authorization.
    def _device_id(self):
        return self.module.BootstrapAPIClient._device_id(self)

    def _authorize(self, action, subject_sha256, transaction_id):
        return self.module.BootstrapAPIClient._authorize(
            self, action, subject_sha256, transaction_id)

    def _admission_body(self, kind, upload_id, archive_sha256):
        return self.module.BootstrapAPIClient._admission_body(
            self, kind, upload_id, archive_sha256)

    def deployment_state(self, transaction_id):
        return self.module.BootstrapAPIClient.deployment_state(self, transaction_id)

    # Bundle v3 asset operations of the same paired client (B2/B3).
    def _install_body(self, admitted, mode, fpga_load):
        return self.module.BootstrapAPIClient._install_body(self, admitted, mode, fpga_load)

    def install_bundle(self, admitted, *, mode, fpga_load):
        return self.module.BootstrapAPIClient.install_bundle(
            self, admitted, mode=mode, fpga_load=fpga_load)

    def assets_status(self):
        return self.module.BootstrapAPIClient.assets_status(self)

    def reconcile_bundle_assets(self, archive, *, fpga_load):
        return self.module.BootstrapAPIClient.reconcile_bundle_assets(
            self, archive, fpga_load=fpga_load)

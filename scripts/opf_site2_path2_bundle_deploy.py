#!/usr/bin/env python3
"""Path 2: replace retired Site 2 OPF Gen7 Bundle via Bootstrap B1/B2/B3.

One owner-authorized, non-root SWPC operator action. Read-only source extraction
from an exact immutable Z2 Gen7 Set; no in-place changes, FPGA reload, flash,
Service restart, OS policy change or OpenOCD Engine switch. Fail closed on any
ambiguous transport/receipt; never automatically re-submit a mutating step.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import opf_platform_bundle_v3_build as builder

ROOT = Path(__file__).resolve().parents[1]
OLD_SHA = "4efe0fea45cd71e48f4de53318f4a4fb863c2332bab8a04affbcdd26fce52a8d"
PROVIDER = "openocd-platform-reference"
PROFILE = "stm32f103c8t6-site2"

# This code runs *read-only* under Z2's existing privileged maintenance path.
# Never print secrets or user-supplied content from Z2.
REMOTE_SOURCE = """
import base64,hashlib,json
from pathlib import Path
base=Path('/opt/plasma/assets/staged/4efe0fea45cd71e48f4de53318f4a4fb863c2332bab8a04affbcdd26fce52a8d')
manifest=json.loads((base/'manifest.json').read_bytes())
assert manifest['schema']=='plasma.ppu.bundle.v3'
pkgs={p['id']:p for p in manifest['packages']}
assert {'openocd-platform-reference','stm32f103c8t6-site2'}<=set(pkgs)
provider=pkgs['openocd-platform-reference']
profile=pkgs['stm32f103c8t6-site2']
assert provider['kind']=='platform-provider' and profile['kind']=='programming-profile'
assert profile['requires']==['openocd-platform-reference']
wanted={
 'plasma-provider-options.json': ('openocd-platform-reference','data/plasma-provider-options.json'),
 'plasma-provider.json': ('stm32f103c8t6-site2','data/plasma-provider.json'),
 'plasma-flash-profile.json': ('stm32f103c8t6-site2','data/plasma-flash-profile.json'),
}
result={}
for name,(package_id,rel) in wanted.items():
 p=pkgs[package_id]
 path='payload/packages/'+package_id+'/'+rel
 entry=[e for e in p['files'] if e['path']==path]
 assert len(entry)==1 and entry[0]['executable'] is False
 file=base/path
 assert file.is_file() and not file.is_symlink()
 raw=file.read_bytes()
 assert 0<len(raw)<=8192 and len(raw)==entry[0]['size']
 assert hashlib.sha256(raw).hexdigest()==entry[0]['sha256']
 result[name]=base64.b64encode(raw).decode('ascii')
 data=json.loads(raw)
 assert type(data) is dict
payload={'target':manifest['target'],'files':result}
print('PLASMA_OPF_GEN7_SOURCE:'+base64.b64encode(json.dumps(payload).encode()).decode())
"""


class DeployDenied(RuntimeError):
    pass


def _load(path: str, name: str):
    source = ROOT / "scripts" / path
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None or source.is_symlink():
        raise DeployDenied("TRUSTED_MODULE_NOT_AVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def retrieve_source(host: str, *, helper) -> dict:
    credentials, hosts = helper.z2_login_credentials(Path.home())
    if credentials["ssh_host"] != host:
        raise DeployDenied("APPROVED_Z2_HOST_MISMATCH")
    rc, transcript = helper.password_ssh_z2(
        ["python3", "-I", "-c", REMOTE_SOURCE], credentials, hosts, timeout=60)
    if rc != 0:
        raise DeployDenied("Z2_GEN7_SOURCE_READ_DENIED")
    matches = re.findall(r"PLASMA_OPF_GEN7_SOURCE:([A-Za-z0-9+/=]{80,60000})", transcript)
    if len(matches) != 1:
        raise DeployDenied("Z2_SOURCE_RECEIPT_INVALID")
    try:
        payload = json.loads(base64.b64decode(matches[0], validate=True))
        assert type(payload) is dict and set(payload) == {"target", "files"}
        assert type(payload["files"]) is dict and set(payload["files"]) == builder.SOURCE_FILES
    except (ValueError, AssertionError, UnicodeError, KeyError) as exc:
        raise DeployDenied("Z2_SOURCE_RECEIPT_INVALID") from exc
    return payload


def run(host: str) -> dict:
    helper = _load("plasma_wordport_program.py", "opf_site2_path2_ssh")
    common = _load("ppu_path2_hardware_baseline.py", "opf_site2_path2_bootstrap")
    source = retrieve_source(host, helper=helper)
    with tempfile.TemporaryDirectory(prefix="plasma-opf-site2-path2-") as temp:
        root = Path(temp)
        inputs = root / "source"
        inputs.mkdir()
        for name, encoded in source["files"].items():
            (inputs / name).write_bytes(base64.b64decode(encoded, validate=True))
        bundle = root / "site2-opf-v3.zip"
        digest = builder.build_bundle(
            inputs, bundle, target=source["target"], provider_id=PROVIDER,
            profile_id=PROFILE, bundle_name="site2-opf-profile-only", version="1.0.0")
        raw = bundle.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest or digest == OLD_SHA:
            raise DeployDenied("NEW_BUNDLE_IDENTITY_INVALID")

        # The already-enrolled owner authorization is consumed only in memory.
        token = common._existing_bootstrap_token_via_z2_ssh(host)
        client_module = common._load_client()

        class BootstrapClient(common.DirectSSHAuthenticatedBootstrap):
            def _install_body(self, admitted, mode, fpga_load):
                return self.module.BootstrapAPIClient._install_body(
                    self, admitted, mode, fpga_load)

            def install_bundle(self, admitted, *, mode, fpga_load):
                return self.module.BootstrapAPIClient.install_bundle(
                    self, admitted, mode=mode, fpga_load=fpga_load)

        api = BootstrapClient(host, module=client_module, token=token)
        # Do not retry after any ambiguous mutating operation.
        uploaded = api.upload(raw)
        admitted = api.submit(kind="bundle", upload_id=uploaded, archive_sha256=digest)
        if admitted.state != "admitted":
            raise DeployDenied("B2_NOT_ADMITTED")
        installed = api.install_bundle(admitted, mode="activate", fpga_load=False)
        deadline = time.monotonic() + 240
        while True:
            receipt = api.deployment_state(installed.transaction_id)
            state = receipt["state"]
            if state in ("succeeded", "failed", "recovery_required"):
                break
            if time.monotonic() >= deadline:
                raise DeployDenied("B3_OBSERVATION_TIMEOUT_DO_NOT_RESUBMIT")
            time.sleep(2)
        if state != "succeeded":
            raise DeployDenied("B3_" + state.upper())
        details = receipt.get("result") or {}
        if details.get("result") != "PASS":
            raise DeployDenied("B3_PASS_RECEIPT_MISSING")
        return {
            "result": "PASS", "route": "PATH2_SWPC_TO_BOOTSTRAP_B1_B2_B3",
            "new_asset_set_sha256": digest, "previous_asset_set_sha256": OLD_SHA,
            "b2_transaction_id": admitted.transaction_id,
            "b3_transaction_id": installed.transaction_id,
            "b3_state": state, "fpga_reload": "NOT_RUN",
            "dut_flash": "NOT_RUN",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    args = parser.parse_args()
    status = {"result": "NOT_RUN", "route": "PATH2_SWPC_TO_BOOTSTRAP_B1_B2_B3"}
    try:
        if not re.fullmatch(r"(?:10|192\.168|172\.(?:1[6-9]|2[0-9]|3[01]))\.(?:[0-9]{1,3}\.)?[0-9]{1,3}", args.host):
            raise DeployDenied("TARGET_PRIVATE_IP_REQUIRED")
        status = run(args.host)
        rc = 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, DeployDenied) else type(exc).__name__
        status["result"] = "FAIL_OR_NOT_RUN"
        status["error_code"] = code
        status["warning"] = "Do not re-submit without reconciling B1/B2/B3 receipt"
        rc = 1
    print("PLASMA_SITE2_PATH2_DEPLOY_JSON=" + json.dumps(status, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

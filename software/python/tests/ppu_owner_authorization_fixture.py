"""Host-only paired-owner fixture: a Bootstrap credential + device identity.

Mirrors the real chain (paired Console -> Manager -> PPU) by issuing ONE
Owner Operation Authorization per explicit operation. Never shipped and
never a per-Bundle allowlist.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OWNER_TOKEN = "owner-paired-console-credential-" + "q" * 16
MACHINE_ID = "0123456789abcdef0123456789abcdef"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


owner = _load("plasma_owner_authorization_fixture_module", "ppu_owner_authorization.py")
_identity = _load("plasma_owner_fixture_bootstrap_identity", "ppu-bootstrap.py")


def machine_id_file(tmp_path: Path) -> Path:
    path = Path(tmp_path) / "owner-machine-id"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MACHINE_ID + "\n", encoding="utf-8")
    return path


def device_id(paths) -> str:
    return _identity._machine_device_id(paths.machine_id_path)


def provision_owner(paths, *, token: str = OWNER_TOKEN) -> str:
    """Enroll this Host-only PPU: current controller credential (same as B1 auth)."""
    from .ppu_controller_fixture import current_credential, seed_controller
    existing = current_credential(paths.state_root)
    return existing if existing is not None else seed_controller(paths.state_root, token)


def authorize(paths, action: str, subject_sha256: str, transaction_id: str, *,
              package_identity_sha256: str | None = None,
              token: str | None = None, device: str | None = None) -> dict:
    credential = token if token is not None else provision_owner(paths)
    return owner.issue(
        credential=credential, action=action,
        device_id=device if device is not None else device_id(paths),
        subject_sha256=subject_sha256, transaction_id=transaction_id,
        package_identity_sha256=package_identity_sha256,
    )


def admit_body(paths, kind: str, upload_id: str, **overrides) -> dict:
    """B2 request for the committed upload's exact SHA256."""
    meta = json.loads((paths.uploads_root / f"{upload_id}.json").read_text())
    return {"kind": kind, "upload_id": upload_id,
            "authorization": authorize(paths, owner.ADMIT, meta["sha256"], upload_id,
                                       **overrides)}


def install_body(paths, b2_record: dict, *, fpga_load: bool,
                 mode: str | None = None, **overrides) -> dict:
    """B3 request bound to the CURRENT B2 transaction and its archive SHA256."""
    plan = b2_record["result"]["plan"]
    if mode is None:
        mode = "activate" if fpga_load else "stage_only"
    action = (owner.ACTIVATE_FPGA_LOAD if fpga_load else
              owner.ACTIVATE if mode == "activate" else owner.INSTALL)
    return {"kind": "bundle", "upload_id": b2_record["upload_id"],
            "mode": mode, "fpga_load": fpga_load,
            "authorization": authorize(paths, action, plan["archive_sha256"],
                                       b2_record["transaction_id"], **overrides)}


def install_summary(subject_sha256: str, *, action: str = "bundle.install",
                    transaction_id: str = "c" * 32) -> dict:
    """Verified owner install summary for the Host-only Deployment Engine sim."""
    claims = owner.issue(
        credential=OWNER_TOKEN, action=action, device_id="ppu-device-" + "0" * 24,
        subject_sha256=subject_sha256, transaction_id=transaction_id,
    )
    return owner.verify(
        claims, credential=OWNER_TOKEN, action=action,
        device_id="ppu-device-" + "0" * 24, subject_sha256=subject_sha256,
        transaction_id=transaction_id,
    )

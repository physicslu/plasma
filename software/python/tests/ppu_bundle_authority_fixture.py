"""Host-only device-local Bundle approval provisioner; never shipped as factory authority."""
from __future__ import annotations
import hashlib
import io
import json
import zipfile
from pathlib import Path

def provision_fixture_grant(paths, archive: bytes, *, digest=None) -> dict:
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        manifest = json.loads(source.read("manifest.json"))
    if manifest.get("schema") != "plasma.ppu.bundle.v3":
        raise ValueError("not canonical Bundle v3")
    policy = {
        "schema": "plasma.ppu.bundle-authority.v2",
        "generation": 1,
        "approved_bundle_sha256": [digest or hashlib.sha256(archive).hexdigest()],
    }
    path: Path = paths.bundle_authority_policy
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy), encoding="utf-8")
    path.chmod(0o600)
    return policy

def maybe_provision_fixture_grant(paths, archive: bytes) -> None:
    try:
        provision_fixture_grant(paths, archive)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        pass

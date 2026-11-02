"""Isolated test-only Master provisioner; never included in PPU factory scripts.

Tests explicitly create a private root/service-owned exact-digest grant
independent of the Bundle. Real devices MUST receive these grants through
a separately controlled, audited local Master provisioning process.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path


def provision_fixture_grant(paths, archive: bytes, *, expires_epoch_s=4102444800,
                            allow_kinds=None, digest=None) -> dict:
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        manifest = json.loads(source.read("manifest.json"))
    if manifest.get("schema") != "plasma.ppu.bundle.v3":
        raise ValueError("not canonical Bundle v3")
    kinds = sorted({p["kind"] for p in manifest["packages"]})
    policy = {
        "schema": "plasma.ppu.bundle-authority.v1",
        "master_generation": 1,
        "authorizations": [{
            "publisher": "open4th-test-master",
            "archive_sha256": digest or hashlib.sha256(archive).hexdigest(),
            "source_commit": manifest["source_commit"],
            "target": dict(manifest["target"]),
            "purpose": manifest["purpose"],
            "allowed_kinds": list(allow_kinds) if allow_kinds is not None else kinds,
            "expires_epoch_s": expires_epoch_s,
        }],
    }
    path: Path = paths.bundle_authority_policy
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy), encoding="utf-8")
    path.chmod(0o600)
    return policy


def maybe_provision_fixture_grant(paths, archive: bytes) -> None:
    # Format-negative tests intentionally upload malformed/noncanonical ZIP.
    # Their verifier must reject the bytes before authority is considered.
    try:
        provision_fixture_grant(paths, archive)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        pass

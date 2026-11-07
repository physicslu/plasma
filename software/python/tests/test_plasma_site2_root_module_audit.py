"""Host-only checks for the read-only installed Root module identity audit."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "plasma_site2_root_module_audit",
    ROOT / "scripts/plasma_site2_root_module_audit.py",
)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

SHA = "a" * 40


class Helper:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def z2_login_credentials(self, home):
        return {"ssh_host": "192.168.2.99"}, Path("/tmp/pinned-hosts")

    def password_ssh_z2(self, command, credentials, hosts, timeout):
        self.calls.append(command)
        return 0, audit.MARK + json.dumps(self.payload) + "\n"


def observed(root_sha, admission_sha):
    return {
        "schema": audit.SCHEMA, "observation": "OBSERVED",
        "manifest": "PARSED", "manifest_sha256": "e" * 64,
        "modules": {
            audit.FILES[0]: {
                "sha256": root_sha, "manifest_sha256": root_sha,
                "manifest_match": True,
                "references_devmem_independent_images": True,
            },
            audit.FILES[1]: {
                "sha256": admission_sha,
                "manifest_sha256": admission_sha,
                "manifest_match": True,
                "references_devmem_independent_images": False,
            },
        },
    }


def test_static_comparison_is_source_pinned_and_read_only():
    git_root = hashlib.sha256((ROOT / audit.FILES[0]).read_bytes()).hexdigest()
    git_admission = hashlib.sha256((ROOT / audit.FILES[1]).read_bytes()).hexdigest()
    helper = Helper(observed("f" * 64, git_admission))
    with patch.object(audit.subprocess, "run", return_value=SimpleNamespace(stdout=SHA + "\n")):
        result = audit.run(SHA, helper=helper)
    assert result["result"] == "OBSERVED"
    assert result["modules"][audit.FILES[0]]["matches_git"] is False
    assert result["modules"][audit.FILES[0]]["matches_installed_manifest"] is True
    assert result["modules"][audit.FILES[1]]["matches_git"] is True
    assert result["modules"][audit.FILES[0]]["references_devmem_independent_images"] is True
    assert helper.calls[0][:3] == ["python3", "-I", "-c"]
    assert "read_bytes()" in helper.calls[0][3]
    assert result["flash"] == "NOT_RUN" and result["deployment"] == "NOT_RUN"


def test_missing_source_pin_fails_before_ssh():
    helper = Helper(observed("f" * 64, "e" * 64))
    with patch.object(audit.subprocess, "run", return_value=SimpleNamespace(stdout=SHA + "\n")):
        with pytest.raises(ValueError, match="SOURCE_SHA_MISMATCH"):
            audit.run("b" * 40, helper=helper)
    assert not helper.calls


def test_broken_protected_manifest_never_claims_observed():
    payload = observed("f" * 64, "e" * 64)
    payload["observation"] = "BLOCKED"
    helper = Helper(payload)
    with patch.object(audit.subprocess, "run", return_value=SimpleNamespace(stdout=SHA + "\n")):
        with pytest.raises(RuntimeError, match="ROOT_AUDIT_INCOMPLETE"):
            audit.run(SHA, helper=helper)

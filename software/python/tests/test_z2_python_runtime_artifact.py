from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "z2-python-runtime.py"
SPEC = importlib.util.spec_from_file_location("z2_python_runtime", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _arm_probe(version: tuple[int, int, int] = (3, 12, 13)) -> dict[str, object]:
    return {
        "version": list(version),
        "releaselevel": "final",
        "machine": "armv7l",
        "executable": "/opt/plasma/python/3.12.13/bin/python3",
        "openssl": "OpenSSL test",
        "sqlite": "3.test",
    }


def _fake_prefix(tmp_path: Path) -> Path:
    root = tmp_path / "prefix"
    binary = root / "bin" / "python3"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    (root / "lib" / "python3.12").mkdir(parents=True)
    (root / "lib" / "python3.12" / "os.py").write_text("# runtime fixture\n", encoding="utf-8")
    return root


def test_probe_contract_requires_final_armv7_python_311_or_newer() -> None:
    version, machine = MODULE._validated_probe(_arm_probe())
    assert version == "3.12.13"
    assert machine == "armv7l"

    with pytest.raises(MODULE.PythonRuntimeArtifactError, match="not ARMv7"):
        payload = _arm_probe()
        payload["machine"] = "x86_64"
        MODULE._validated_probe(payload)

    with pytest.raises(MODULE.PythonRuntimeArtifactError, match="older than required"):
        MODULE._validated_probe(_arm_probe((3, 10, 14)))

    with pytest.raises(MODULE.PythonRuntimeArtifactError, match="final release"):
        payload = _arm_probe()
        payload["releaselevel"] = "candidate"
        MODULE._validated_probe(payload)


def test_build_verify_and_install_round_trip_is_source_tree_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _fake_prefix(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr(MODULE, "_probe_python", lambda _path: _arm_probe())

    built = MODULE.build_artifact(
        python_root=prefix,
        output_dir=output,
        source_ref="cpython-v3.12.13",
    )
    artifact = Path(str(built["artifact"]))
    sidecar = Path(str(built["sidecar"]))
    assert artifact.is_file()
    assert sidecar.is_file()
    assert "linux-armv7l" in artifact.name

    verified = MODULE.verify_artifact(
        artifact,
        sidecar=sidecar,
        extract_to=tmp_path / "verify",
    )
    manifest = verified["manifest"]
    assert manifest["python_version"] == "3.12.13"
    assert manifest["architecture"] == "armv7l"
    assert manifest["ownership_boundary"] == {
        "replaces_pynq_python": False,
        "replaces_system_python": False,
    }

    monkeypatch.setattr(MODULE, "_require_target", lambda: None)
    product_root = tmp_path / "product"
    evidence = MODULE.install_artifact(
        artifact,
        sidecar=sidecar,
        product_root=product_root,
    )
    assert evidence["result"] == "PASS"
    assert evidence["architecture"] == "armv7l"
    assert str(evidence["python_path"]).startswith(str(product_root / "python" / "3.12.13"))
    retained = json.loads((product_root / "install" / "python-runtime.json").read_text(encoding="utf-8"))
    assert retained["artifact_sha256"] == evidence["artifact_sha256"]
    assert retained["ownership_boundary"]["replaces_system_python"] is False


def test_detached_hash_detects_artifact_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prefix = _fake_prefix(tmp_path)
    monkeypatch.setattr(MODULE, "_probe_python", lambda _path: _arm_probe())
    built = MODULE.build_artifact(
        python_root=prefix,
        output_dir=tmp_path / "out",
        source_ref="cpython-v3.12.13",
    )
    artifact = Path(str(built["artifact"]))
    sidecar = Path(str(built["sidecar"]))
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(MODULE.PythonRuntimeArtifactError, match="SHA-256 mismatch"):
        MODULE.verify_artifact(
            artifact,
            sidecar=sidecar,
            extract_to=tmp_path / "verify",
        )


def test_archive_rejects_symlink_members(tmp_path: Path) -> None:
    artifact = tmp_path / "bad.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        root = tarfile.TarInfo("plasma-python")
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        archive.addfile(root)
        link = tarfile.TarInfo("plasma-python/python/bin/python3")
        link.type = tarfile.SYMTYPE
        link.linkname = "/usr/bin/python3"
        link.mode = 0o755
        archive.addfile(link)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    sidecar = Path(str(artifact) + ".sha256")
    sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    with pytest.raises(MODULE.PythonRuntimeArtifactError, match="non-regular archive member"):
        MODULE.verify_artifact(
            artifact,
            sidecar=sidecar,
            extract_to=tmp_path / "verify",
        )

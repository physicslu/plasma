from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-bootstrap-kit.py"
SPEC = importlib.util.spec_from_file_location("ppu_bootstrap_kit", SCRIPT)
assert SPEC and SPEC.loader
kitmod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = kitmod
SPEC.loader.exec_module(kitmod)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_kit(tmp_path: Path, *, release_id="1.2.3-aaaaaaaaaaaa"):
    root = tmp_path / f"plasma-z2-ps-kit-{release_id}"
    (root / "scripts").mkdir(parents=True)
    (root / "artifacts").mkdir()
    (root / "docs").mkdir()
    for name in ("plasmactl", "plasmactl-z2-ps", "ppu-z2-installer.py", "z2-python-runtime.py"):
        (root / "scripts" / name).write_text(f"{name}\n", encoding="utf-8")
    ppu = root / "artifacts" / f"plasma-ppu-{release_id}-linux-armv7l.tar.gz"
    python = root / "artifacts" / "plasma-python-3.12.13-linux-armv7l.tar.gz"
    ppu.write_bytes(b"ppu")
    python.write_bytes(b"python")
    (Path(str(ppu) + ".sha256")).write_text(f"{_sha(ppu)}  {ppu.name}\n", encoding="utf-8")
    (Path(str(python) + ".sha256")).write_text(f"{_sha(python)}  {python.name}\n", encoding="utf-8")
    (root / "docs" / "README.md").write_text("docs\n", encoding="utf-8")

    files = sorted(path for path in root.rglob("*") if path.is_file())
    lines = [f"{_sha(path)}  {path.relative_to(root).as_posix()}" for path in files]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    archive = tmp_path / f"{root.name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=root.name)
    sidecar = Path(str(archive) + ".sha256")
    sidecar.write_text(f"{_sha(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, sidecar


def test_verify_canonical_kit(tmp_path: Path):
    archive, sidecar = _build_kit(tmp_path)
    verified = kitmod.verify_kit(archive, sidecar=sidecar, extract_to=tmp_path / "extract")
    assert verified.release_id == "1.2.3-aaaaaaaaaaaa"
    assert verified.ppu_artifact.name.startswith("plasma-ppu-")
    assert verified.python_artifact.name.startswith("plasma-python-")
    assert verified.kit_sha256 == _sha(archive)


def test_outer_digest_mismatch_fails_before_extract(tmp_path: Path):
    archive, sidecar = _build_kit(tmp_path)
    sidecar.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")
    with pytest.raises(kitmod.BootstrapKitError, match="does not match"):
        kitmod.verify_kit(archive, sidecar=sidecar, extract_to=tmp_path / "extract")
    assert not (tmp_path / "extract").exists()


def test_archive_traversal_is_rejected(tmp_path: Path):
    archive = tmp_path / "plasma-z2-ps-kit-1.0.0-aaaaaaaaaaaa.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("plasma-z2-ps-kit-1.0.0-aaaaaaaaaaaa/../escape")
        payload = b"bad"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    sidecar = Path(str(archive) + ".sha256")
    sidecar.write_text(f"{_sha(archive)}  {archive.name}\n", encoding="utf-8")
    with pytest.raises(kitmod.BootstrapKitError, match="non-canonical|unsafe"):
        kitmod.verify_kit(archive, sidecar=sidecar, extract_to=tmp_path / "extract")


def test_internal_file_set_is_exact(tmp_path: Path):
    archive, sidecar = _build_kit(tmp_path)
    extract = tmp_path / "first"
    verified = kitmod.verify_kit(archive, sidecar=sidecar, extract_to=extract)
    (verified.root / "unexpected.txt").write_text("drift", encoding="utf-8")
    with pytest.raises(kitmod.BootstrapKitError, match="file set"):
        kitmod._verify_internal_hashes(verified.root)


def test_install_uses_python_artifact_only_for_first_install(tmp_path: Path):
    archive, sidecar = _build_kit(tmp_path)
    verified = kitmod.verify_kit(archive, sidecar=sidecar, extract_to=tmp_path / "extract")
    product_root = tmp_path / "product"
    seen = []

    def runner(argv, **kwargs):
        seen.append(list(argv))
        evidence = product_root / "install" / "last-install.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({"result": "PASS", "release_id": verified.release_id}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok")

    result = kitmod.install_verified_kit(
        verified,
        gateway_host="192.168.2.99",
        ppu_id="ppu-01",
        facility_id="lab",
        display_name="PPU 01",
        product_root=product_root,
        runner=runner,
    )
    assert result["operation"] == "install"
    assert "--python-artifact" in seen[0]
    assert result["publisher_authenticity"] == "not_yet_qualified"
    assert result["fpga_update"] is False

    seen.clear()
    result = kitmod.install_verified_kit(
        verified,
        gateway_host="192.168.2.99",
        ppu_id="ppu-01",
        facility_id="lab",
        display_name="PPU 01",
        product_root=product_root,
        runner=runner,
    )
    assert result["operation"] == "deploy"
    assert "--python-artifact" not in seen[0]


def test_install_evidence_must_match_verified_kit(tmp_path: Path):
    archive, sidecar = _build_kit(tmp_path)
    verified = kitmod.verify_kit(archive, sidecar=sidecar, extract_to=tmp_path / "extract")
    product_root = tmp_path / "product"

    def runner(argv, **kwargs):
        evidence = product_root / "install" / "last-install.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({"result": "PASS", "release_id": "wrong"}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok")

    with pytest.raises(kitmod.BootstrapKitError, match="does not match"):
        kitmod.install_verified_kit(
            verified,
            gateway_host="192.168.2.99",
            ppu_id="ppu-01",
            facility_id="lab",
            display_name="PPU 01",
            product_root=product_root,
            runner=runner,
        )

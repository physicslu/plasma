from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "scripts" / "ppu-bootstrap-hil-negative.py"
KIT_TOOL = ROOT / "scripts" / "ppu-bootstrap-kit.py"
INSTALLER = ROOT / "scripts" / "ppu-z2-installer.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load(BUILDER, "test_ppu_bootstrap_hil_negative")
kitmod = _load(KIT_TOOL, "test_ppu_bootstrap_hil_negative_kit")
installer = _load(INSTALLER, "test_ppu_bootstrap_hil_negative_installer")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sums(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    (root / "SHA256SUMS").write_text(
        "\n".join(f"{_sha(path)}  {path.relative_to(root).as_posix()}" for path in files) + "\n",
        encoding="utf-8",
    )


def _source_kit(tmp_path: Path, release_id: str = "1.2.3-aaaaaaaaaaaa") -> tuple[Path, Path]:
    version, git_prefix = release_id.rsplit("-", 1)
    git_sha = git_prefix + "a" * (40 - len(git_prefix))

    release_root = tmp_path / "release-src" / "plasma-release"
    app = release_root / "runtime" / "ppu" / "ppu.pyz"
    catalog = release_root / "runtime" / "data" / "device-catalog" / "production" / "icpn-v1-manifest.json"
    app.parent.mkdir(parents=True)
    catalog.parent.mkdir(parents=True)
    app.write_text("print('source runtime')\n", encoding="utf-8")
    catalog.write_text("{}\n", encoding="utf-8")
    (release_root / "runtime" / "ppu-runtime.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "role": "ppu",
                "data": {"device_catalog_manifest": "data/device-catalog/production/icpn-v1-manifest.json"},
                "hardware_boundary": {
                    "loads_fpga": False,
                    "accesses_pl": False,
                    "changes_target_power": False,
                    "programs_real_ic": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (release_root / "release.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product": "plasma",
                "product_version": version,
                "git_sha": git_sha,
                "role": "ppu",
                "platform": "linux",
                "architecture": "armv7l",
                "target": "linux-armv7l",
                "archive_format": "tar.gz",
                "contracts": {"plasma_protocol": "3.3", "web_rest_api": "3"},
                "layout": {"runtime": "runtime"},
            }
        ),
        encoding="utf-8",
    )
    _write_sums(release_root)
    ppu_artifact = tmp_path / f"plasma-ppu-{release_id}-linux-armv7l.tar.gz"
    with tarfile.open(ppu_artifact, "w:gz") as archive:
        archive.add(release_root, arcname="plasma-release")
    ppu_sidecar = Path(str(ppu_artifact) + ".sha256")
    ppu_sidecar.write_text(f"{_sha(ppu_artifact)}  {ppu_artifact.name}\n", encoding="utf-8")

    kit_root = tmp_path / f"plasma-z2-ps-kit-{release_id}"
    scripts = kit_root / "scripts"
    artifacts = kit_root / "artifacts"
    docs = kit_root / "docs"
    scripts.mkdir(parents=True)
    artifacts.mkdir()
    docs.mkdir()
    for name in (
        "plasmactl",
        "plasmactl-z2-ps",
        "ppu-bootstrap-deployment.py",
        "ppu-z2-installer.py",
        "z2-python-runtime.py",
    ):
        (scripts / name).write_text(f"{name}\n", encoding="utf-8")
    (artifacts / ppu_artifact.name).write_bytes(ppu_artifact.read_bytes())
    (artifacts / ppu_sidecar.name).write_text(ppu_sidecar.read_text(encoding="utf-8"), encoding="utf-8")
    python_artifact = artifacts / "plasma-python-3.12.13-linux-armv7l.tar.gz"
    python_artifact.write_bytes(b"python")
    (Path(str(python_artifact) + ".sha256")).write_text(
        f"{_sha(python_artifact)}  {python_artifact.name}\n",
        encoding="utf-8",
    )
    (docs / "README.md").write_text("fixture\n", encoding="utf-8")
    _write_sums(kit_root)

    kit = tmp_path / f"{kit_root.name}.tar.gz"
    with tarfile.open(kit, "w:gz") as archive:
        archive.add(kit_root, arcname=kit_root.name)
    sidecar = Path(str(kit) + ".sha256")
    sidecar.write_text(f"{_sha(kit)}  {kit.name}\n", encoding="utf-8")
    return kit, sidecar


def test_negative_builder_preserves_admission_and_changes_only_runtime_behavior(tmp_path: Path):
    source, sidecar = _source_kit(tmp_path)
    source_verified = kitmod.verify_kit(source, sidecar=sidecar, extract_to=tmp_path / "source-verify")
    source_release = installer.verify_release(
        source_verified.ppu_artifact,
        sidecar=source_verified.ppu_sidecar,
        extract_to=tmp_path / "source-release-verify",
    )
    assert source_release.release_id == "1.2.3-aaaaaaaaaaaa"

    result = builder.derive_negative_kit(
        source,
        sidecar=sidecar,
        output_dir=tmp_path / "out",
        kit_tool_path=KIT_TOOL,
        installer_path=INSTALLER,
    )
    assert result["result"] == "PASS"
    assert result["qualification_only"] is True
    assert result["production_eligible"] is False
    assert result["source_release_id"] == source_release.release_id
    assert result["negative_release_id"].startswith("1.2.3-hil.rollback.negative-")
    assert result["failure_exit_code"] == 86
    assert result["expected_result"] == "activation-readiness-failure-followed-by-automatic-rollback"

    negative = Path(result["negative_kit"])
    negative_sidecar = Path(result["negative_kit_sidecar"])
    verified = kitmod.verify_kit(
        negative,
        sidecar=negative_sidecar,
        extract_to=tmp_path / "negative-kit-verify",
    )
    release = installer.verify_release(
        verified.ppu_artifact,
        sidecar=verified.ppu_sidecar,
        extract_to=tmp_path / "negative-release-verify",
    )
    assert verified.release_id == result["negative_release_id"]
    assert release.release_id == result["negative_release_id"]
    assert release.manifest["git_sha"] == source_release.manifest["git_sha"]
    qualification = release.manifest["qualification_only"]
    assert qualification["production_eligible"] is False
    assert qualification["source_release_id"] == source_release.release_id
    app = release.root / "runtime" / "ppu" / "ppu.pyz"
    text = app.read_text(encoding="utf-8")
    assert "PLASMA HIL NEGATIVE" in text
    assert "SystemExit(86)" in text
    assert "source runtime" not in text


def test_negative_builder_is_deterministic_and_refuses_to_rederive_negative_source(tmp_path: Path):
    assert builder._negative_version("1.2.3") == "1.2.3-hil.rollback.negative"
    assert builder._negative_version("1.2.3-rc.1") == "1.2.3-rc.1.hil.rollback.negative"
    assert builder._negative_version("1.2.3+build.4") == "1.2.3-hil.rollback.negative+build.4"
    try:
        builder._negative_version("1.2.3-hil.rollback.negative")
    except builder.HILNegativeError:
        pass
    else:
        raise AssertionError("qualification-only source must not be transformed again")

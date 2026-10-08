from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import sys
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "openocd-runtime.py"
METADATA = REPO_ROOT / "release" / "openocd.json"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-openocd-runtime.sh"
Z2_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "z2-ps-release.yml"
QEMU_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "z2like-demo-qemu.yml"
SPEC = importlib.util.spec_from_file_location("plasma_openocd_runtime", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SOURCE_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
RUNTIME_ID = "0.12.0-9ea7f3d647c8"


def _fake_elf(path: Path, machine: int = 62) -> None:
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    struct.pack_into("<H", header, 18, machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"fixture")
    path.chmod(0o755)


def _fake_prefix(tmp_path: Path) -> Path:
    prefix = tmp_path / "prefix"
    _fake_elf(prefix / "bin" / "openocd")
    (prefix / "share" / "openocd" / "scripts" / "target").mkdir(parents=True)
    (prefix / "share" / "openocd" / "scripts" / "interface").mkdir(parents=True)
    (prefix / "share" / "openocd" / "scripts" / "target" / "stm32f1x.cfg").write_text(
        "# fixture\n", encoding="utf-8"
    )
    return prefix


def test_release_metadata_pins_upstream_openocd_identity() -> None:
    payload = json.loads(METADATA.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "engine": "openocd",
        "version": "0.12.0",
        "source_repository": "https://github.com/openocd-org/openocd.git",
        "source_tag": "v0.12.0",
        "source_commit": SOURCE_COMMIT,
        "runtime_id": RUNTIME_ID,
        "install_root": f"/opt/plasma/programming-engines/openocd/{RUNTIME_ID}",
        "hardware_runtime_ready": False,
    }


def test_build_verify_install_round_trip_keeps_hardware_gate_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _fake_prefix(tmp_path)
    monkeypatch.setattr(MODULE.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        MODULE,
        "_probe_openocd",
        lambda _path: ("0.12.0", "Open On-Chip Debugger 0.12.0"),
    )
    monkeypatch.setattr(
        MODULE,
        "_ldd_dependencies",
        lambda _path: ["libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6"],
    )

    built = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "out",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )
    artifact = Path(str(built["artifact"]))
    sidecar = Path(str(built["sidecar"]))
    assert artifact.is_file()
    assert sidecar.is_file()
    assert built["runtime_id"] == RUNTIME_ID
    assert len(built["payload_sha256"]) == 64
    assert len(built["artifact_sha256"]) == 64
    assert built["hardware_runtime_ready"] is False

    verified = MODULE.verify_artifact(
        artifact,
        sidecar=sidecar,
        extract_to=tmp_path / "verify",
    )
    manifest = verified["manifest"]
    assert manifest["runtime_id"] == RUNTIME_ID
    assert manifest["payload_sha256"] == built["payload_sha256"]
    assert manifest["architecture"] == "x86_64"
    assert manifest["qualification_boundary"] == {
        "hardware_runtime_ready": False,
        "starts_openocd_service": False,
        "qualifies_swd_jtag": False,
        "qualifies_target_power_reset": False,
        "qualifies_real_ic": False,
    }

    monkeypatch.setattr(MODULE, "_require_install_target", lambda architecture: architecture)
    product_root = tmp_path / "product"
    evidence = MODULE.install_artifact(
        artifact,
        sidecar=sidecar,
        product_root=product_root,
    )
    binary = (
        product_root
        / "programming-engines"
        / "openocd"
        / RUNTIME_ID
        / "bin"
        / "openocd"
    )
    assert binary.is_file()
    assert evidence["binary"] == str(binary)
    assert evidence["hardware_runtime_ready"] is False
    retained = json.loads(
        (product_root / "install" / "openocd-runtime.json").read_text(encoding="utf-8")
    )
    assert retained["artifact_sha256"] == evidence["artifact_sha256"]
    assert retained["payload_sha256"] == built["payload_sha256"]
    assert retained["starts_openocd_service"] is False
    assert retained["qualification_boundary"]["hardware_runtime_ready"] is False


def test_build_is_reproducible_for_identical_payload_bytes_despite_mtime_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _fake_prefix(tmp_path)
    monkeypatch.setattr(MODULE.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        MODULE,
        "_probe_openocd",
        lambda _path: ("0.12.0", "Open On-Chip Debugger 0.12.0"),
    )
    monkeypatch.setattr(MODULE, "_ldd_dependencies", lambda _path: ["libc.so.6"])

    binary = prefix / "bin" / "openocd"
    os.utime(binary, (1_600_000_000, 1_600_000_000))
    first = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "out-a",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )

    os.utime(binary, (1_700_000_000, 1_700_000_000))
    second = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "out-b",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )

    first_artifact = Path(str(first["artifact"]))
    second_artifact = Path(str(second["artifact"]))
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first_artifact.read_bytes() == second_artifact.read_bytes()
    assert first["packaging_policy"] == "normalized-tar-gzip-v1"

    with tarfile.open(first_artifact, "r:gz") as archive:
        members = archive.getmembers()
    assert members
    assert all(member.mtime == 0 for member in members)
    assert all(member.uid == 0 and member.gid == 0 for member in members)
    assert all(member.uname == "" and member.gname == "" for member in members)
    archive_root = next(member for member in members if member.name.rstrip("/") == "plasma-openocd")
    assert archive_root.mode == 0o755


def test_payload_identity_includes_directory_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _fake_prefix(tmp_path)
    monkeypatch.setattr(MODULE.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        MODULE,
        "_probe_openocd",
        lambda _path: ("0.12.0", "Open On-Chip Debugger 0.12.0"),
    )
    monkeypatch.setattr(MODULE, "_ldd_dependencies", lambda _path: ["libc.so.6"])

    first = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "mode-a",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )
    target_dir = prefix / "share" / "openocd" / "scripts" / "target"
    target_dir.chmod(0o750)
    second = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "mode-b",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )

    assert first["payload_sha256"] != second["payload_sha256"]
    assert first["artifact_sha256"] != second["artifact_sha256"]

    prefix.chmod(0o750)
    third = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "mode-c",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )
    assert second["payload_sha256"] != third["payload_sha256"]
    assert second["artifact_sha256"] != third["artifact_sha256"]


def test_reinstall_rejects_tampered_existing_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _fake_prefix(tmp_path)
    monkeypatch.setattr(MODULE.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        MODULE,
        "_probe_openocd",
        lambda _path: ("0.12.0", "Open On-Chip Debugger 0.12.0"),
    )
    monkeypatch.setattr(MODULE, "_ldd_dependencies", lambda _path: ["libc.so.6"])
    monkeypatch.setattr(MODULE, "_require_install_target", lambda architecture: architecture)

    built = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "out",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )
    artifact = Path(str(built["artifact"]))
    sidecar = Path(str(built["sidecar"]))
    product_root = tmp_path / "product"
    MODULE.install_artifact(artifact, sidecar=sidecar, product_root=product_root)

    installed_target = (
        product_root
        / "programming-engines"
        / "openocd"
        / RUNTIME_ID
        / "share"
        / "openocd"
        / "scripts"
        / "target"
        / "stm32f1x.cfg"
    )
    installed_target.write_text("# tampered\n", encoding="utf-8")

    with pytest.raises(
        MODULE.OpenOCDRuntimeArtifactError,
        match="existing OpenOCD runtime content does not match",
    ):
        MODULE.install_artifact(artifact, sidecar=sidecar, product_root=product_root)


def test_detached_hash_detects_artifact_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _fake_prefix(tmp_path)
    monkeypatch.setattr(MODULE.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        MODULE,
        "_probe_openocd",
        lambda _path: ("0.12.0", "Open On-Chip Debugger 0.12.0"),
    )
    monkeypatch.setattr(MODULE, "_ldd_dependencies", lambda _path: ["libc.so.6"])

    built = MODULE.build_artifact(
        prefix=prefix,
        output_dir=tmp_path / "out",
        version="0.12.0",
        source_commit=SOURCE_COMMIT,
        architecture="x86_64",
    )
    artifact = Path(str(built["artifact"]))
    sidecar = Path(str(built["sidecar"]))
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(MODULE.OpenOCDRuntimeArtifactError, match="SHA-256 mismatch"):
        MODULE.verify_artifact(
            artifact,
            sidecar=sidecar,
            extract_to=tmp_path / "verify",
        )


def test_archive_rejects_symlink_members(tmp_path: Path) -> None:
    artifact = tmp_path / "bad.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        root = tarfile.TarInfo("plasma-openocd")
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        archive.addfile(root)
        link = tarfile.TarInfo("plasma-openocd/payload/bin/openocd")
        link.type = tarfile.SYMTYPE
        link.linkname = "/usr/bin/openocd"
        link.mode = 0o755
        archive.addfile(link)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    sidecar = Path(str(artifact) + ".sha256")
    sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    with pytest.raises(MODULE.OpenOCDRuntimeArtifactError, match="non-regular archive member"):
        MODULE.verify_artifact(
            artifact,
            sidecar=sidecar,
            extract_to=tmp_path / "verify",
        )


def test_build_recipe_uses_pinned_commit_and_minimal_control_plane_adapters() -> None:
    source = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "release/openocd.json" in source
    assert 'git fetch --depth 1 origin "$OPENOCD_SOURCE_COMMIT"' in source
    assert 'test "$(git rev-parse HEAD)" = "$OPENOCD_SOURCE_COMMIT"' in source
    assert "--enable-dummy" in source
    assert "--enable-remote-bitbang" in source
    assert "--disable-jlink" in source
    assert "python3 tcl" in source
    assert "adapter driver dummy" in source
    assert "ldd" in source
    assert "not found" in source


def test_z2_release_builds_both_openocd_architectures_and_packages_armv7() -> None:
    source = Z2_WORKFLOW.read_text(encoding="utf-8")
    assert "openocd-runtime:" in source
    assert "- x86_64" in source
    assert "- armv7l" in source
    assert "bash scripts/build-openocd-runtime.sh" in source
    assert "Install and execute on fresh matching Ubuntu 22.04 userspace" in source
    assert "plasma-openocd-*-linux-armv7l-" in source
    assert 'python "$root/scripts/openocd-runtime.py" verify' in source
    assert "hardware_runtime_ready" in source


def test_qemu_workflow_verifies_kit_deployed_armv7_openocd_without_hardware_claims() -> None:
    source = QEMU_WORKFLOW.read_text(encoding="utf-8")
    assert "Drive Manager to Bootstrap to QEMU deployment E2E" in source
    assert "Verify kit-deployed OpenOCD inside QEMU ARMv7 target" in source
    assert "Install and smoke packaged OpenOCD inside QEMU ARMv7 target" not in source
    assert "python3 /tmp/openocd-runtime.py install" not in source
    assert 'assert p["architecture"] == "armv7l"' in source
    assert 'assert p["hardware_runtime_ready"] is False' in source
    assert 'assert p["starts_openocd_service"] is False' in source
    assert '"adapter driver dummy"' in source

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "product-release.py"
spec = importlib.util.spec_from_file_location("product_release", SCRIPT)
assert spec is not None and spec.loader is not None
product_release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = product_release
spec.loader.exec_module(product_release)

GIT_SHA = "0123456789abcdef0123456789abcdef01234567"
BUILD_TIMESTAMP = "2026-08-30T00:00:00Z"


def make_runtime(tmp_path: Path, *, name: str = "runtime") -> Path:
    runtime = tmp_path / name
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "plasma-runtime.txt").write_text("runtime payload\n", encoding="utf-8")
    return runtime


def make_defaults(tmp_path: Path) -> Path:
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "plasma-defaults.json").write_text('{"mode":"product"}\n', encoding="utf-8")
    return defaults


def test_source_product_descriptor_matches_embedded_release_contract() -> None:
    descriptor = product_release._load_product_descriptor(REPO_ROOT)

    assert descriptor["product"] == "plasma"
    assert descriptor["product_version"] == "0.1.0"
    assert descriptor["role_contracts"] == product_release.ROLE_CONTRACTS


def test_build_and_verify_linux_control_station_tar_gz_with_clean_extraction(
    tmp_path: Path,
) -> None:
    runtime = make_runtime(tmp_path)
    defaults = make_defaults(tmp_path)
    output = tmp_path / "out"

    artifact = product_release.build_release(
        repo_root=REPO_ROOT,
        runtime_dir=runtime,
        config_defaults_dir=defaults,
        output_dir=output,
        role="control-station",
        platform_name="linux",
        architecture="x86_64",
        git_sha=GIT_SHA,
        build_timestamp=BUILD_TIMESTAMP,
    )

    assert artifact.name == "plasma-control-station-0.1.0-linux-x86_64.tar.gz"
    assert Path(str(artifact) + ".sha256").is_file()

    clean = tmp_path / "clean"
    result = product_release.verify_release(
        artifact,
        extract_to=clean,
        expect_role="control-station",
        expect_platform="linux",
        expect_architecture="x86_64",
        expect_version="0.1.0",
    )

    extracted = clean / "plasma-release"
    assert (extracted / "runtime" / "bin" / "plasma-runtime.txt").read_text(
        encoding="utf-8"
    ) == "runtime payload\n"
    assert (extracted / "config" / "defaults" / "plasma-defaults.json").is_file()
    manifest = json.loads((extracted / "release.json").read_text(encoding="utf-8"))
    assert manifest["archive_format"] == "tar.gz"
    assert manifest["components"] == {"python": "0.3.2", "web": "0.1.0"}
    assert manifest["contracts"] == {"web_rest_api": "3"}
    assert result["artifact_sha256"] == product_release._sha256_file(artifact)

    sums = (extracted / "SHA256SUMS").read_text(encoding="utf-8")
    assert "  release.json\n" in sums
    assert "  runtime/bin/plasma-runtime.txt\n" in sums


def test_windows_control_station_uses_zip_and_normalizes_amd64(tmp_path: Path) -> None:
    artifact = product_release.build_release(
        repo_root=REPO_ROOT,
        runtime_dir=make_runtime(tmp_path),
        output_dir=tmp_path / "out",
        role="control-station",
        platform_name="windows",
        architecture="AMD64",
        git_sha=GIT_SHA,
        build_timestamp=BUILD_TIMESTAMP,
    )

    assert artifact.name == "plasma-control-station-0.1.0-windows-x86_64.zip"
    result = product_release.verify_release(
        artifact,
        expect_role="control-station",
        expect_platform="windows",
        expect_architecture="AMD64",
    )
    assert result["archive_format"] == "zip"
    assert result["target"] == "windows-x86_64"


def test_ppu_release_has_ppu_contracts_and_python_component_only(tmp_path: Path) -> None:
    artifact = product_release.build_release(
        repo_root=REPO_ROOT,
        runtime_dir=make_runtime(tmp_path),
        output_dir=tmp_path / "out",
        role="ppu",
        platform_name="linux",
        architecture="armv7l",
        git_sha=GIT_SHA,
        build_timestamp=BUILD_TIMESTAMP,
    )

    result = product_release.verify_release(artifact)
    assert result["components"] == {"python": "0.3.2"}
    assert result["contracts"] == {
        "plasma_protocol": "3.3",
        "web_rest_api": "3",
    }


def test_unsupported_target_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(product_release.ReleaseError, match="unsupported release target"):
        product_release.build_release(
            repo_root=REPO_ROOT,
            runtime_dir=make_runtime(tmp_path),
            output_dir=tmp_path / "out",
            role="control-station",
            platform_name="windows",
            architecture="arm64",
            git_sha=GIT_SHA,
            build_timestamp=BUILD_TIMESTAMP,
        )


@pytest.mark.parametrize(
    "relative",
    [
        Path(".env"),
        Path("node_modules/pkg/index.js"),
        Path("tests/test_runtime.py"),
        Path("nested/.git/config"),
    ],
)
def test_build_rejects_secret_and_development_only_payload_paths(
    tmp_path: Path,
    relative: Path,
) -> None:
    runtime = tmp_path / "runtime"
    path = runtime / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("should not ship\n", encoding="utf-8")

    with pytest.raises(product_release.ReleaseError):
        product_release.build_release(
            repo_root=REPO_ROOT,
            runtime_dir=runtime,
            output_dir=tmp_path / "out",
            role="ppu",
            platform_name="linux",
            architecture="armv7l",
            git_sha=GIT_SHA,
            build_timestamp=BUILD_TIMESTAMP,
        )


def test_build_refuses_to_overwrite_immutable_output(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    kwargs = {
        "repo_root": REPO_ROOT,
        "runtime_dir": runtime,
        "output_dir": tmp_path / "out",
        "role": "ppu",
        "platform_name": "linux",
        "architecture": "armv7l",
        "git_sha": GIT_SHA,
        "build_timestamp": BUILD_TIMESTAMP,
    }
    product_release.build_release(**kwargs)

    with pytest.raises(product_release.ReleaseError, match="refusing to overwrite"):
        product_release.build_release(**kwargs)


def test_verify_detects_outer_archive_hash_mismatch(tmp_path: Path) -> None:
    artifact = product_release.build_release(
        repo_root=REPO_ROOT,
        runtime_dir=make_runtime(tmp_path),
        output_dir=tmp_path / "out",
        role="ppu",
        platform_name="linux",
        architecture="armv7l",
        git_sha=GIT_SHA,
        build_timestamp=BUILD_TIMESTAMP,
    )
    artifact.write_bytes(artifact.read_bytes() + b"tamper")

    with pytest.raises(product_release.ReleaseError, match="archive SHA-256 mismatch"):
        product_release.verify_release(artifact)


def test_verify_tree_detects_inner_payload_hash_mismatch(tmp_path: Path) -> None:
    artifact = product_release.build_release(
        repo_root=REPO_ROOT,
        runtime_dir=make_runtime(tmp_path),
        output_dir=tmp_path / "out",
        role="control-station",
        platform_name="linux",
        architecture="x86_64",
        git_sha=GIT_SHA,
        build_timestamp=BUILD_TIMESTAMP,
    )
    extracted = tmp_path / "manual-extract"
    product_release._extract_archive(artifact, extracted)
    root = extracted / "plasma-release"
    (root / "runtime" / "bin" / "plasma-runtime.txt").write_text(
        "tampered payload\n", encoding="utf-8"
    )

    with pytest.raises(product_release.ReleaseError, match="file SHA-256 mismatch"):
        product_release._verify_tree_hashes(root)


def test_verify_rejects_archive_path_traversal_before_extraction(tmp_path: Path) -> None:
    artifact = tmp_path / "malicious.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("../escape.txt", "escape")
    product_release._write_archive_sidecar(artifact)

    with pytest.raises(product_release.ReleaseError, match="unsafe archive member path"):
        product_release.verify_release(artifact)

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_SCRIPT = ROOT / "scripts" / "ppu-runtime.py"
RELEASE_SCRIPT = ROOT / "scripts" / "ppu-release.py"
PRODUCT_RELEASE_SCRIPT = ROOT / "scripts" / "product-release.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = _load(RUNTIME_SCRIPT, "ppu_runtime_release_test")
release = _load(RELEASE_SCRIPT, "ppu_release_test")
product_release = _load(PRODUCT_RELEASE_SCRIPT, "product_release_ppu_test")


def test_ppu_release_builds_and_verifies_linux_armv7l_artifact(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=runtime_dir)

    artifact = release.build_ppu_release(
        repo_root=ROOT,
        runtime_dir=runtime_dir,
        output_dir=tmp_path / "releases",
        git_sha="a" * 40,
        build_timestamp="2026-08-30T00:00:00Z",
    )

    assert artifact.is_file()
    assert artifact.name.endswith("-linux-armv7l.tar.gz")
    assert Path(str(artifact) + ".sha256").is_file()

    manifest = product_release.verify_release(
        artifact,
        extract_to=tmp_path / "verified",
        expect_role="ppu",
        expect_platform="linux",
        expect_architecture="armv7l",
    )
    assert manifest["role"] == "ppu"
    assert manifest["target"] == "linux-armv7l"
    assert manifest["contracts"] == {"plasma_protocol": "3.3", "web_rest_api": "3"}

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_SCRIPT = ROOT / "scripts" / "control-station-runtime.py"
RELEASE_SCRIPT = ROOT / "scripts" / "control-station-release.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = _load(RUNTIME_SCRIPT, "control_station_runtime_test")
release = _load(RELEASE_SCRIPT, "control_station_release_test")


def _standalone(tmp_path: Path) -> Path:
    root = tmp_path / "standalone"
    modules = root / "node_modules" / "vinext"
    modules.mkdir(parents=True)
    (root / "server.js").write_text("console.log('standalone');\n", encoding="utf-8")
    (root / "package.json").write_text('{"private":true,"type":"module"}\n', encoding="utf-8")
    (modules / "package.json").write_text('{"name":"vinext"}\n', encoding="utf-8")
    return root


def test_control_station_release_accepts_validated_console_runtime_node_modules(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime.build_runtime(
        repo_root=ROOT,
        standalone_console=_standalone(tmp_path),
        output_dir=runtime_dir,
    )

    artifact = release.build_control_station_release(
        repo_root=ROOT,
        runtime_dir=runtime_dir,
        output_dir=tmp_path / "releases",
        platform_name="linux",
        architecture="x86_64",
        git_sha="a" * 40,
        build_timestamp="2026-08-30T00:00:00Z",
    )

    assert artifact.is_file()
    assert Path(str(artifact) + ".sha256").is_file()


def test_control_station_release_rejects_node_modules_outside_console(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime.build_runtime(
        repo_root=ROOT,
        standalone_console=_standalone(tmp_path),
        output_dir=runtime_dir,
    )
    bad = runtime_dir / "manager" / "node_modules"
    bad.mkdir()
    (bad / "unexpected.js").write_text("bad\n", encoding="utf-8")

    with pytest.raises(release.ControlStationReleaseError, match="only allowed under console/node_modules"):
        release.build_control_station_release(
            repo_root=ROOT,
            runtime_dir=runtime_dir,
            output_dir=tmp_path / "releases",
            platform_name="linux",
            architecture="x86_64",
            git_sha="a" * 40,
            build_timestamp="2026-08-30T00:00:00Z",
        )

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "control-station-runtime.py"
SPEC = importlib.util.spec_from_file_location("control_station_runtime", SCRIPT)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def _standalone(tmp_path: Path) -> Path:
    root = tmp_path / "standalone"
    root.mkdir()
    (root / "server.js").write_text("console.log('standalone');\n", encoding="utf-8")
    (root / "package.json").write_text('{"private":true,"type":"module"}\n', encoding="utf-8")
    modules = root / "node_modules" / "vinext"
    modules.mkdir(parents=True)
    (modules / "package.json").write_text('{"name":"vinext"}\n', encoding="utf-8")
    return root


def test_build_runtime_creates_console_manager_manifest_and_license(tmp_path: Path) -> None:
    standalone = _standalone(tmp_path)
    output = tmp_path / "runtime"

    result = runtime.build_runtime(
        repo_root=ROOT,
        standalone_console=standalone,
        output_dir=output,
    )

    assert result == output.resolve()
    assert (output / "console" / "server.js").is_file()
    manager = output / "manager" / "manager.pyz"
    assert manager.is_file()
    assert (output / "manager" / "THIRD_PARTY_LICENSES" / "PyYAML.txt").is_file()

    manifest = json.loads((output / "control-station-runtime.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["role"] == "control-station"
    assert manifest["processes"]["console"]["entrypoint"] == "console/server.js"
    assert manifest["processes"]["manager"]["entrypoint"] == "manager/manager.pyz"
    assert manifest["packaging"] == {
        "console": "vinext-standalone",
        "manager": "python-zipapp",
    }
    assert manifest["third_party"]["PyYAML"]["version"]

    completed = subprocess.run(
        [sys.executable, str(manager), "--help"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Plasma Manager fleet control plane" in completed.stdout


def test_runtime_builder_refuses_to_overwrite_output(tmp_path: Path) -> None:
    standalone = _standalone(tmp_path)
    output = tmp_path / "runtime"
    output.mkdir()

    with pytest.raises(runtime.RuntimePackagingError, match="refusing to overwrite"):
        runtime.build_runtime(repo_root=ROOT, standalone_console=standalone, output_dir=output)


def test_runtime_builder_rejects_secret_or_source_files(tmp_path: Path) -> None:
    standalone = _standalone(tmp_path)
    (standalone / ".env").write_text("SECRET=value\n", encoding="utf-8")

    with pytest.raises(runtime.RuntimePackagingError, match="prohibited"):
        runtime.build_runtime(
            repo_root=ROOT,
            standalone_console=standalone,
            output_dir=tmp_path / "runtime",
        )


def test_validate_runtime_rejects_missing_manager(tmp_path: Path) -> None:
    standalone = _standalone(tmp_path)
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, standalone_console=standalone, output_dir=output)
    (output / "manager" / "manager.pyz").unlink()

    with pytest.raises(runtime.RuntimePackagingError, match="manager.pyz"):
        runtime.validate_runtime(output)


@pytest.mark.parametrize(
    (system_name, machine, expected),
    [
        ("Darwin", "arm64", ("macos", "arm64")),
        ("Darwin", "x86_64", ("macos", "x86_64")),
        ("Linux", "AMD64", ("linux", "x86_64")),
        ("Linux", "aarch64", ("linux", "arm64")),
        ("Windows", "AMD64", ("windows", "x86_64")),
    ],
)
def test_host_target_normalization(monkeypatch, system_name: str, machine: str, expected: tuple[str, str]) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: system_name)
    monkeypatch.setattr(runtime.platform, "machine", lambda: machine)
    assert runtime.host_target() == expected


def test_windows_arm64_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "ARM64")
    with pytest.raises(runtime.RuntimePackagingError, match="Windows ARM64"):
        runtime.host_target()

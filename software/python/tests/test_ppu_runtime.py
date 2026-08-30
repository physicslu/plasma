from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-runtime.py"
SPEC = importlib.util.spec_from_file_location("ppu_runtime", SCRIPT)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def test_build_runtime_creates_server_gateway_zipapp_and_catalog(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    result = runtime.build_runtime(repo_root=ROOT, output_dir=output)

    assert result == output.resolve()
    app = output / "ppu" / "ppu.pyz"
    assert app.is_file()
    assert (output / "ppu" / "THIRD_PARTY_LICENSES" / "PyYAML.txt").is_file()
    assert (output / "data" / "device-catalog" / "production" / "icpn-v1-manifest.json").is_file()

    manifest = json.loads((output / "ppu-runtime.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["role"] == "ppu"
    assert set(manifest["processes"]) == {"server", "gateway"}
    assert manifest["packaging"] == {"python": "python-zipapp"}
    assert manifest["hardware_boundary"] == {
        "loads_fpga": False,
        "accesses_pl": False,
        "changes_target_power": False,
        "programs_real_ic": False,
    }

    for command, expected in (
        ("server", "Plasma multi-site programming server"),
        ("gateway", "Plasma browser REST gateway"),
    ):
        completed = subprocess.run(
            [sys.executable, str(app), command, "--help"],
            cwd=tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        assert completed.returncode == 0, completed.stderr
        assert expected in completed.stdout


def test_runtime_builder_refuses_to_overwrite_output(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    output.mkdir()
    with pytest.raises(runtime.PPURuntimePackagingError, match="refusing to overwrite"):
        runtime.build_runtime(repo_root=ROOT, output_dir=output)


def test_validate_runtime_rejects_missing_app(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    (output / "ppu" / "ppu.pyz").unlink()
    with pytest.raises(runtime.PPURuntimePackagingError, match="ppu.pyz"):
        runtime.validate_runtime(output)


def test_validate_runtime_rejects_open_hardware_boundary(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    manifest_path = output / "ppu-runtime.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hardware_boundary"]["accesses_pl"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(runtime.PPURuntimePackagingError, match="hardware boundary"):
        runtime.validate_runtime(output)

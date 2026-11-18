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


def test_build_runtime_creates_server_gateway_helper_zipapp_without_catalog(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    result = runtime.build_runtime(repo_root=ROOT, output_dir=output)

    assert result == output.resolve()
    app = output / "ppu" / "ppu.pyz"
    assert app.is_file()
    assert (output / "ppu" / "THIRD_PARTY_LICENSES" / "PyYAML.txt").is_file()
    # OPF S5 / PR-C1: no Catalog / IC Support data ships in the PPU runtime.
    assert not (output / "data").exists()

    manifest = json.loads((output / "ppu-runtime.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["role"] == "ppu"
    assert set(manifest["processes"]) == {"server", "gateway", "runtime_activation_helper"}
    assert manifest["processes"]["runtime_activation_helper"]["privilege_boundary"] == "restart-plasma-server-only"
    assert manifest["packaging"] == {"python": "python-zipapp"}
    assert "data" not in manifest
    assert manifest["hardware_boundary"] == {
        "loads_fpga": False,
        "accesses_pl": False,
        "changes_target_power": False,
        "programs_real_ic": False,
    }

    for command, expected in (
        ("server", "Plasma multi-site programming server"),
        ("gateway", "Plasma browser REST gateway"),
        ("runtime-activation-helper", "Plasma bounded runtime activation helper"),
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


def test_packaged_opf_contract_imports_from_isolated_zipapp(tmp_path: Path) -> None:
    """Regression: the real Z2 release failed after activation without plasma_opf."""
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    app = output / "ppu" / "ppu.pyz"
    probe = (
        "import sys; "
        f"sys.path.insert(0, {str(app)!r}); "
        "from plasma_opf import TimeoutPolicy, OPF_PROGRAMMING_SCHEMA; "
        "assert OPF_PROGRAMMING_SCHEMA == 'plasma.opf.programming.v1'; "
        "assert TimeoutPolicy(5000, 12000).default_timeout_ms == 5000"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", probe], cwd=tmp_path,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_runtime_validator_rejects_missing_opf_contract(tmp_path: Path) -> None:
    import zipfile

    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    app = output / "ppu" / "ppu.pyz"
    damaged = tmp_path / "damaged.pyz"
    with zipfile.ZipFile(app) as source, zipfile.ZipFile(damaged, "w") as dest:
        for item in source.infolist():
            if item.filename not in {"plasma_opf/__init__.py", "plasma_opf/contract.py"}:
                dest.writestr(item, source.read(item.filename))
    damaged.replace(app)
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c",
         f"import sys; sys.path.insert(0, {str(app)!r}); import plasma_opf.contract"],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0 and "No module named 'plasma_opf.contract'" in result.stderr
    with pytest.raises(runtime.PPURuntimePackagingError, match="plasma_opf"):
        runtime.validate_runtime(output)


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


def test_zipapp_contains_no_catalog_only_module(tmp_path: Path) -> None:
    import zipfile

    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    with zipfile.ZipFile(output / "ppu" / "ppu.pyz") as archive:
        names = set(archive.namelist())
    assert not names & set(runtime.CATALOG_ONLY_MODULES)
    assert not [n for n in names if n.startswith("data/")]
    # Every excluded module really exists in source (the list cannot rot silently).
    for relative in runtime.CATALOG_ONLY_MODULES:
        assert (ROOT / "software" / "python" / relative).is_file(), relative


_CATALOG_ENV = ("PLASMA_IC_SUPPORT_ROOT", "PLASMA_DEVICE_CATALOG_MANIFEST")


def test_enabled_openocd_site_starts_from_catalog_free_runtime(tmp_path: Path) -> None:
    """Inverse of the historical Z2 D6 regression: with no Catalog data, no
    Catalog modules in the zipapp and no Catalog environment, an enabled
    non-mock Site still starts (OPF S5: Catalog is never a Runtime dependency)."""
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    config = tmp_path / "ppu.yaml"
    config.write_text(
        "ppu: {id: z2-test, facility_id: lab, model: PYNQ-Z2, display_name: Z2}\n"
        f"server: {{output_root: {tmp_path / 'out'}, log_root: {tmp_path / 'log'}}}\n"
        "sites:\n"
        '  - {id: 2, enabled: true, interface: "openocd", target: "STM32F103C8T6"}\n',
        encoding="utf-8",
    )
    probe = (
        "import json, sys\n"
        "from plasma_core.config import load_config\n"
        "from plasma_server.site_manager import SiteManager\n"
        "import plasma_web.gateway_phase3, plasma_web.runtime_activation_helper\n"
        "manager = SiteManager(load_config(sys.argv[1]))\n"
        "catalog = sorted(m for m in sys.modules if m.split('.')[-1] in sys.argv[2].split(','))\n"
        "import plasma_web\n"
        "assert plasma_web.__file__.startswith(sys.path[0]), plasma_web.__file__\n"
        "print(json.dumps({'sites': sorted(manager.interfaces), 'catalog': catalog}))\n"
    )
    names = ",".join(Path(m).stem for m in runtime.CATALOG_ONLY_MODULES)
    environment = {"PATH": "/usr/bin:/bin"}
    assert not set(_CATALOG_ENV) & set(environment)
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c",
         f"import sys; sys.path.insert(0, {str(output / 'ppu' / 'ppu.pyz')!r}); exec({probe!r})",
         str(config), names],
        cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {"sites": [2], "catalog": []}


def test_validate_runtime_accepts_runtime_without_catalog_manifest_section(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    assert runtime.validate_runtime(output)["role"] == "ppu"

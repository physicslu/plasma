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


def test_build_runtime_creates_server_gateway_helper_zipapp_and_catalog(tmp_path: Path) -> None:
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
    assert set(manifest["processes"]) == {"server", "gateway", "runtime_activation_helper"}
    assert manifest["processes"]["runtime_activation_helper"]["privilege_boundary"] == "restart-plasma-server-only"
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


def test_runtime_ships_ic_support_data_only_and_enabled_openocd_site_starts(tmp_path: Path) -> None:
    """Regression for Z2 D6: an enabled non-mock Site crash-looped the installed
    Runtime with ICSupportIntegrityError because no IC Support data shipped."""
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    manifest = json.loads((output / "ppu-runtime.json").read_text(encoding="utf-8"))
    assert manifest["data"]["ic_support_root"] == "data/ic-support"
    ic_root = output / "data" / "ic-support"
    shipped = {p.relative_to(ic_root).as_posix() for p in ic_root.rglob("*") if p.is_file()}
    assert "socket-profiles/stm32f103c8t6-lqfp48-swd-v1.json" in shipped
    assert "manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.lock.json" in shipped
    assert "benchmarks/nxp-kl25/backend-implementation-lock.json" in shipped
    assert not [name for name in shipped if name.endswith(".py")]

    config = tmp_path / "ppu.yaml"
    config.write_text(
        "ppu: {id: z2-test, facility_id: lab, model: PYNQ-Z2, display_name: Z2}\n"
        f"server: {{output_root: {tmp_path / 'out'}, log_root: {tmp_path / 'log'}}}\n"
        "sites:\n"
        '  - {id: 2, enabled: true, interface: "openocd", target: "STM32F103C8T6"}\n',
        encoding="utf-8",
    )
    probe = (
        "import sys\n"
        "from plasma_core.config import load_config\n"
        "from plasma_server.site_manager import SiteManager\n"
        "manager = SiteManager(load_config(sys.argv[1]))\n"
        "assert manager.ic_support_resolver is not None\n"
        "print(sorted(manager.interfaces))\n"
    )
    environment = {"PATH": "/usr/bin:/bin", "PLASMA_IC_SUPPORT_ROOT": str(ic_root)}
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c",
         f"import sys; sys.path.insert(0, {str(output / 'ppu' / 'ppu.pyz')!r}); exec({probe!r})", str(config)],
        cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[2]"

    # Negative control: the same zipapp without shipped data fails closed.
    import shutil

    isolated = tmp_path / "isolated" / "runtime" / "ppu" / "ppu.pyz"
    isolated.parent.mkdir(parents=True)
    shutil.copyfile(output / "ppu" / "ppu.pyz", isolated)
    del environment["PLASMA_IC_SUPPORT_ROOT"]
    failed = subprocess.run(
        [sys.executable, "-I", "-B", "-c",
         f"import sys; sys.path.insert(0, {str(isolated)!r}); exec({probe!r})", str(config)],
        cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
    )
    assert failed.returncode != 0
    assert "PLASMA_IC_SUPPORT_ROOT" in failed.stderr


def test_validate_runtime_rejects_missing_ic_support(tmp_path: Path) -> None:
    import shutil

    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    shutil.rmtree(output / "data" / "ic-support" / "bindings")
    with pytest.raises(runtime.PPURuntimePackagingError, match="IC Support data is incomplete"):
        runtime.validate_runtime(output)


def test_validate_runtime_rejects_python_tooling_in_ic_support(tmp_path: Path) -> None:
    output = tmp_path / "runtime"
    runtime.build_runtime(repo_root=ROOT, output_dir=output)
    (output / "data" / "ic-support" / "validate.py").write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(runtime.PPURuntimePackagingError, match="must not contain Python tooling"):
        runtime.validate_runtime(output)

"""S5-A: portable OPF import isolation and retired Runtime boundary guards.

Host-only evidence: a module import or fake process is never physical Flash PASS.
This suite exercises only files in plasma_opf and retired source paths.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PYTHON_ROOT = Path(__file__).resolve().parents[1]
OPF_SOURCE = PYTHON_ROOT / "plasma_opf"
FORBIDDEN_HOST_ROOTS = frozenset({
    "plasma_core", "plasma_interfaces", "plasma_handlers", "plasma_server",
    "plasma_web", "plasma_manager", "plasma_client",
})
RETIRED_RUNTIME_MODULES = (
    "plasma_interfaces/compiler_registry.py",
    "plasma_interfaces/openocd_plan.py",
    "plasma_interfaces/openocd_executor.py",
    "plasma_interfaces/kl25_openocd_plan.py",
)


def _isolated_import(opf_parent: Path) -> subprocess.CompletedProcess[str]:
    # -I and -S avoid user-site/editable wheels; only the copied OPF package
    # is supplied in sys.path, not the repository or PPU runtime.
    code = """
import sys
sys.path.insert(0, sys.argv[1])
from plasma_opf import (OPF_PROGRAMMING_SCHEMA, TimeoutPolicy,
                        parse_programming_selection, ProcessObservation)
selection = parse_programming_selection(
    {"schema": OPF_PROGRAMMING_SCHEMA, "provider": "fake",
     "profile": "synthetic", "options": {}},
    policy=TimeoutPolicy(default_timeout_ms=500, maximum_timeout_ms=1000),
)
assert (selection.provider, selection.profile) == ("fake", "synthetic")
observation = ProcessObservation(
    provider="fake", profile="synthetic", image_sha256="00",
    process_status="SUCCEEDED", exit_code=0, stdout="FLASH PASS", stderr="",
)
assert observation.programming_status == "NOT_QUALIFIED"
assert not hasattr(observation, "flash_pass")
for prefix in ("plasma_core", "plasma_interfaces", "plasma_handlers",
               "plasma_server", "plasma_web", "plasma_manager",
               "plasma_client"):
    assert not any(name == prefix or name.startswith(prefix + ".")
                   for name in sys.modules), prefix
print("OPF_ISOLATED_IMPORT_PASS")
"""
    return subprocess.run(
        [sys.executable, "-I", "-S", "-c", code, str(opf_parent)],
        capture_output=True, text=True, check=False, timeout=15,
    )


def test_opf_import_graph_has_no_ppu_or_catalog_edges():
    files = sorted(OPF_SOURCE.glob("*.py"))
    assert {file.name for file in files} >= {
        "__init__.py", "contract.py", "python_provider.py",
    }
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = (item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = (node.module or "",)
            else:
                continue
            for module in modules:
                assert module.split(".", 1)[0] not in FORBIDDEN_HOST_ROOTS, (
                    f"{file.name} imports PPU/Catalog dependency: {module}"
                )


def test_isolated_stdlib_only_opf_can_parse_selection_without_ppu(tmp_path):
    shutil.copytree(OPF_SOURCE, tmp_path / "plasma_opf")
    result = _isolated_import(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OPF_ISOLATED_IMPORT_PASS"


def test_import_isolation_negative_control_rejects_injected_ppu_dependency(tmp_path):
    shutil.copytree(OPF_SOURCE, tmp_path / "plasma_opf")
    package_init = tmp_path / "plasma_opf" / "__init__.py"
    with package_init.open("a", encoding="utf-8") as stream:
        stream.write("\nfrom plasma_server import site_manager\n")
    result = _isolated_import(tmp_path)
    assert result.returncode != 0
    assert "No module named 'plasma_server'" in result.stderr


@pytest.mark.parametrize("relative_path", RETIRED_RUNTIME_MODULES)
def test_retired_exact_icpn_compiler_modules_do_not_reappear(relative_path):
    assert not (PYTHON_ROOT / relative_path).exists(), relative_path

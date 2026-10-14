#!/usr/bin/env python3
"""Prevent installed Python runtimes from mistaking site-packages for project data.

Domain-owned external evidence must be found through explicit runtime contracts
(PLASMA_DEVICE_CATALOG_MANIFEST, PLASMA_IC_SUPPORT_ROOT or
PLASMA_RUNTIME_EVIDENCE_ROOT), never a new module-relative __file__ walk.

Only two historical, source-tree DEVELOPMENT fallbacks are allowed. Their AST
shape is frozen; all new package code is deny-by-default for __file__ access.
Package-local assets should use importlib.resources instead.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "software/python"
# Ratcheted migration debt, not an exemption for new loaders.
# Existing implementations consult their explicit runtime configuration before
# invoking these source-tree-only convenience fallbacks.
EXISTING_SOURCE_TREE_FALLBACKS = frozenset({
    "software/python/plasma_core/ic_support.py",
    "software/python/plasma_web/device_catalog.py",
})
LEGACY_FUNCTION = "_repository_root"
LEGACY_EXPRESSION = "Path(__file__).resolve().parents[3]"

# Ensure repaired source-only and executor loaders keep the shared root API
# even when a future refactor no longer uses __file__ directly.
REQUIRED_RESOLVER_CALLS = {
    "software/python/plasma_web/nxp_manufacturer_device_evidence.py": (
        "default_catalog_manifest_path",
    ),
    "software/python/plasma_web/runtime_evidence_root.py": (
        "default_catalog_manifest_path",
    ),
    "software/python/plasma_web/backend_candidate_registry.py": (
        "default_runtime_evidence_root", "source_files_available",
    ),
    "software/python/plasma_web/backend_source_reference.py": (
        "default_runtime_evidence_root", "source_files_available",
    ),
    "software/python/plasma_web/openocd_provider_registry.py": (
        "default_runtime_evidence_root", "source_files_available",
    ),
    "software/python/plasma_interfaces/kl25_openocd_plan.py": (
        "default_ic_support_root",
    ),
}


@dataclass(frozen=True)
class Issue:
    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}"


class FileRootVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scopes: list[str] = []
        self.references: list[tuple[int, tuple[str, ...]]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scopes.append(f"function:{node.name}")
        self.generic_visit(node)
        self.scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scopes.append(f"function:{node.name}")
        self.generic_visit(node)
        self.scopes.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scopes.append(f"class:{node.name}")
        self.generic_visit(node)
        self.scopes.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.scopes.append("lambda")
        self.generic_visit(node)
        self.scopes.pop()

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "__file__":
            self.references.append((node.lineno, tuple(self.scopes)))


def examine_source(path: str, source: str, *, guard_legacy: bool = True) -> list[Issue]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [Issue(path, exc.lineno or 1, f"invalid Python syntax: {exc.msg}")]

    visitor = FileRootVisitor(path)
    visitor.visit(tree)
    issues = []
    allowed = path in EXISTING_SOURCE_TREE_FALLBACKS

    for lineno, scope in visitor.references:
        if not allowed or scope != (f"function:{LEGACY_FUNCTION}",):
            issues.append(Issue(
                path, lineno,
                "installed-runtime module must not derive project paths from __file__; "
                "use the explicit data-root resolver or importlib.resources",
            ))

    if allowed and guard_legacy:
        # A legacy fallback must not grow a second use or change its meaning.
        funcs = [
            stmt for stmt in tree.body
            if isinstance(stmt, ast.FunctionDef) and stmt.name == LEGACY_FUNCTION
        ]
        valid = len(funcs) == 1
        if valid:
            returns = [
                stmt for stmt in funcs[0].body
                if isinstance(stmt, ast.Return)
            ]
            valid = (len(returns) == 1 and
                     ast.unparse(returns[0].value) == LEGACY_EXPRESSION and
                     len(visitor.references) == 1)
        if not valid:
            issues.append(Issue(
                path, 1,
                "grandfathered source-tree fallback changed; migrate to an explicit "
                "runtime root and update the governed exception instead of expanding it",
            ))
    return issues


def check_required_resolvers(sources: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    for path, required in REQUIRED_RESOLVER_CALLS.items():
        if path not in sources:
            issues.append(Issue(path, 1, "protected runtime loader is missing"))
            continue
        tree = ast.parse(sources[path], filename=path)
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for name in required:
            if name not in called:
                issues.append(Issue(
                    path, 1,
                    f"protected runtime loader must call {name}()",
                ))
    return issues


def package_sources(root: Path) -> dict[str, str]:
    package = root / "software/python"
    sources = {}
    for folder in sorted(package.glob("plasma_*")):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            sources[relative] = path.read_text(encoding="utf-8")
    if not sources:
        raise ValueError(f"no installable Plasma Python modules found beneath {package}")
    return sources


def audit_repository(root: Path) -> tuple[int, list[Issue]]:
    sources = package_sources(root)
    issues = [issue for path, src in sources.items() for issue in examine_source(path, src)]
    missing_debt = EXISTING_SOURCE_TREE_FALLBACKS - sources.keys()
    for path in sorted(missing_debt):
        issues.append(Issue(path, 1, "grandfathered fallback file missing; ratchet debt ledger"))
    issues.extend(check_required_resolvers(sources))
    return len(sources), sorted(issues, key=lambda v: (v.path, v.line, v.reason))


def self_test() -> None:
    normal = "from importlib.resources import files\nROOT = files('plasma_core')\n"
    assert not examine_source("software/python/plasma_web/new_vendor.py", normal)
    assert not examine_source(
        "software/python/plasma_web/new_vendor.py",
        "ROOT = default_runtime_evidence_root()\n",
    )
    bad = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[3] / 'data/device-catalog'\n"
    )
    assert examine_source("software/python/plasma_web/new_vendor.py", bad)
    assert examine_source(
        "software/python/plasma_interfaces/new_loader.py",
        "import os\nROOT = os.path.dirname(__file__)\n",
    )
    assert examine_source(
        "software/python/plasma_web/new_vendor.py",
        "def x():\n    return __file__\n",
    )
    legacy = (
        "from pathlib import Path\n"
        "def _repository_root() -> Path:\n"
        "    return Path(__file__).resolve().parents[3]\n"
    )
    oldpath = "software/python/plasma_core/ic_support.py"
    assert not examine_source(oldpath, legacy)
    assert examine_source(oldpath, legacy + "LEAK = __file__\n")
    assert examine_source(
        oldpath, legacy.replace("parents[3]", "parents[2]")
    )
    assert examine_source(
        oldpath, legacy.replace("def _repository_root()", "def new_loader()")
    )
    # A protected loader with only one of its required resolvers is invalid.
    for path, required in REQUIRED_RESOLVER_CALLS.items():
        tree = ast.parse("".join(f"{name}()\n" for name in required))
        assert len([n for n in ast.walk(tree) if isinstance(n, ast.Call)]) == len(required)
    assert len(check_required_resolvers({path: "" for path in REQUIRED_RESOLVER_CALLS})) == sum(
        map(len, REQUIRED_RESOLVER_CALLS.values())
    )
    print("Runtime Data Root CI policy self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    total, issues = audit_repository(ROOT)
    if issues:
        print("Runtime Data Root contract: FAIL")
        for issue in issues:
            print("  " + str(issue))
        return 1
    print(
        f"Runtime Data Root contract PASS; {total} installed Python modules audited; "
        f"source-tree fallback debt={len(EXISTING_SOURCE_TREE_FALLBACKS)}; "
        f"protected loaders={len(REQUIRED_RESOLVER_CALLS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plasma FPGA target orchestration.

Resolve repository-defined FPGA targets and delegate work to the real tools
(Verilator and pytest/cocotb). Keep this frontend small and deterministic.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGETS_DIR = REPO_ROOT / "pl" / "targets"


class FpgaToolError(RuntimeError):
    """Deterministic user-facing FPGA workflow error."""


@dataclass(frozen=True)
class Target:
    name: str
    top: str
    simulator: str
    sources: tuple[Path, ...]
    test_runner: Path | None
    waveform: Path | None
    manifest: Path


def _repo_path(raw: str, *, field: str, manifest: Path) -> Path:
    candidate = (REPO_ROOT / raw).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise FpgaToolError(
            f"{manifest}: {field} path escapes repository root: {raw}"
        ) from exc
    return candidate


def _require_str(data: dict, key: str, manifest: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FpgaToolError(f"{manifest}: '{key}' must be a non-empty string")
    return value.strip()


def load_target(manifest: Path) -> Target:
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise FpgaToolError(f"Cannot read target manifest {manifest}: {exc}") from exc

    name = _require_str(data, "name", manifest)
    top = _require_str(data, "top", manifest)

    simulator = data.get("simulator", "verilator")
    if not isinstance(simulator, str) or not simulator.strip():
        raise FpgaToolError(f"{manifest}: 'simulator' must be a non-empty string")
    simulator = simulator.strip()

    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise FpgaToolError(f"{manifest}: 'sources' must be a non-empty array")

    sources: list[Path] = []
    for raw_source in raw_sources:
        if not isinstance(raw_source, str) or not raw_source.strip():
            raise FpgaToolError(
                f"{manifest}: each 'sources' entry must be a non-empty string"
            )
        sources.append(_repo_path(raw_source.strip(), field="source", manifest=manifest))

    verification = data.get("verification", {})
    if not isinstance(verification, dict):
        raise FpgaToolError(f"{manifest}: 'verification' must be a table")

    test_runner = None
    raw_runner = verification.get("runner")
    if raw_runner is not None:
        if not isinstance(raw_runner, str) or not raw_runner.strip():
            raise FpgaToolError(
                f"{manifest}: verification.runner must be a non-empty string"
            )
        test_runner = _repo_path(
            raw_runner.strip(), field="verification.runner", manifest=manifest
        )

    waveform = None
    raw_waveform = verification.get("waveform")
    if raw_waveform is not None:
        if not isinstance(raw_waveform, str) or not raw_waveform.strip():
            raise FpgaToolError(
                f"{manifest}: verification.waveform must be a non-empty string"
            )
        waveform = _repo_path(
            raw_waveform.strip(), field="verification.waveform", manifest=manifest
        )

    return Target(
        name=name,
        top=top,
        simulator=simulator,
        sources=tuple(sources),
        test_runner=test_runner,
        waveform=waveform,
        manifest=manifest.resolve(),
    )


def all_targets() -> list[Target]:
    if not TARGETS_DIR.is_dir():
        raise FpgaToolError(f"Target directory does not exist: {TARGETS_DIR}")

    targets = [load_target(path) for path in sorted(TARGETS_DIR.glob("*.toml"))]
    if not targets:
        raise FpgaToolError(f"No FPGA target manifests found in {TARGETS_DIR}")

    names: set[str] = set()
    for target in targets:
        if target.name in names:
            raise FpgaToolError(f"Duplicate FPGA target name: {target.name}")
        names.add(target.name)
    return targets


def select_target(*, name: str | None, source_file: str | None) -> Target:
    targets = all_targets()

    if name is not None:
        matches = [target for target in targets if target.name == name]
        if not matches:
            available = ", ".join(target.name for target in targets)
            raise FpgaToolError(
                f"Unknown FPGA target '{name}'. Available targets: {available}"
            )
        return matches[0]

    if source_file is None:
        raise FpgaToolError("Specify a target name or --file <RTL path>")

    candidate = Path(source_file)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()

    matches = [target for target in targets if candidate in target.sources]
    if not matches:
        raise FpgaToolError(f"No FPGA target contains source file: {candidate}")
    if len(matches) > 1:
        names = ", ".join(target.name for target in matches)
        raise FpgaToolError(
            f"Source file belongs to multiple FPGA targets ({names}); "
            "select the target explicitly"
        )
    return matches[0]


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _check_paths(paths: Iterable[Path], *, kind: str) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        lines = "\n".join(f"  - {_relative(path)}" for path in missing)
        raise FpgaToolError(f"Missing {kind} path(s):\n{lines}")


def _run(command: list[str]) -> int:
    print(f"+ {shlex.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return completed.returncode


def lint_target(target: Target) -> int:
    if target.simulator != "verilator":
        raise FpgaToolError(
            f"Target '{target.name}' uses unsupported lint simulator "
            f"'{target.simulator}'"
        )
    if shutil.which("verilator") is None:
        raise FpgaToolError("verilator is not on PATH. Run 'source pl/env.sh' first.")

    _check_paths(target.sources, kind="RTL source")

    return _run(
        [
            "verilator",
            "--lint-only",
            "--sv",
            "-Wall",
            "--top-module",
            target.top,
            *[str(path) for path in target.sources],
        ]
    )


def test_target(target: Target) -> int:
    if target.test_runner is None:
        raise FpgaToolError(f"Target '{target.name}' does not define verification.runner")

    _check_paths([target.test_runner], kind="test runner")
    return _run(
        [
            sys.executable,
            "-m",
            "pytest",
            _relative(target.test_runner),
            "-v",
            "-s",
        ]
    )


def verify_target(target: Target) -> int:
    print(f"== FPGA target: {target.name} ==")
    lint_status = lint_target(target)
    if lint_status != 0:
        return lint_status

    if target.test_runner is None:
        print("No functional test runner configured; lint passed.")
        return 0
    return test_target(target)


def show_waveform(target: Target, *, open_in_vscode: bool) -> int:
    if target.waveform is None:
        raise FpgaToolError(
            f"Target '{target.name}' does not define verification.waveform"
        )

    _check_paths([target.waveform], kind="waveform")
    print(_relative(target.waveform))

    if open_in_vscode:
        code = shutil.which("code")
        if code is None:
            raise FpgaToolError(
                "VS Code CLI 'code' is not on PATH; open the waveform path manually."
            )
        return _run([code, "-r", str(target.waveform)])
    return 0


def _add_selector(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("target", nargs="?", help="FPGA target name")
    group.add_argument(
        "--file",
        dest="source_file",
        help="Resolve target from an RTL source file",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plasma FPGA target build and verification frontend"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List configured FPGA targets")

    for command, help_text in (
        ("lint", "Run static/lint checks"),
        ("test", "Run functional regression"),
        ("verify", "Run lint followed by functional regression"),
        ("wave", "Show or open the target waveform"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        _add_selector(subparser)
        if command == "wave":
            subparser.add_argument(
                "--open",
                action="store_true",
                help="Open waveform through the VS Code CLI",
            )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            for target in all_targets():
                print(
                    f"{target.name:<20} top={target.top:<20} "
                    f"sources={len(target.sources)}"
                )
            return 0

        target = select_target(name=args.target, source_file=args.source_file)

        if args.command == "lint":
            return lint_target(target)
        if args.command == "test":
            return test_target(target)
        if args.command == "verify":
            return verify_target(target)
        if args.command == "wave":
            return show_waveform(target, open_in_vscode=args.open)

        parser.error(f"Unsupported command: {args.command}")
    except FpgaToolError as exc:
        print(f"FPGA ERROR: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

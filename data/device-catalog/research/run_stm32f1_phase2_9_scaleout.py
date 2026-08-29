#!/usr/bin/env python3
"""Run the bounded Phase 2.9 STM32F1 live-evidence pipeline end to end.

This command intentionally stops at retained evidence plus a read-only admission plan.
It never writes the canonical commercial ICPN dataset.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DEFAULT_MANIFEST = HERE / "stm32f1-phase2.9-scaleout-manifest.json"
DEFAULT_BASELINE = HERE / "stm32f1-phase2.9-scaleout-baseline.json"
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
DEFAULT_CONTROL = "STM32F100CB"


class ScaleoutRunError(RuntimeError):
    pass


def run_checked(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise ScaleoutRunError(
            "command failed with exit code "
            f"{completed.returncode}: {' '.join(command)}"
        )


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise ScaleoutRunError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def require_clean_repository() -> str:
    status = git_output("status", "--porcelain")
    if status:
        raise ScaleoutRunError("live evidence requires a clean Git working tree")
    sha = git_output("rev-parse", "HEAD")
    if len(sha) != 40:
        raise ScaleoutRunError("cannot resolve full executed Git SHA")
    return sha


def command_plan(
    *,
    python: str,
    manifest: Path,
    baseline: Path,
    catalog: Path,
    canonical: Path,
    control_base: str,
    scratch: Path,
    evidence_dir: Path,
    admission_plan: Path,
    git_sha: str,
) -> list[list[str]]:
    runner = HERE / "run_stm32f1_browser_pilot.py"
    evaluator = HERE / "evaluate_stm32f1_live_pilot.py"
    retention = HERE / "retain_stm32f1_browser_evidence.py"
    planner = HERE / "stm32f1_scaleout_admission.py"
    control = scratch / "control-summary.json"
    pilot = scratch / "pilot-summary.json"
    evaluation = scratch / "evaluation.json"
    return [
        [
            python,
            str(runner),
            "--manifest",
            str(manifest),
            "--catalog",
            str(catalog),
            "--output",
            str(control),
            "--scope",
            "control",
            "--control-base-device",
            control_base,
            "--headed",
        ],
        [
            python,
            str(runner),
            "--manifest",
            str(manifest),
            "--catalog",
            str(catalog),
            "--output",
            str(pilot),
            "--scope",
            "pilot",
            "--headed",
        ],
        [
            python,
            str(evaluator),
            "--summary",
            str(pilot),
            "--baseline",
            str(baseline),
            "--output",
            str(evaluation),
            "--repository",
            "physicslu/plasma",
            "--git-sha",
            git_sha,
        ],
        [
            python,
            str(retention),
            "--control",
            str(control),
            "--pilot",
            str(pilot),
            "--evaluation",
            str(evaluation),
            "--baseline",
            str(baseline),
            "--output-dir",
            str(evidence_dir),
        ],
        [
            python,
            str(planner),
            "--evidence-dir",
            str(evidence_dir),
            "--baseline",
            str(baseline),
            "--catalog",
            str(catalog),
            "--canonical",
            str(canonical),
            "--output",
            str(admission_plan),
        ],
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--control-base-device", default=DEFAULT_CONTROL)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--admission-plan", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        git_sha = require_clean_repository()
        if args.evidence_dir.exists():
            raise ScaleoutRunError(f"evidence directory already exists: {args.evidence_dir}")
        if args.admission_plan.exists():
            raise ScaleoutRunError(f"admission plan already exists: {args.admission_plan}")
        args.admission_plan.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="plasma-stm32f1-phase2.9-") as temp:
            scratch = Path(temp)
            commands = command_plan(
                python=sys.executable,
                manifest=args.manifest.resolve(),
                baseline=args.baseline.resolve(),
                catalog=args.catalog.resolve(),
                canonical=args.canonical.resolve(),
                control_base=args.control_base_device,
                scratch=scratch,
                evidence_dir=args.evidence_dir.resolve(),
                admission_plan=args.admission_plan.resolve(),
                git_sha=git_sha,
            )
            for command in commands:
                run_checked(command)
        plan = json.loads(args.admission_plan.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "executed_git_sha": git_sha,
                    "evidence_dir": str(args.evidence_dir),
                    "admission_plan": str(args.admission_plan),
                    "candidate_count": plan.get("candidate_count"),
                    "decision_counts": plan.get("decision_counts"),
                    "conflicts": plan.get("conflicts"),
                    "canonical_dataset_written": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, ScaleoutRunError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

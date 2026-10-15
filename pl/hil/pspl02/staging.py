"""Build a new local inspection kit. No network, tool execution or hardware I/O."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tarfile

from pl.hil.pspl02 import contract as c


def create(paths: dict[str, Path], output: Path):
    report = c.verify_artifacts(paths)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for key, path in paths.items():
        destination = output/"artifacts"/key
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, destination)
    c.verify_artifacts({key: output/"artifacts"/key for key in c.HASHES})
    root = Path(__file__).resolve().parents[3]
    sources = list(Path(__file__).parent.glob("*.py"))
    sources += [root/"pl/hil/swd04"/name for name in ("contract.py", "collect.py", "staging.py")]
    for source in sources:
        dest = output/source.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    (output/"templates").mkdir()
    c.write_record(output/"templates/attestation.json",
                   dict(schema_version=1, **dict.fromkeys(c.PREREQUISITES, False)))
    for stage in c.STAGES:
        session = dict.fromkeys(("candidate_loaded_and_verified", "original_uios_unbound",
            "kernel_and_clocks_reviewed_after_load", "uart_login_verified_now",
            "independent_power_recovery_ready", "operator_present", "no_shared_service_changes",
            "no_asynchronous_pl_reconfiguration"), False)
        session.update(stage=stage, p0_sha256="", observed_utc="", load_log="", load_log_sha256="",
                       metadata_file="", metadata_backup="", metadata_sha256="",
                       board_identity_sha256="")
        c.write_record(output/f"templates/session-{stage}.json", session)
    checklist = root/"docs/development/pspl02-swd00-hil-runbook.md"
    if not checklist.is_file():
        checklist = root/"CHECKLIST.md"
    shutil.copyfile(checklist, output/"CHECKLIST.md")
    report.update(qualification="PSPL-02/SWD-00", physical_readiness="NO_GO_UNTIL_FRESH_BOARD_PREFLIGHT",
                  hardware_execution="NOT_RUN", service_changes="NOT_RUN")
    c.write_record(output/"staging-report.json", report)
    files = sorted(p for p in output.rglob("*") if p.is_file())
    with (output/"SHA256SUMS").open("x") as stream:
        for path in files:
            stream.write(f"{c.sha256_file(path)}  {path.relative_to(output)}\n")
    with tarfile.open(output/"pspl02-kit.tar.gz", "x:gz") as archive:
        for path in [*files, output/"SHA256SUMS"]:
            archive.add(path, arcname="pspl02/"+str(path.relative_to(output)), recursive=False)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in c.HASHES:
        parser.add_argument("--"+key.replace(".", "-"), dest=key, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        create({key: vars(args)[key] for key in c.HASHES}, args.output)
    except (OSError, ValueError, c.SafetyError) as exc:
        print("PSPL02_STAGING_NO_GO: " + str(exc), file=sys.stderr)
        return 2
    print("PSPL02_OFFLINE_KIT_VERIFIED_NO_HARDWARE_ACTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Issue #981: owner-only non-actuating LA2016 worker failure diagnosis.

No USB opens, firmware changes, sudo, PWM, FPGA, JTAG or Hub commands.
The only model operation is the existing read-only Codex capability request
inside the identical reviewed bubblewrap namespace; its output stays private.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import sys
import tempfile

REPO = "physicslu/plasma"
OWNER = "physicslu"
COMMAND = "/plasma-codex la2016-diag 981"
SCRIPT = Path(__file__).resolve().parent / "plasma-codex-la2016.py"

def authorize(event: dict, actor: str, repository: str, ref: str) -> bool:
    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    sender = event.get("sender") or {}
    source = event.get("repository") or {}
    return (
        event.get("action") == "created"
        and repository == REPO and source.get("full_name") == REPO
        and actor == OWNER and sender.get("login") == OWNER
        and comment.get("user", {}).get("login") == OWNER
        and issue.get("number") == 981 and not issue.get("pull_request")
        and comment.get("body") == COMMAND and ref == "refs/heads/main"
    )

def load_supervisor():
    # Import source from the reviewed immutable main checkout; no execution.
    spec = importlib.util.spec_from_file_location("plasma_la2016_guard", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ALLOWED = {
    "PINNED_KINGST_APPIMAGE_NOT_INSTALLED", "KINGST_APPIMAGE_SHA_MISMATCH",
    "KINGST_UNIQUE_USB_MAPPING_NOT_READY", "KINGST_USB_DAC_DENIED",
    "USB_OWNER_CHECK_UNAVAILABLE", "KINGST_BUSY_OR_OWNER_UNCERTAIN",
    "ISOLATION_OR_CODEX_MISSING", "SYMLINKED_PRIVATE_HOME",
    "CODEX_HOME_NOT_READY", "CODEX_EXEC_NOT_SUCCESS",
    "NO_AGENT_REQUEST", "INVALID_AGENT_JSON", "AGENT_REQUEST_SCHEMA",
    "AGENT_CAPABILITY_DENIED", "AGENT_CASES_NOT_ALLOWLISTED",
    "AGENT_CASE_NOT_ALLOWLISTED",
}

def error_code(exc: BaseException) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "TIMEOUT"
    value = str(exc)
    return value if value in ALLOWED else "UNEXPECTED_ERROR"

def check_worker() -> None:
    if (socket.gethostname() != "SWPC"
        or pwd.getpwuid(os.geteuid()).pw_name != "plasma-codex"
        or os.geteuid() == 0
        or os.environ.get("RUNNER_NAME") != "SWPC-plasma-codex"
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_EVENT_NAME") != "issue_comment"
        or os.environ.get("GITHUB_REPOSITORY") != REPO
        or os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise SystemExit("DENIED_WORKER_IDENTITY")

def passive_status(function) -> str:
    try:
        function()
        return "PASS"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return error_code(exc)

def cli_status() -> str:
    exe = shutil.which("codex")
    if exe is None:
        return "CODEX_CLI_NOT_IN_RUNNER_PATH"
    try:
        completed = subprocess.run(
            [exe, "--version"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=10, check=False,
        )
        return "PASS" if completed.returncode == 0 else "CODEX_VERSION_FAILED"
    except (OSError, subprocess.SubprocessError) as exc:
        return error_code(exc)

def namespace_status(supervisor, out: Path) -> str:
    try:
        # Exact production mount arguments, including hidden USB and
        # masked credentials. Replace Codex subcommand with passive tests.
        args = supervisor.sandbox_args(out)
        marker = args.index("--")
        args = args[:marker] + [
            "--", "/bin/sh", "-c",
            "test ! -e /dev/bus/usb && test ! -e /dev/mem && test ! -e /dev/uio0",
        ]
        completed = subprocess.run(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=15, check=False,
        )
        return "PASS" if completed.returncode == 0 else "BWRAP_NAMESPACE_FAILED"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return error_code(exc)

def agent_status(supervisor, out: Path) -> str:
    try:
        # Exact previously reviewed read-only Codex call. Never run the
        # trusted hardware supervisor, never open USB, publish no model text.
        supervisor.codex_request(out)
        return "PASS"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return error_code(exc)

def firmware_status() -> str:
    raw = os.environ.get("SIGROK_FIRMWARE_PATH")
    if not raw:
        return "NOT_CONFIGURED_INFORMATIONAL"
    path = Path(raw)
    return ("CONFIGURED_READABLE" if path.is_dir() and
            not path.is_symlink() and os.access(path, os.R_OK | os.X_OK)
            else "CONFIGURED_NOT_READABLE")

def write_report(out: Path, report: dict, exit_code: int) -> None:
    # Only fixed non-sensitive enum strings leave the worker.
    for status in report["checks"].values():
        if not isinstance(status, str) or len(status) > 80:
            raise SystemExit("INVALID_SANITIZED_REPORT")
    (out / "report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (out / "exit_code").write_text(str(exit_code) + "\n", encoding="ascii")
    with (out / "SHA256SUMS").open("w", encoding="ascii") as handle:
        for name in ("report.json", "exit_code"):
            digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
            handle.write(digest + "  " + name + "\n")

def run() -> int:
    check_worker()
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id.isascii() or not run_id.isdecimal():
        raise SystemExit("INVALID_RUN_ID")
    out = Path(os.environ["RUNNER_TEMP"]) / ("plasma-la2016-diagnose-" + run_id)
    out.mkdir(mode=0o700, exist_ok=False)
    supervisor = load_supervisor()
    checks = {}
    checks["pinned_appimage"] = passive_status(supervisor.trusted_appimage)
    # kingst_connection reads sysfs, checks DAC and passive fuser ownership;
    # it does not open any /dev/bus/usb device.
    checks["usb_metadata_dac_owner"] = passive_status(supervisor.kingst_connection)
    checks["runner_codex_cli"] = cli_status()
    checks["firmware_path"] = firmware_status()
    with tempfile.TemporaryDirectory(prefix="agent-", dir=out) as tmp:
        agent_home = Path(tmp)
        (agent_home / "agent").mkdir(mode=0o700)
        checks["bwrap_usb_isolation"] = namespace_status(supervisor, agent_home)
        checks["codex_readonly_request"] = (
            agent_status(supervisor, agent_home)
            if checks["bwrap_usb_isolation"] == "PASS"
            and checks["runner_codex_cli"] == "PASS"
            else "NOT_RUN_PREREQUISITE"
        )
    mandatory = ("pinned_appimage", "usb_metadata_dac_owner", "runner_codex_cli",
                 "bwrap_usb_isolation", "codex_readonly_request")
    ok = all(checks[key] == "PASS" for key in mandatory)
    report = {
        "schema": "plasma.la2016.readonly-diagnostic.v1",
        "result": "PASS_DIAGNOSTIC_PREREQUISITES" if ok else "NO_GO_DIAGNOSTIC",
        "checks": checks,
        "physical_usb_open": False, "pwm_enabled": False,
        "ch0_capture": "NOT_RUN", "z2_fpga": "NOT_RUN",
        "usb_hub_power": "NOT_RUN", "external_dut": "NOT_RUN",
    }
    write_report(out, report, 0 if ok else 2)
    print("LA2016 diagnostic: " + report["result"] + "; sanitized checks in artifact")
    return 0 if ok else 2

def self_test() -> None:
    event = {
        "action": "created", "repository": {"full_name": REPO},
        "sender": {"login": OWNER}, "issue": {"number": 981},
        "comment": {"user": {"login": OWNER}, "body": COMMAND},
    }
    assert authorize(event, OWNER, REPO, "refs/heads/main")
    for actor, repository, ref in (
        ("attacker", REPO, "refs/heads/main"),
        (OWNER, "attacker/plasma", "refs/heads/main"),
        (OWNER, REPO, "refs/heads/feature"),
    ):
        assert not authorize(event, actor, repository, ref)
    for key, value in (
        ("action", "edited"), ("issue.number", 999),
        ("issue.pull_request", {"url": "pr"}),
        ("comment.body", COMMAND + "\n"),
        ("comment.body", COMMAND + "; unsafe"),
        ("comment.user.login", "attacker"),
        ("sender.login", "attacker"),
    ):
        bad = copy.deepcopy(event)
        cur = bad
        items = key.split(".")
        for item in items[:-1]:
            cur = cur[item]
        cur[items[-1]] = value
        assert not authorize(bad, OWNER, REPO, "refs/heads/main")
    assert error_code(ValueError("KINGST_APPIMAGE_SHA_MISMATCH")) == "KINGST_APPIMAGE_SHA_MISMATCH"
    assert error_code(ValueError("secret-value-and-private-path")) == "UNEXPECTED_ERROR"
    wf = (Path(__file__).resolve().parents[1] /
          ".github/workflows/plasma-codex-la2016-diagnose.yml").read_text()
    for needed in (
        "github.actor == 'physicslu'", "needs.authorize.outputs.reviewed_sha",
        "runs-on: [self-hosted, linux, x64, plasma-codex]",
        "persist-credentials: false", "contents: read",
        "python3 scripts/plasma-codex-la2016-diagnose.py --run",
    ):
        assert needed in wf, needed
    for forbidden in ("pull_request_target:", "sudo ", "docker.sock",
                      "permissions: write-all", "secrets: inherit"):
        assert forbidden not in wf
    print("LA2016 owner-only read-only diagnostic offline contract PASS")

def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--event":
        event = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        if not authorize(event, os.environ.get("GITHUB_ACTOR", ""),
                         os.environ.get("GITHUB_REPOSITORY", ""),
                         os.environ.get("GITHUB_REF", "")):
            raise SystemExit("DENIED_OWNER_DISPATCH")
        print("LA2016 diagnostic owner authorization PASS")
        return 0
    if len(sys.argv) == 2 and sys.argv[1] == "--run":
        return run()
    raise SystemExit("Usage: --self-test | --event EVENT_JSON | --run")

if __name__ == "__main__":
    raise SystemExit(main())

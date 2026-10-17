#!/usr/bin/env python3
"""Issue #981: direct Codex CLI -> sigrok LA2016. No JSON action intermediary.

Only the independent deadline OFF guard and offline evidence verifier are trusted
host helpers; they do not choose/relay Codex's instrument commands. The LIVE
entry is owner-only after separately approved Gate 2 + one hardware authorization.
"""
from __future__ import annotations
import argparse
import configparser
import copy
import fcntl
import hashlib
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import shutil
import signal
import socket
import statistics
import struct
import subprocess
import sys
import time
import zipfile

REPO = "physicslu/plasma"
OWNER = "physicslu"
CMD = "/plasma-codex la2016-direct 981"
APP = Path("/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage")
APP_HASH = "b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475"
USB_ROOT = Path("/sys/bus/usb/devices")
LOCK = Path("/run/lock/plasma-la2016.lock")
CASES = ((1000, 50), (2000, 25))
MAX_SAMPLES = 250000
# A live hardware budget is NOT a physical PWM-ON timer. The independent
# watchdog is a best-effort OFF attempt; no guaranteed electrical cutoff.
CODEX_TIMEOUT_SECONDS = 600  # Ten-minute live execution; never auto-retry actuation.
# One initial preparation attempt plus THREE escalating timeout-only retries.
# Hardware USB is masked in every preparation attempt.
PREPARATION_TIMEOUT_SECONDS = (300, 600, 900, 1200)
WATCHDOG_DEADLINE_SECONDS = 635
AGENT_TERM_GRACE_SECONDS = 8
AGENT_KILL_GRACE_SECONDS = 5
PRIVATE_LOG_RETENTION_DAYS = 14
# Real device must never be driven by PR-triggered execution.
def authorized(e: dict, actor: str, repo: str, ref: str) -> bool:
    i, c, s, r = (e.get("issue") or {}, e.get("comment") or {},
                  e.get("sender") or {}, e.get("repository") or {})
    return (e.get("action") == "created" and repo == REPO
            and r.get("full_name") == REPO and actor == OWNER
            and s.get("login") == OWNER and c.get("user", {}).get("login") == OWNER
            and i.get("number") == 981 and not i.get("pull_request")
            and c.get("body") == CMD and ref == "refs/heads/main")

def worker_identity() -> None:
    if (socket.gethostname() != "SWPC" or os.geteuid() == 0
            or pwd.getpwuid(os.geteuid()).pw_name != "plasma-codex"
            or os.getenv("RUNNER_NAME") != "SWPC-plasma-codex"
            or os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("GITHUB_EVENT_NAME") != "issue_comment"
            or os.getenv("GITHUB_REPOSITORY") != REPO
            or os.getenv("GITHUB_REF") != "refs/heads/main"):
        raise ValueError("WORKER_IDENTITY_DENIED")
    groups = set(os.getgroups())
    if 0 in groups:
        raise ValueError("ROOT_GROUP_DENIED")
    if grp.getgrnam("plasma-codex-io").gr_gid not in groups:
        raise ValueError("LA_GROUP_NOT_LOADED")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for buf in iter(lambda: f.read(1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()

def pinned_app() -> None:
    if APP.is_symlink() or not APP.is_file() or not os.access(APP, os.X_OK):
        raise ValueError("APPIMAGE_MISSING")
    if sha256(APP) != APP_HASH:
        raise ValueError("APPIMAGE_SHA_MISMATCH")

def detect_la() -> tuple[str, Path]:
    found: list[tuple[str,Path]] = []
    for entry in USB_ROOT.iterdir():
        try:
            if (entry.joinpath("idVendor").read_text().strip().lower(),
                entry.joinpath("idProduct").read_text().strip().lower()) != ("77a1", "01a2"):
                continue
            bus, dev = (int(entry.joinpath(n).read_text()) for n in ("busnum", "devnum"))
            if not (1 <= bus <= 999 and 1 <= dev <= 999):
                raise ValueError("BAD_USB_ADDRESS")
            found.append((f"{bus}.{dev}", Path(f"/dev/bus/usb/{bus:03}/{dev:03}")))
        except (OSError, ValueError):
            continue
    if len(found) != 1:
        raise ValueError("LA2016_NOT_UNIQUE")
    conn, device = found[0]
    if not device.is_char_device() or not os.access(device, os.R_OK | os.W_OK):
        raise ValueError("LA2016_DAC_DENIED")
    if not shutil.which("fuser"):
        raise ValueError("FUSER_MISSING")
    p = subprocess.run(["fuser", "-s", str(device)], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=5, check=False)
    if p.returncode != 1:
        raise ValueError("LA2016_BUSY_OR_UNKNOWN")
    return conn, device

def physical_off(conn: str, private_log: Path | None = None) -> bool:
    """Issue OFF directly; stdout/stderr are private if explicitly requested."""
    cmd = [str(APP), "--appimage-extract-and-run", "--loglevel", "4",
           "--driver", "kingst-la2016:conn=" + conn,
           "--config", "channel_group=PWM1:enabled=off", "--set"]
    if private_log is None:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=16, check=False)
    else:
        fd = os.open(private_log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as private:
            p = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                               stdout=private, stderr=subprocess.STDOUT,
                               timeout=16, check=False)
    return p.returncode == 0


def resolver_bind_args(resolv: Path = Path("/etc/resolv.conf")) -> list[str]:
    """Restore just the verified systemd-resolved stub, never the host /run.

    The host's /etc/resolv.conf may be a symlink into /run.  --tmpfs /run
    otherwise breaks that symlink inside bubblewrap (confirmed on SWPC).
    """
    try:
        target = resolv.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("DNS_RESOLV_CONF_UNAVAILABLE") from exc
    if not target.is_file() or not os.access(target, os.R_OK):
        raise ValueError("DNS_RESOLV_CONF_UNREADABLE")
    run_root = Path("/run")
    if target == run_root or run_root in target.parents:
        if target not in {
            Path("/run/systemd/resolve/stub-resolv.conf"),
            Path("/run/systemd/resolve/resolv.conf"),
        }:
            raise ValueError("DNS_RUN_TARGET_NOT_ALLOWLISTED")
        return ["--dir", "/run/systemd", "--dir", "/run/systemd/resolve",
                "--ro-bind", str(target), str(target)]
    # Regular /etc/resolv.conf, or a symlink outside /run: ro-bind / / suffices.
    return []


def private_run_directory(rid: str) -> Path:
    """Owner-private durable log storage, deliberately outside RUNNER_TEMP."""
    if not re.fullmatch(r"[0-9]+", rid):
        raise ValueError("PRIVATE_RUN_ID_INVALID")
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    if home.is_symlink() or not home.is_dir():
        raise ValueError("PRIVATE_LOG_HOME_UNSAFE")
    root = home
    # .local is not necessarily private, but all children must be owner 0700.
    for name in (".local", "state", "plasma", "codex-runs"):
        root = root / name
        if root.is_symlink():
            raise ValueError("PRIVATE_LOG_SYMLINK_DENIED")
        if not root.exists():
            root.mkdir(mode=0o700)
        mode = root.stat()
        if not stat.S_ISDIR(mode.st_mode) or mode.st_uid != os.geteuid():
            raise ValueError("PRIVATE_LOG_DIRECTORY_OWNER_DENIED")
        if name in {"plasma", "codex-runs"} and mode.st_mode & 0o077:
            raise ValueError("PRIVATE_LOG_DIRECTORY_MODE_DENIED")
    prune_private_logs(root)
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    if not re.fullmatch(r"[1-9][0-9]{0,3}", attempt):
        raise ValueError("PRIVATE_LOG_ATTEMPT_INVALID")
    result = root / (rid + "-attempt-" + attempt)
    if result.is_symlink() or result.exists():
        raise ValueError("PRIVATE_LOG_RUN_COLLISION")
    result.mkdir(mode=0o700)
    return result


def prune_private_logs(root: Path) -> None:
    """Remove only stale, owned 0700 numeric run directories older than 14d.

    Called only under the owner-specific GitHub Actions concurrency lock.
    Never follow symlinks or change host permissions.
    """
    cutoff = time.time() - PRIVATE_LOG_RETENTION_DAYS * 86400
    for folder in root.iterdir():
        if not re.fullmatch(r"[0-9]+-attempt-[0-9]+", folder.name):
            continue
        if folder.is_symlink():
            continue
        st = folder.stat(follow_symlinks=False)
        if (stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                and (st.st_mode & 0o077) == 0 and st.st_mtime < cutoff):
            shutil.rmtree(folder)


def network_preflight(prefix: list[str]) -> str:
    """Check DNS in the exact Codex sandbox before every model invocation.

    API authentication is NOT established by DNS and cannot be inferred here.
    """
    expr = (
        "import pathlib,socket,sys; "
        "p=pathlib.Path('/etc/resolv.conf'); "
        "sys.exit(21) if not p.is_file() else None; "
        "try_it=socket.getaddrinfo('api.openai.com',443,type=socket.SOCK_STREAM); "
        "sys.exit(0 if try_it else 22)"
    )
    try:
        p = subprocess.run(prefix + ["--", sys.executable, "-c", expr],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("CODEX_NETWORK_PREFLIGHT_ERROR") from exc
    if p.returncode == 21:
        raise ValueError("CODEX_NETWORK_RESOLV_CONF_MISSING")
    if p.returncode != 0:
        raise ValueError("CODEX_NETWORK_DNS_FAIL")
    return "DNS_PASS_MODEL_API_UNVERIFIED"

def sandbox_prefix(device: Path, evidence: Path, *, allow_device: bool = True) -> list[str]:
    """OS-enforced LA-only /dev despite worker DAC to other devices.

    The outer bubblewrap namespace is the hardware isolation boundary.
    Codex's inner 'danger-full-access' mode does NOT escape this namespace,
    immutable checkout, or masked private credentials.
    """
    bwrap = shutil.which("bwrap")
    if not bwrap or not shutil.which("codex"):
        raise ValueError("CODEX_OR_BWRAP_MISSING")
    if not re.fullmatch(r"/dev/bus/usb/[0-9]{3}/[0-9]{3}", str(device)):
        raise ValueError("UNSAFE_USB_PATH")
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    if not (home / ".codex").is_dir() or (home / ".codex").is_symlink():
        raise ValueError("CODEX_AUTH_HOME_MISSING")
    if evidence.is_symlink() or not evidence.is_dir():
        raise ValueError("EVIDENCE_DIR_INVALID")
    parts = [
        bwrap, "--die-with-parent", "--new-session", "--unshare-pid",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/run", "--tmpfs", "/tmp",
    ]
    parts += resolver_bind_args()
    if allow_device:
        parts += ["--dir", "/dev/bus", "--dir", "/dev/bus/usb",
                  "--dir", str(device.parent), "--dev-bind", str(device), str(device)]
    parts += ["--bind", str(evidence), str(evidence)]
    for private in (home / ".ssh", home / ".config" / "plasma"):
        if private.is_dir():
            if private.is_symlink():
                raise ValueError("PRIVATE_HOME_SYMLINK")
            parts += ["--tmpfs", str(private)]
    parts += ["--bind", str(home / ".codex"), str(home / ".codex"),
              "--chdir", os.environ.get("GITHUB_WORKSPACE", "/")]
    return parts

def namespace_test(prefix: list[str], device: Path) -> None:
    # No Python stdout/USB addresses published; check actual namespace before PWM.
    expr = ("from pathlib import Path; import sys, os; "
            "dev=Path(sys.argv[1]); "
            "assert dev.exists() and dev.is_char_device(); "
            "assert list(Path('/dev/bus/usb').glob('*/*')) == [dev]; "
            "assert not Path('/dev/mem').exists(); "
            "assert not list(Path('/dev').glob('ttyUSB*')); "
            "assert not Path('/home/plasma-codex/.ssh/id_rsa').exists(); "
            "fd=os.open(dev, os.O_RDWR|os.O_NONBLOCK|os.O_CLOEXEC); os.close(fd)")
    args = prefix + ["--", sys.executable, "-c", expr, str(device)]
    p = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=20, check=False)
    if p.returncode != 0:
        raise ValueError("LA_ONLY_NAMESPACE_NOT_PROVEN")

def prompt(evidence: Path, conn: str) -> str:
    return f"""PLASMA Issue #981: ONE owner-approved KINGST LA2016 PWM1 -> SAME LA2016 CH0
direct loopback. You are the EXECUTING Codex engineering agent, not a JSON intent
requester. Your commands call sigrok-cli directly inside a rootless OS namespace
which exposes ONLY the approved LA2016 USB node. No Python Supervisor forwarding.
Read docs/evidence/la2016-pwm-loopback/2026-10-16/README.md for measured
acceptance and exact command patterns; inspect other public tools as needed.
Do not open Z2, FT2232, USB Hub, FPGA, SSH, JTAG, DUT, or change host services,
firmware, permissions, source code or Git history. Do not browse unrelated
networks, paths or private credentials. Do not install/download packages.
AppImage is exactly /opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage.
CURRENT device connection is kingst-la2016:conn={conn} (never cache this).
Only PWM1 on this instrument, only 1kHz/50% and 2kHz/25%, samplerate 1m,
100000 CH0 samples ON per setting, then explicit PWM1 enabled=off.
Collect distinct 20000-sample OFF captures after each setting. The four
required real archive filenames in {evidence} are:
1000hz-on.sr 1000hz-off.sr 2000hz-on.sr 2000hz-off.sr.
Use --appimage-extract-and-run; log files under evidence if needed but
do not embed credentials, USB IDs, host/user/path info or logs in your reply.
Before any configuration/capture, ensure no other process owns the LA.
You MUST execute PWM1 OFF after each ON acquisition and in finally/EXIT
handling as far as possible. An independent host-side deadline OFF is armed.
Do not alter, stop or suppress it. If any control fails, stop, attempt OFF,
report NO_GO. No screenshots, fabricated PASS, synthetic captures or replay
of archived records. Operator already confirmed SAME LA PWM1-to-CH0 wiring.
Your last response is a concise factual test summary, not an action JSON.
"""

def bits(path: Path) -> list[int]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 1_500_000:
        raise ValueError("WAVEFORM_FILE_INVALID")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "metadata" not in names or z.getinfo("metadata").file_size > 8192:
            raise ValueError("WAVEFORM_METADATA_INVALID")
        cfg = configparser.ConfigParser()
        cfg.read_string(z.read("metadata").decode("utf-8"))
        dv = cfg["device 1"]
        if (dv["probe1"], dv["samplerate"], dv["unitsize"]) != ("CH0", "1 MHz", "2"):
            raise ValueError("WAVEFORM_CHANNEL_MISMATCH")
        chunks = sorted((n for n in names if re.fullmatch(r"logic-1-[0-9]+", n)),
                        key=lambda n: int(n.split("-")[-1]))
        if not chunks or sum(z.getinfo(n).file_size for n in chunks) > MAX_SAMPLES * 2:
            raise ValueError("WAVEFORM_TOO_LARGE")
        raw = b"".join(z.read(n) for n in chunks)
    if len(raw) % 2 or not 20_000 <= len(raw) // 2 <= MAX_SAMPLES:
        raise ValueError("WAVEFORM_SAMPLE_COUNT")
    return [v[0] & 1 for v in struct.iter_unpack("<H", raw)]

def validate_pair(on: Path, off: Path, hz: int, duty: int) -> dict:
    values = bits(on)
    shifts = [i for i in range(1,len(values)) if values[i] != values[i-1]]
    rises = [i for i in shifts if values[i]]
    falls = [i for i in shifts if not values[i]]
    periods, highs = [], []
    for a,b in zip(rises, rises[1:]):
        f=[x for x in falls if a<x<b]
        if len(f)!=1:
            raise ValueError("WAVEFORM_EDGES_INVALID")
        periods.append(b-a)
        highs.append(f[0]-a)
    expected_period = 1_000_000//hz
    expected_high = expected_period*duty//100
    if (len(periods)<20 or
        any(abs(p-expected_period)>1 for p in periods) or
        any(abs(h-expected_high)>1 for h in highs)):
        raise ValueError("WAVEFORM_OUTSIDE_TOLERANCE")
    low=bits(off)
    if any(low):
        raise ValueError("PWM_OFF_CH0_NOT_LOW")
    return {
        "requested_frequency_hz": hz, "requested_duty_percent": duty,
        "measured_frequency_hz": round(1_000_000/statistics.mean(periods),3),
        "measured_duty_percent": round(100*sum(highs)/sum(periods),3),
        "complete_cycles": len(periods), "on_samples": len(values),
        "off_samples": len(low),
        "on_sha256": sha256(on), "off_sha256": sha256(off),
        "result": "PASS",
    }

def evidence_report(root: Path) -> list[dict]:
    # Two byte-for-byte copies of the archival ON captures cannot be new HIL
    # evidence. This only catches naive replay; it is not cryptographic proof
    # of instrument origin.
    archive = (Path(__file__).resolve().parents[1] /
               "docs/evidence/la2016-pwm-loopback/2026-10-16")
    archive_dirs = ("1khz-50pct", "2khz-25pct")
    archived_on = 0
    for (hz, _duty), folder in zip(CASES, archive_dirs):
        candidate = root / f"{hz}hz-on.sr"
        if candidate.exists() and sha256(candidate) == sha256(archive / folder / "on.sr"):
            archived_on += 1
    if archived_on == 2:
        raise ValueError("ARCHIVED_CAPTURE_REPLAY_DENIED")
    return [validate_pair(root/f"{hz}hz-on.sr", root/f"{hz}hz-off.sr", hz, duty)
            for hz,duty in CASES]

def write_watchdog_receipt(out: Path, result: str) -> None:
    """Persist a sanitized local receipt; not an electrical OFF proof."""
    allowed = {"PARENT_OFF_COMMAND_OK", "DEADLINE_OFF_COMMAND_OK",
               "DEADLINE_OFF_FAILED_OR_UNKNOWN"}
    if result not in allowed:
        raise ValueError("INVALID_WATCHDOG_RESULT")
    temp = out / "watchdog-receipt.tmp"
    temp.write_text(result + "\n", encoding="utf-8")
    os.replace(temp, out / "watchdog-receipt")


def watchdog(out: Path, conn: str, private_logs: Path | None = None) -> int:
    worker_identity()
    if not re.fullmatch(r"[1-9][0-9]{0,2}\.[1-9][0-9]{0,2}", conn):
        return 2
    (out/"armed").touch(exist_ok=False)
    deadline = time.monotonic() + WATCHDOG_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if (out / "off-confirmed").is_file():
            write_watchdog_receipt(out, "PARENT_OFF_COMMAND_OK")
            return 0
        time.sleep(1)
    # Physical command is still best-effort; do not claim output is LOW.
    try:
        pinned_app()
        success = physical_off(conn, (private_logs or out) / "watchdog-off-private.log")
    except (OSError, ValueError, subprocess.SubprocessError):
        success = False
    write_watchdog_receipt(
        out, "DEADLINE_OFF_COMMAND_OK" if success else "DEADLINE_OFF_FAILED_OR_UNKNOWN"
    )
    return 0 if success else 2

def terminate_agent(proc: subprocess.Popen, *, sleep_grace: int = AGENT_TERM_GRACE_SECONDS) -> str:
    """Bounded cleanup of the rootless bwrap launch process group.

    A detached descendant can escape process groups; bwrap --die-with-parent
    further limits it but cannot guarantee all libusb handles have closed.
    No OFF result is trusted solely because SIGTERM was sent.
    """
    if proc.poll() is not None:
        return "ALREADY_EXITED"
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return "ALREADY_EXITED"
    except OSError:
        return "TERMINATION_UNKNOWN"
    try:
        proc.wait(timeout=sleep_grace)
        return "SIGTERM_REAPED"
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=AGENT_KILL_GRACE_SECONDS)
            return "SIGKILL_REAPED"
        except (OSError, subprocess.TimeoutExpired):
            return "TERMINATION_UNKNOWN"


def invoke_codex(args: list[str], work: str, out: Path,
                 *, timeout_seconds: int | None = None) -> dict[str, object]:
    """Save *raw* stdout/stderr privately; release only enum diagnostics."""
    # Deliberately avoid putting arbitrary model/tool output in Actions logs.
    safe_env = {k: v for k, v in os.environ.items()
                if k not in {"GITHUB_TOKEN", "GH_TOKEN", "SSH_AUTH_SOCK",
                             "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}
                and not k.endswith(("_PASSWORD", "_PRIVATE_KEY", "_SECRET"))}
    result: dict[str, object] = {
        "status": "NOT_STARTED", "termination": "NOT_NEEDED",
        "elapsed_seconds": 0
    }
    if timeout_seconds is None:
        timeout_seconds = CODEX_TIMEOUT_SECONDS
    started = time.monotonic()
    with (os.fdopen(os.open(out / "codex-stdout-private.jsonl",
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stdout,
          os.fdopen(os.open(out / "codex-stderr-private.log",
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stderr):
        proc = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            text=True, env=safe_env, start_new_session=True,
            close_fds=True
        )
        result["status"] = "STARTED"
        try:
            proc.communicate(input=work, timeout=timeout_seconds)
            result["status"] = "PASS" if proc.returncode == 0 else "EXIT_NONZERO"
            result["exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            result["status"] = "TIMEOUT"
            result["termination"] = terminate_agent(proc)
            # communicate() may have written stdin before timing out.
            # Process-group reap, not a Codex answer, precedes host PWM OFF.
        except (OSError, ValueError):
            result["status"] = "SPAWN_OR_IO_ERROR"
            result["termination"] = terminate_agent(proc)
        finally:
            result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def preparation_prompt() -> str:
    return """PLASMA Issue #981 LA2016 non-actuating preparation.
You are Codex preparing to execute a previously owner-approved, separately
isolated LA2016 PWM1->CH0 experiment. In THIS session you have NO USB nodes,
NO ability to drive PWM, and NO hardware work is authorized. DO NOT attempt
to access USB, network instruments, Z2, FT2232, DUT, JTAG, USB Hub or FPGA.
Read checked-in public docs/evidence/la2016-pwm-loopback/2026-10-16/README.md
and verify the documented CLI syntax. Prepare your own concise checklist of
expected steps and risks. You can use ordinary read-only shell commands in
the repository (do not run any instrument commands). No downloads,
credential reads, privilege escalation, host configuration or file edits.
Return concise preparation notes, no JSON API schema. This is not a test PASS.
"""


def preparation_namespace_test(prefix: list[str]) -> None:
    """No real USB hardware access while Codex may be automatically retried."""
    expr = ("from pathlib import Path; "
            "assert not list(Path('/dev/bus/usb').glob('*/*')); "
            "assert not Path('/dev/mem').exists(); "
            "assert not list(Path('/dev').glob('ttyUSB*'))")
    proc = subprocess.run(prefix + ["--", sys.executable, "-c", expr],
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=20, check=False)
    if proc.returncode != 0:
        raise ValueError("PREPARATION_USB_MASK_NOT_PROVEN")


def prepare_codex(out: Path, private_logs: Path | None = None) -> list[dict[str, object]]:
    """Retry ONLY an inert Codex planning session, never a real PWM session.

    The outer bwrap --dev mount hides LA and all other USB devices. No physical
    claim/control occurs in this function. Do not infer model authorization.
    """
    notes: list[dict[str, object]] = []
    root = (private_logs or out) / "preparation"
    root.mkdir(mode=0o700)
    cmd = shutil.which("codex")
    if not cmd:
        raise ValueError("PREPARATION_CODEX_MISSING")
    for attempt, budget in enumerate(PREPARATION_TIMEOUT_SECONDS, start=1):
        folder = root / f"attempt-{attempt}"
        folder.mkdir(mode=0o700)
        prefix = sandbox_prefix(Path("/dev/bus/usb/001/001"), folder,
                                allow_device=False)
        preparation_namespace_test(prefix)
        network_preflight(prefix)
        argv = prefix + [
            "--", cmd, "--ask-for-approval", "never", "exec", "--json",
            "--sandbox", "danger-full-access",
            "--output-last-message", str(folder / "last-message-private.txt"), "-"
        ]
        outcome = invoke_codex(argv, preparation_prompt(), folder,
                               timeout_seconds=budget)
        # Only bounded categorical evidence is returned from private output.
        entry = {"attempt": attempt, "timeout_seconds": budget,
                 "status": outcome["status"],
                 "termination": outcome["termination"],
                 "elapsed_seconds": outcome["elapsed_seconds"]}
        notes.append(entry)
        # Every step is durably recorded even if all retries time out.
        receipt = out / "preparation-receipts.json"
        temp = out / "preparation-receipts.tmp"
        temp.write_text(json.dumps(notes, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, receipt)
        if outcome["status"] == "PASS":
            return notes
        # Failed, un-reaped process, or other error is NOT safe to retry.
        if (outcome["status"] != "TIMEOUT"
            or outcome["termination"] not in {"SIGTERM_REAPED", "SIGKILL_REAPED"}):
            raise ValueError("PREPARATION_NOT_RETRYABLE")
    raise ValueError("PREPARATION_TIMEOUT_RETRY_EXHAUSTED")


def run() -> int:
    worker_identity()
    rid=os.getenv("GITHUB_RUN_ID","")
    if not re.fullmatch(r"[0-9]+",rid):
        raise ValueError("RUN_ID_INVALID")
    out=Path(os.environ["RUNNER_TEMP"])/("plasma-la2016-direct-"+rid)
    if out.exists() or out.is_symlink():
        raise ValueError("EXISTING_OUTPUT_DENIED")
    out.mkdir(mode=0o700)
    private_logs = private_run_directory(rid)
    evidence=out/"evidence"
    evidence.mkdir(mode=0o700)
    report={"schema":"plasma.la2016.direct.v1","result":"NO_GO","agent_exec":"NOT_RUN",
            "failure_stage":"NOT_STARTED","primary_failure":"NONE",
            "agent_termination":"NOT_NEEDED","codex_elapsed_seconds":0,
            "preparation_attempts":[],"preparation_status":"NOT_RUN",
            "network_preflight":"NOT_RUN","live_attempts":0,
            "cases":[],"pwm_off_command":"NOT_RUN","independent_off_watchdog":"NOT_ARMED",
            "z2_fpga":"NOT_RUN","usb_hub_power":"NOT_RUN","external_dut":"NOT_RUN"}
    rc=2
    conn=None
    try:
        report["failure_stage"] = "APPIMAGE_PREFLIGHT"
        pinned_app()
        report["failure_stage"] = "CODEX_PREPARATION"
        try:
            report["preparation_attempts"] = prepare_codex(out, private_logs)
            report["preparation_status"] = "PASS"
            report["network_preflight"] = "DNS_PASS_MODEL_API_UNVERIFIED"
        except ValueError as exc:
            report["preparation_status"] = "FAILED_OR_RETRY_EXHAUSTED"
            if str(exc).startswith(("CODEX_NETWORK_", "DNS_")):
                report["failure_stage"] = "NETWORK_PREFLIGHT"
                report["primary_failure"] = str(exc)
            receipt = out / "preparation-receipts.json"
            if receipt.is_file():
                report["preparation_attempts"] = json.loads(
                    receipt.read_text(encoding="utf-8"))
            raise
        report["failure_stage"] = "USB_PREFLIGHT"
        conn,dev=detect_la()
        with LOCK.open("a+") as file:
            fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # Fail closed unless the sandbox can really expose ONE LA device.
            report["failure_stage"] = "NAMESPACE_PREFLIGHT"
            prefix=sandbox_prefix(dev,evidence)
            namespace_test(prefix,dev)
            report["failure_stage"] = "NETWORK_PREFLIGHT"
            report["network_preflight"] = network_preflight(prefix)
            report["failure_stage"] = "WATCHDOG_ARM"
            # Secure the independent OFF attempt before asking Codex to actuate.
            guard=subprocess.Popen(
                [sys.executable,str(Path(__file__).resolve()),"--watchdog",
                 "--output",str(out),"--connection",conn,
                 "--private-output",str(private_logs)],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True,
                env={k:v for k,v in os.environ.items() if k!="RUNNER_TRACKING_ID"},
            )
            for _ in range(50):
                if (out/"armed").is_file() and guard.poll() is None:
                    break
                if guard.poll() is not None:
                    raise ValueError("WATCHDOG_FAILED_TO_ARM")
                time.sleep(0.1)
            else:
                raise ValueError("WATCHDOG_ARM_TIMEOUT")
            report["independent_off_watchdog"]="ARMED"
            report["failure_stage"] = "CODEX_EXEC"
            report["live_attempts"] = 1  # Physical execution may never auto-retry.
            try:
                codex=shutil.which("codex")
                args=prefix+[
                    "--",codex,"--ask-for-approval","never","exec","--json",
                    "--sandbox","danger-full-access",
                    "--output-last-message",str(evidence/"agent-result.txt"),"-"
                ]
                # Full CLI sandbox disabled *inside* outer fail-closed bwrap:
                # real /dev, host write paths and private Z2 credentials hidden.
                outcome=invoke_codex(args,prompt(evidence,conn),private_logs)
                report["agent_exec"]=outcome["status"]
                report["agent_termination"]=outcome["termination"]
                report["codex_elapsed_seconds"]=outcome["elapsed_seconds"]
                if outcome["status"]!="PASS":
                    report["primary_failure"]="CODEX_"+str(outcome["status"])
                    raise ValueError("DIRECT_CODEX_FAILED")
                report["failure_stage"]="EVIDENCE_VERIFICATION"
                report["cases"]=evidence_report(evidence)
                report["result"]="PASS_DIRECT_LA2016_LOOPBACK"
                report["failure_stage"]="FINAL_OFF"
                rc=0
            finally:
                # OFF regardless of Codex or waveform verifier outcome.
                try:
                    # The model launch group has been reaped (or marked unknown)
                    # before the final OFF attempt; preserve first failure.
                    if physical_off(conn, private_logs / "parent-off-private.log"):
                        report["pwm_off_command"]="COMMAND_OK"
                        (out/"off-confirmed").touch(exist_ok=False)
                    else:
                        report["pwm_off_command"]="FAILED_OR_UNKNOWN"
                        if report["primary_failure"]=="NONE":
                            report["primary_failure"]="FINAL_OFF_COMMAND_NONZERO"
                        rc=2
                        report["result"]="NO_GO_OFF"
                except (OSError,ValueError,subprocess.SubprocessError):
                    if report["primary_failure"]=="NONE":
                        report["primary_failure"]="FINAL_OFF_COMMAND_ERROR"
                    report["pwm_off_command"]="FAILED_OR_UNKNOWN"
                    report["result"]="NO_GO_OFF"
                    rc=2
    except (OSError,ValueError,subprocess.SubprocessError,zipfile.BadZipFile,
            configparser.Error,KeyError,IndexError):
        if report["result"]!="NO_GO_OFF":
            report["result"]="NO_GO"
        if report["primary_failure"] == "NONE":
            report["primary_failure"]="FAIL_IN_"+str(report["failure_stage"])
        rc=2
    # A model response or an OFF command rc can never attest electrical LOW.
    # Before finalizing report/cleaning Runner temp, reconcile the watchdog
    # receipt. If parent OFF failed, allow deadline OFF to actually attempt
    # recovery; never mark that attempt as a physical CH0 LOW confirmation.
    if report["independent_off_watchdog"] == "ARMED":
        try:
            guard.wait(timeout=5 if report["pwm_off_command"]=="COMMAND_OK"
                       else WATCHDOG_DEADLINE_SECONDS + 20)
        except subprocess.TimeoutExpired:
            # Detached watchdog retains its best-effort OFF duty.
            pass
    receipt = out / "watchdog-receipt"
    report["watchdog_final_receipt"]=(
        receipt.read_text(encoding="utf-8").strip()
        if receipt.is_file() else "PENDING_OR_UNOBSERVED"
    )
    (out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    (out/"exit_code").write_text(str(rc)+"\n")
    with (out/"SHA256SUMS").open("w") as f:
        for name in ("report.json","exit_code"):
            f.write(sha256(out/name)+"  "+name+"\n")
        if rc==0:
            for hz,_ in CASES:
                for label in ("on","off"):
                    file=evidence/f"{hz}hz-{label}.sr"
                    f.write(sha256(file)+"  evidence/"+file.name+"\n")
    print("LA2016 direct Codex: "+report["result"],flush=True)
    return rc

def self_test() -> int:
    event={"action":"created","issue":{"number":981},
           "repository":{"full_name":REPO},
           "sender":{"login":OWNER},"comment":{"body":CMD,"user":{"login":OWNER}}}
    assert authorized(event,OWNER,REPO,"refs/heads/main")
    for a,r,ref in (("fake",REPO,"refs/heads/main"),
                    (OWNER,"other/repo","refs/heads/main"),
                    (OWNER,REPO,"refs/heads/pr")):
        assert not authorized(event,a,r,ref)
    for k,v in (("action","edited"),("issue.number",982),
                ("issue.pull_request",{"url":"pr"}),
                ("comment.body",CMD+"\n"),
                ("comment.body",CMD+" ;rm"),("comment.user.login","fake")):
        bad=copy.deepcopy(event);t=bad;p=k.split(".")
        for key in p[:-1]:
            t=t[key]
        t[p[-1]]=v
        assert not authorized(bad,OWNER,REPO,"refs/heads/main")
    fixture=Path(__file__).resolve().parents[1]/"docs/evidence/la2016-pwm-loopback/2026-10-16"
    for hz,duty,d in ((1000,50,"1khz-50pct"),(2000,25,"2khz-25pct")):
        a=validate_pair(fixture/d/"on.sr",fixture/d/"off.sr",hz,duty)
        assert a["result"]=="PASS" and a["off_samples"]>=20000
    src=Path(__file__).read_text()
    assert "codex" in src and "--dev-bind" in src
    assert "validate_agent_request" not in src.split("def self_test()")[0]
    assert CODEX_TIMEOUT_SECONDS == 600
    assert PREPARATION_TIMEOUT_SECONDS == (300, 600, 900, 1200)
    assert WATCHDOG_DEADLINE_SECONDS > CODEX_TIMEOUT_SECONDS
    print("LA2016 Direct owner gating, real archived waveform/off verification PASS")
    return 0

def main() -> int:
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    for arg in ("--self-test","--event","--run","--watchdog"):
        g.add_argument(arg,action="store_true")
    p.add_argument("--input",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--connection",type=str)
    p.add_argument("--private-output",type=Path)
    opts=p.parse_args()
    if opts.self_test:
        return self_test()
    if opts.event:
        if opts.input is None: return 2
        e=json.loads(opts.input.read_text())
        if not authorized(e,os.getenv("GITHUB_ACTOR",""),
                          os.getenv("GITHUB_REPOSITORY",""),os.getenv("GITHUB_REF","")):
            return 2
        print("LA2016 Direct owner Issue authorization PASS")
        return 0
    if opts.watchdog:
        if opts.output is None or opts.connection is None: return 2
        return watchdog(opts.output,opts.connection,opts.private_output)
    if opts.input or opts.output or opts.connection or opts.private_output: return 2
    return run()

if __name__=="__main__":
    raise SystemExit(main())

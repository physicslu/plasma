#!/usr/bin/env python3
"""Direct SWPC toolbox for the enrolled Z2 development board."""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PS_SOURCE = ROOT / "scripts/z2/bluepill-stage-a-ps.py"
PS_INSTALLED = "/opt/plasma/bluepill-manual-stage-a-20261027/ps-manual-stage-a.py"
PS_PYTHON = "/opt/plasma/python/3.12.13/bin/python3"
LA_APP = Path("/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage")
LA_SHA = "b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475"
LA_LOCK = Path("/run/lock/plasma-la2016.lock")
LA_USB = Path("/sys/bus/usb/devices")
LOGIN = Path.home() / ".config/plasma/z2-login-smoke.json"
KEY = Path.home() / ".ssh/plasma_z2_ed25519"
KNOWN = Path.home() / ".ssh/known_hosts"
SAMPLES = 25_000_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def private_login() -> dict[str, str]:
    directory, meta = LOGIN.parent.lstat(), LOGIN.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid()
            or stat.S_IMODE(directory.st_mode) != 0o700
            or not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
            or stat.S_IMODE(meta.st_mode) != 0o600):
        raise ValueError("PRIVATE_LOGIN_OWNER_OR_MODE")
    record = json.loads(LOGIN.read_text())
    if (not isinstance(record, dict) or
            not {"ssh_host", "ssh_username", "ssh_password"} <= set(record)
            or set(record) - {"ssh_host", "ssh_username", "ssh_password", "sudo_password"}):
        raise ValueError("PRIVATE_LOGIN_SCHEMA")
    if (record["ssh_username"] != "xilinx"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,250}", record["ssh_host"])):
        raise ValueError("Z2_LOGIN_TARGET")
    if not all(isinstance(record[k], str) and record[k] for k in ("ssh_password",)):
        raise ValueError("PRIVATE_LOGIN_VALUE")
    if "sudo_password" in record and not isinstance(record["sudo_password"], str):
        raise ValueError("PRIVATE_SUDO_VALUE")
    for path in (KEY, KNOWN):
        mode = path.lstat()
        if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.geteuid() or mode.st_mode & 0o077:
            raise ValueError("SSH_KEY_OR_KNOWN_HOSTS_UNTRUSTED")
    pinned = subprocess.run(["ssh-keygen", "-F", record["ssh_host"], "-f", str(KNOWN)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=5, check=False)
    if pinned.returncode:
        raise ValueError("Z2_HOST_KEY_NOT_PINNED")
    return record


def la_device() -> tuple[str, Path]:
    if not LA_APP.is_file() or not os.access(LA_APP, os.X_OK) or sha256(LA_APP) != LA_SHA:
        raise ValueError("LA_APP_MISSING_OR_CHANGED")
    firmware = Path.home() / ".local/share/sigrok-firmware"
    if not (firmware / "kingst-la-01a2.fw").is_file():
        raise ValueError("LA_FIRMWARE_MISSING")
    matches: list[tuple[str, Path]] = []
    for item in LA_USB.iterdir():
        try:
            if ((item / "idVendor").read_text().strip().lower(),
                    (item / "idProduct").read_text().strip().lower()) != ("77a1", "01a2"):
                continue
            bus, dev = (int((item / key).read_text()) for key in ("busnum", "devnum"))
            node = Path(f"/dev/bus/usb/{bus:03}/{dev:03}")
            if not stat.S_ISCHR(node.stat().st_mode) or not os.access(node, os.R_OK | os.W_OK):
                raise ValueError("LA_DAC_DENIED")
            matches.append((f"{bus}.{dev}", node))
        except (FileNotFoundError, PermissionError):
            continue
    if len(matches) != 1:
        raise ValueError("LA_NOT_UNIQUE_OR_ACCESS_DENIED")
    return matches[0]


def remote_code(source_sha: str) -> str:
    # The installed PS script must be byte-for-byte equal to the reviewed repo source.
    return ("import hashlib,json,os,platform,runpy,stat,sys\n"
            f"path={PS_INSTALLED!r}\nexpected={source_sha!r}\n"
            "file_stat=os.lstat(path)\n"
            "if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_uid != 0: "
            "raise RuntimeError('PS_SCRIPT_OWNER_OR_TYPE')\n"
            "actual=hashlib.sha256(open(path,'rb').read()).hexdigest()\n"
            "if actual != expected: raise RuntimeError('PS_SCRIPT_SHA_MISMATCH')\n"
            "print(json.dumps({'kind':'ps_environment','machine':platform.machine(),"
            "'python':sys.version.split()[0],'boot_id':open('/proc/sys/kernel/random/boot_id').read().strip(),"
            "'script_sha256':actual}),flush=True)\n"
            "sys.argv=[path,'--bluepill-removed']\n"
            "runpy.run_path(path,run_name='__main__')\n")


def ssh_run(login: dict[str, str], source_sha: str) -> subprocess.CompletedProcess[str]:
    import shlex

    command = "sudo -S -p '' " + PS_PYTHON + " -I -B -c " + shlex.quote(remote_code(source_sha))
    argv = ["ssh", "-F", "/dev/null", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + str(KNOWN), "-o", "ConnectTimeout=8",
            "-o", "ConnectionAttempts=1", "--",
            login["ssh_username"] + "@" + login["ssh_host"], command]
    password = login.get("sudo_password", login["ssh_password"])
    result = subprocess.run(argv, input=password + "\n", text=True,
                            capture_output=True, timeout=40, check=False)
    # Passwords and enrolled board address are never written to evidence.
    for secret in (login["ssh_password"], password, login["ssh_host"]):
        result.stdout = result.stdout.replace(secret, "[REDACTED]")
        result.stderr = result.stderr.replace(secret, "[REDACTED]")
    return result


def analyze_wave(path: Path) -> dict[str, object]:
    """Summarize digital levels without equating them with analog pad voltage."""
    states_seen: Counter[int] = Counter()
    rises = [0, 0, 0, 0]
    falls = [0, 0, 0, 0]
    samples = 0
    previous = None
    with zipfile.ZipFile(path) as archive:
        meta = archive.read("metadata").decode()
        if "samplerate=1 MHz" not in meta or "unitsize=2" not in meta:
            raise ValueError("LA_METADATA_UNEXPECTED")
        for channel in range(4):
            if f"probe{channel + 1}=CH{channel}" not in meta:
                raise ValueError("LA_CHANNEL_MAP_UNEXPECTED")
        names = sorted((name for name in archive.namelist() if re.fullmatch(r"logic-1-[0-9]+", name)),
                       key=lambda name: int(name.rsplit("-", 1)[1]))
        if not names:
            raise ValueError("LA_LOGIC_MISSING")
        for name in names:
            with archive.open(name) as stream:
                while chunk := stream.read(1 << 20):
                    if len(chunk) % 2:
                        raise ValueError("LA_LOGIC_TRUNCATED")
                    states = chunk[::2]  # four enabled digital probes fit in one byte
                    states_seen.update(states)
                    samples += len(states)
                    for state in states:
                        changed = 0 if previous is None else state ^ previous
                        if changed:
                            for channel in range(4):
                                bit = 1 << channel
                                if changed & bit:
                                    if state & bit:
                                        rises[channel] += 1
                                    else:
                                        falls[channel] += 1
                        previous = state
    if samples < SAMPLES:
        raise ValueError("LA_SAMPLE_COUNT_SHORT")
    counts = [sum(count for state, count in states_seen.items() if state & (1 << i))
              for i in range(4)]
    return {"sample_count": samples, "duration_s": samples / 1_000_000,
            "channels": {f"CH{i}": {"high_samples": counts[i], "rises": rises[i],
                                    "falls": falls[i]} for i in range(4)},
            "reference_ch2_high": counts[2] == samples,
            "clock_ch0_edges": rises[0] >= 1 and falls[0] >= 1,
            "dio_ch1_edges": rises[1] >= 1 and falls[1] >= 1,
            "clock_ch3_edges": rises[3] >= 1 and falls[3] >= 1}


def stop_capture(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=3)


def stage_a(out: Path) -> int:
    if out.exists() or out.is_symlink():
        raise ValueError("OUTPUT_EXISTS")
    login = private_login()
    conn, node = la_device()
    source_sha = sha256(PS_SOURCE)
    out.mkdir(parents=True, mode=0o700)
    out.chmod(0o700)
    wave = out / "stage-a.sr"
    report = out / "report.json"
    record: dict[str, object] = {"tool": "z2-toolbox stage-a", "source_sha256": source_sha,
                                 "host": os.uname().nodename, "host_machine": os.uname().machine,
                                 "host_python": sys.version.split()[0],
                                 "channel_map": {"CH0": "PmodBB P1 CLOCK", "CH1": "PmodBB P2 DIO",
                                                 "CH2": "Z2 3.3 V", "CH3": "PmodBB P1 CLOCK"},
                                 "la_conn": conn, "started_unix_ns": time.time_ns()}
    capture = None
    lines: list[str] = []
    remote = None
    try:
        with LA_LOCK.open("a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            busy = subprocess.run(["fuser", "-s", str(node)], capture_output=True, timeout=4)
            if busy.returncode != 1:
                raise ValueError("LA_BUSY_OR_UNCERTAIN")
            argv = [str(LA_APP), "--appimage-extract-and-run", "--loglevel", "3",
                    "--driver", "kingst-la2016:conn=" + conn,
                    "--config", "samplerate=1m", "--channels", "CH0,CH1,CH2,CH3",
                    "--samples", str(SAMPLES), "--output-file", str(wave)]
            env = dict(os.environ, SIGROK_FIRMWARE_PATH=str(Path.home() / ".local/share/sigrok-firmware"))
            capture = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, bufsize=1, env=env, start_new_session=True)
            ready = threading.Event()

            def drain() -> None:
                assert capture is not None and capture.stdout is not None
                for line in capture.stdout:
                    lines.append(line)
                    if "session: Starting." in line:
                        ready.set()

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            if ready.wait(8) and capture.poll() is None:
                record["la_started_unix_ns"] = time.time_ns()
                record["remote_trigger_unix_ns"] = time.time_ns()
                remote = ssh_run(login, source_sha)
                record["remote_exit"] = remote.returncode
                record["remote_stderr"] = remote.stderr[-1500:]
                payload = []
                for line in remote.stdout.splitlines():
                    try:
                        payload.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                record["ps_environment"] = next((item for item in payload if item.get("kind") == "ps_environment"), None)
                record["mmio"] = next((item for item in payload if "internal_swclk_pass" in item), None)
            else:
                record["remote_exit"] = None
                record["failure"] = "LA_DID_NOT_START"
            record["la_exit"] = capture.wait(timeout=40)
            reader.join(timeout=2)
    except Exception as exc:
        # TimeoutExpired embeds the SSH argv, including the private target address.
        record["failure"] = (type(exc).__name__ if isinstance(exc, subprocess.TimeoutExpired)
                             else type(exc).__name__ + ":" + str(exc))
    finally:
        if capture is not None:
            stop_capture(capture)
            record["la_exit"] = capture.returncode
        record["finished_unix_ns"] = time.time_ns()
        record["la_log_tail"] = "".join(lines)[-2500:]
        if wave.is_file():
            record["wave_sha256"] = sha256(wave)
            record["wave_bytes"] = wave.stat().st_size
            if record.get("la_exit") == 0:
                try:
                    record["wave_analysis"] = analyze_wave(wave)
                except Exception as exc:
                    record["analysis_error"] = type(exc).__name__ + ":" + str(exc)
        mmio = record.get("mmio")
        physical = record.get("wave_analysis")
        record["internal_pass"] = bool(isinstance(mmio, dict) and record.get("remote_exit") == 0
                                       and all(mmio.get(k) for k in ("internal_swclk_pass",
                                                    "swdio_output_state_pass", "swdio_pad_feedback_pass",
                                                    "final_hiz_low_pass")))
        record["la_pass"] = bool(isinstance(physical, dict) and record.get("la_exit") == 0
                                 and all(physical.get(k) for k in ("reference_ch2_high",
                                   "clock_ch0_edges", "dio_ch1_edges", "clock_ch3_edges")))
        record["result"] = "PASS" if record["internal_pass"] and record["la_pass"] else "FAIL"
        report.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"result": record["result"], "internal_pass": record["internal_pass"],
                          "la_pass": record["la_pass"], "report": str(report),
                          "wave": str(wave) if wave.is_file() else None}, sort_keys=True))
    return 0 if record["result"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("stage-a", help="Capture LA and drive CLOCK/DIO 0-1-0, three seconds each")
    run.add_argument("--bluepill-removed", action="store_true",
                     help="Confirm Blue Pill and all active P1/P2 drivers are disconnected")
    run.add_argument("--output-dir", type=Path,
                     help="Fresh evidence directory (default: .work/z2-toolbox/<UTC timestamp>)")
    args = parser.parse_args()
    if args.command == "stage-a":
        if not args.bluepill_removed:
            parser.error("Blue Pill and all active P1/P2 drivers must be removed")
        out = args.output_dir or ROOT / ".work/z2-toolbox" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        try:
            return stage_a(out)
        except Exception as exc:
            print("z2-toolbox: " + type(exc).__name__ + ":" + str(exc), file=sys.stderr)
            return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only, operator-public projections of Codex JSONL item events.

This module never executes commands, reads file contents or changes evidence.
Raw JSON/arguments are untrusted: only strictly allowlisted fields are emitted.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re

PREFIX = "@PLASMA_ACTIVITY_V1 "
ITEM_ID = re.compile(r"[A-Za-z0-9_-]{1,48}\Z")
SAFE_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,95}\Z")
SENSITIVE = re.compile(
    r"(?i)(?:secret|token|passwd|password|credential|private|"
    r"authorization|\.env|id_rsa|\.pem|\.key|auth)"
)
# Complete-command grammar. Never show shell pipelines, expansion,
# URLs, absolute paths, inline Python, arguments or embedded secrets.
COMMANDS = (
    (re.compile(r"python3 -m pytest scripts/tests/(?:test_[A-Za-z0-9_]+\.py)?\Z"),
     "TEST"),
    (re.compile(r"python3 scripts/tests/test_[A-Za-z0-9_]+\.py\Z"), "TEST"),
    (re.compile(r"git status(?: --short| --porcelain)?\Z"), "COMMAND"),
    (re.compile(r"git diff --check\Z"), "COMMAND"),
)
# Classifications expose only a fixed label; no shell arguments or paths.
# These describe Codex-reported commands, not verified execution receipts.
SEMANTIC_COMMANDS = (
    (re.compile(r"git (?:status|diff|log|show|rev-parse|ls-files)(?: [A-Za-z0-9_./=:+, '()-]{1,160})?\Z"),
     "COMMAND", "Inspect Git repository (arguments redacted)"),
    (re.compile(r"(?:rg|grep|sed|head|tail|cat|find) [A-Za-z0-9_./=:+, '()*?-]{1,160}\Z"),
     "READ", "Inspect source files (arguments redacted)"),
    (re.compile(r"python3 -m (?:pytest|unittest)(?: [A-Za-z0-9_./=:+, '()*-]{1,160})?\Z"),
     "TEST", "Run Python tests (arguments redacted)"),
    (re.compile(r"(?:/opt/Xilinx/Vivado/[0-9.]+/bin/)?vivado -mode batch(?: [A-Za-z0-9_./=:+, '()*-]{1,160})?\Z"),
     "BUILD", "Run Vivado batch build (arguments redacted)"),
    (re.compile(r"(?:make|ninja|cmake)(?: [A-Za-z0-9_./=:+, '()*-]{1,160})?\Z"),
     "BUILD", "Run build tool (arguments redacted)"),
    (re.compile(r"(?:sha256sum|shasum)(?: [A-Za-z0-9_./=:+, '()*-]{1,160})?\Z"),
     "CHECK", "Inspect artifact checksums (arguments redacted)"),
)
SEMANTIC_KIND_BY_LABEL = {label: kind for _, kind, label in SEMANTIC_COMMANDS}
# Native CLI activity is identified only by an exact executable prefix. The
# remaining command line is never copied into the monitor. This is an
# observation of a Codex item, not a tool permission or an operation receipt.
NATIVE_TOOLS = (
    (re.compile(r"(?:/opt/plasma/hil-tools/kingst-la2016-sigrok\.AppImage|"
                r"(?:/usr/bin/)?sigrok-cli)(?:\s|\Z)"), "CHECK",
     "Run Sigrok CLI (arguments redacted)"),
    (re.compile(r"(?:/usr/bin/)?openocd(?:\s|\Z)"), "COMMAND",
     "Run OpenOCD (arguments redacted)"),
    (re.compile(r"(?:/usr/bin/)?ssh(?:\s|\Z)"), "COMMAND",
     "Run SSH client (destination redacted)"),
    (re.compile(r"(?:/usr/bin/)?lsusb(?:\s|\Z)"), "CHECK",
     "Inspect USB devices (arguments redacted)"),
    (re.compile(r"(?:/usr/bin/)?udevadm(?:\s|\Z)"), "CHECK",
     "Inspect udev devices (arguments redacted)"),
    (re.compile(r"(?:/usr/bin/)?python3?(?:\s|\Z)"), "COMMAND",
     "Run Python command (arguments redacted)"),
    (re.compile(r"(?:/usr/bin/)?git(?:\s|\Z)"), "COMMAND",
     "Run Git operation (arguments redacted)"),
    (re.compile(r"(?:/usr/bin/)?(?:bash|sh)(?:\s|\Z)"), "COMMAND",
     "Run shell task (details restricted)"),
)
SIGROK_LABELS = {
    "scan": "Probe Sigrok devices (arguments redacted)",
    "show": "Inspect Sigrok device (arguments redacted)",
    "capture": "Acquire Sigrok samples (arguments redacted)",
}
NATIVE_KIND_BY_LABEL = {
    **{label: kind for _, kind, label in NATIVE_TOOLS},
    **{label: "CHECK" for label in SIGROK_LABELS.values()},
}
# Shell metacharacters mean that an executable prefix may be only one part of
# a larger operation. Never infer a simple native action from those strings.
UNSAFE_SHELL = re.compile(r"[\x00-\x1f\x7f;&|<>`$\\]")
REPO_TOP = frozenset({
    "scripts", "software", "pl", "firmware", "docs", "specs", "packaging",
    "data", "handover", "release",
})
STATES = frozenset({"RUNNING", "DONE", "FAIL", "UNKNOWN"})
KINDS = frozenset({"TEST", "COMMAND", "FILE", "READ", "BUILD", "CHECK"})
MAX_EVENT_BYTES = 640
MAX_ACTIVE_ITEMS = 64
MAX_SEQUENCE = 10000000


def safe_command(value: object) -> tuple[str, str]:
    # Native tool invocations may be longer than the legacy 256-byte exact
    # patterns. Their arguments are NEVER rendered, so accept a bounded
    # longer input solely to classify an exact executable prefix.
    if (type(value) is str and len(value) <= 2048 and value.isascii() and
            SENSITIVE.search(value) is None):
        if len(value) <= 125:
            for grammar, kind in COMMANDS:
                if grammar.fullmatch(value) is not None:
                    return kind, value
        # Classify relative, single-command forms only. An absolute argument
        # or a shell control operator falls back to the opaque safe marker.
        if (len(value) <= 256 and
                re.search(r"\s/[A-Za-z]", value) is None):
            for grammar, kind, label in SEMANTIC_COMMANDS:
                if grammar.fullmatch(value) is not None:
                    return kind, label
        if UNSAFE_SHELL.search(value) is None:
            for grammar, kind, label in NATIVE_TOOLS:
                if grammar.match(value) is None:
                    continue
                # Preserve the old conservative policy for generic repo,
                # shell and Python commands with absolute arguments. Named
                # native instrument/remote tools still expose ONLY fixed
                # labels, never paths, remote hosts or arguments.
                if (re.search(r"\s/[A-Za-z]", value) is not None and
                        label not in {
                            "Run Sigrok CLI (arguments redacted)",
                            "Run OpenOCD (arguments redacted)",
                            "Run SSH client (destination redacted)",
                        }):
                    continue
                if label.startswith("Run Sigrok"):
                    if re.search(r"(?:^|\s)--scan(?:\s|\Z)", value):
                        label = SIGROK_LABELS["scan"]
                    elif re.search(r"(?:^|\s)--show(?:\s|\Z)", value):
                        label = SIGROK_LABELS["show"]
                    elif re.search(r"(?:^|\s)(?:-o|--output-file|"
                                   r"--samples|--time|--channels)"
                                   r"(?:=|\s|\Z)", value):
                        label = SIGROK_LABELS["capture"]
                return kind, label
    return "COMMAND", "(command hidden)"


def safe_repo_path(value: object, workspace: Path) -> str | None:
    if type(value) is not str or not value or len(value) > 256:
        return None
    try:
        root = workspace.resolve(strict=True)
        candidate = Path(value)
        if candidate.is_absolute():
            # Absolute names are accepted ONLY if they refer to the pinned
            # candidate checkout; the original absolute name is never shown.
            relative = candidate.relative_to(root)
        else:
            relative = candidate
        posix = relative.as_posix()
        parts = relative.parts
        if (len(parts) < 2 or parts[0] not in REPO_TOP or
                any(p in (".", "..") or p.startswith(".") for p in parts)
                or SAFE_PATH.fullmatch(posix) is None
                or SENSITIVE.search(posix) is not None):
            return None
        check = root
        for part in parts:
            check = check / part
            if check.is_symlink():
                return None
        if not (root / relative).resolve(strict=False).is_relative_to(root):
            return None
        return posix
    except (OSError, RuntimeError, ValueError):
        return None


class Path3Activity:
    """Project a bounded sequence of supported Codex item events only.

    The source is OBSERVED_CODEX, not a trusted receipt; no item event
    proves test PASS or authenticates physical operations.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.next_seq = 0
        self.active: dict[str, str] = {}

    def project(self, event: dict) -> bytes:
        phase = event.get("type")
        # Item updates often repeat the unchanged command many times. Keep
        # just start and completion so each operation has one bounded pair.
        if phase not in ("item.started", "item.completed"):
            return b""
        item = event.get("item")
        if type(item) is not dict:
            return b""
        category = item.get("type")
        if category not in ("command_execution", "file_change"):
            return b""
        identity = item.get("id")
        if (type(identity) is not str or ITEM_ID.fullmatch(identity) is None or
                self.next_seq >= MAX_SEQUENCE):
            return b""
        if phase == "item.started":
            if identity in self.active or len(self.active) >= MAX_ACTIVE_ITEMS:
                return b""
            self.active[identity] = category
        elif self.active.get(identity) != category:
            # An orphan completion cannot turn into a verified result.
            return b""
        exit_code = None
        if category == "command_execution":
            kind, detail = safe_command(item.get("command"))
            if phase == "item.completed":
                code = item.get("exit_code")
                if type(code) is int and -255 <= code <= 255:
                    exit_code = code
                state = ("DONE" if exit_code == 0 else
                         "FAIL" if exit_code is not None else "UNKNOWN")
            else:
                state = "RUNNING"
        else:
            changes = item.get("changes")
            names = []
            if type(changes) is list and 0 < len(changes) <= 16:
                for change in changes:
                    if type(change) is not dict or change.get("kind") not in (
                            "add", "update", "delete"):
                        names = []
                        break
                    name = safe_repo_path(change.get("path"), self.workspace)
                    if name is None:
                        names = []
                        break
                    names.append(name)
            kind = "FILE"
            detail = names[0] if len(names) == 1 else (
                names[0] + " (+" + str(len(names)-1) + " files)"
                if names else "(file paths hidden)")
            state = "DONE" if phase == "item.completed" else "RUNNING"
        if phase == "item.completed":
            self.active.pop(identity, None)
        self.next_seq += 1
        record = {
            "schema": 1, "seq": self.next_seq, "id": identity,
            "kind": kind, "detail": detail, "state": state,
            "exit_code": exit_code, "source": "C",
            "time": dt.datetime.now().astimezone().strftime("%H:%M:%S"),
        }
        wire = (PREFIX + json.dumps(record, ensure_ascii=True,
                                   separators=(",", ":")) + "\n").encode("ascii")
        return wire if len(wire) <= MAX_EVENT_BYTES else b""


def parse_public_line(line: str) -> dict | None:
    if not line.startswith(PREFIX) or len(line) > MAX_EVENT_BYTES:
        return None
    try:
        obj = json.loads(line[len(PREFIX):])
    except (ValueError, TypeError):
        return None
    if type(obj) is not dict or set(obj) != {
            "schema", "seq", "id", "kind", "detail", "state",
            "exit_code", "source", "time"}:
        return None
    if (type(obj["schema"]) is not int or obj["schema"] != 1 or
            type(obj["seq"]) is not int or
            not 0 < obj["seq"] <= MAX_SEQUENCE or
            type(obj["id"]) is not str or ITEM_ID.fullmatch(obj["id"]) is None or
            type(obj["kind"]) is not str or obj["kind"] not in KINDS or
            type(obj["state"]) is not str or obj["state"] not in STATES or
            type(obj["source"]) is not str or obj["source"] != "C" or
            type(obj["time"]) is not str or
            re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"
                         r"(?::[0-5][0-9])?", obj["time"]) is None or
            type(obj["detail"]) is not str or len(obj["detail"]) > 150 or
            any(ord(c) < 32 or ord(c) > 126 for c in obj["detail"])):
        return None
    code = obj["exit_code"]
    if (code is not None and (
            type(code) is not int or not -255 <= code <= 255 or
            obj["kind"] == "FILE" or
            obj["state"] != ("DONE" if code == 0 else "FAIL"))):
        return None
    if (code is None and obj["state"] in ("FAIL", "DONE") and
            obj["kind"] != "FILE") or (
            obj["kind"] == "FILE" and obj["state"] in ("FAIL", "UNKNOWN")):
        return None
    # Reject forged display records, even if the log was accidentally
    # modified; do not make viewer parse a second arbitrary text channel.
    if obj["kind"] == "FILE":
        if obj["detail"] != "(file paths hidden)":
            match = re.fullmatch(
                r"([A-Za-z0-9._/-]{1,96})(?: \(\+[0-9]{1,2} files\))?",
                obj["detail"])
            if match is None:
                return None
            name = match.group(1)
            parts = name.split("/")
            if (len(parts) < 2 or parts[0] not in REPO_TOP or
                    any(p in ("", ".", "..") or p.startswith(".") for p in parts)
                    or SENSITIVE.search(name) is not None):
                return None
    elif obj["detail"] == "(command hidden)":
        if obj["kind"] != "COMMAND":
            return None
    elif obj["detail"] in {**SEMANTIC_KIND_BY_LABEL, **NATIVE_KIND_BY_LABEL}:
        if obj["kind"] != {
                **SEMANTIC_KIND_BY_LABEL,
                **NATIVE_KIND_BY_LABEL}[obj["detail"]]:
            return None
    elif obj["detail"] != "(command hidden)":
        # Legacy explicitly allowlisted commands must retain their original
        # category. Arbitrary sanitized-looking strings cannot forge kinds.
        if safe_command(obj["detail"]) != (obj["kind"], obj["detail"]):
            return None
    return obj

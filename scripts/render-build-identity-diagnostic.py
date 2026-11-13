#!/usr/bin/env python3
"""Log only non-secret build-provenance states at Render build checkpoints."""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHA40 = re.compile(r"[0-9a-fA-F]{40}\Z")


def git(*args):
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            timeout=30, check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""
    except OSError:
        return "error", ""
    return ("ok", result.stdout.strip()) if result.returncode == 0 else ("error", "")


def metadata(name):
    value = os.environ.get(name)
    if value is None:
        return "absent", None
    value = value.strip()
    return ("valid", value.lower()) if SHA40.fullmatch(value) else ("invalid", None)


def main():
    stage = sys.argv[1] if len(sys.argv) == 2 else None
    if stage not in {"before-python", "after-python", "before-npm", "after-npm", "before-vinext", "after-artifact"}:
        raise SystemExit("invalid diagnostic stage")
    head_state, head = git("rev-parse", "--verify", "HEAD")
    if head_state == "ok" and not SHA40.fullmatch(head):
        head_state = "invalid"
    status_state, status = git("status", "--porcelain", "--untracked-files=normal")
    entries = status.splitlines() if status_state == "ok" and status else []
    untracked = sum(entry.startswith("??") for entry in entries)
    tracked = len(entries) - untracked
    render_state, render_sha = metadata("RENDER_GIT_COMMIT")
    plasma_state, plasma_sha = metadata("PLASMA_BUILD_GIT_SHA")
    metadata_match = "mismatch" if render_sha and plasma_sha and render_sha != plasma_sha else "match" if render_sha and plasma_sha else "n/a"
    head_match = "mismatch" if head_state == "ok" and any(
        sha and sha != head.lower() for sha in (render_sha, plasma_sha)
    ) else "match" if head_state == "ok" and (render_sha or plasma_sha) else "n/a"
    print(
        f"[render-identity] stage={stage} head={head_state} "
        f"status={status_state} tracked_modified={tracked} untracked={untracked} "
        f"render_sha={render_state} plasma_sha={plasma_state} "
        f"metadata_match={metadata_match} head_match={head_match}",
        flush=True,
    )


if __name__ == "__main__":
    main()

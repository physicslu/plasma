#!/usr/bin/env python3
"""Host-only regression: obsolete Issue 981 pilots never define Path 3 policy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = (
    "docs/development/plasma-codex-pilot.md",
    "docs/development/plasma-codex-swpc-bootstrap-preflight.md",
    "docs/development/plasma-codex-worker-provisioning.md",
    "docs/development/plasma-codex-hil-tool-inventory.md",
)
index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
policy = (ROOT / "docs/development/plasma-path3-codex.md").read_text(encoding="utf-8")
for old in OLD:
    assert not (ROOT / old).exists(), f"Obsolete Path 3 guide restored: {old}"
    assert old.removeprefix("docs/") not in index, f"Obsolete Plan reindexed: {old}"
assert "docs/development/plasma-path3-codex.md" in agents
assert "Do not apply retired Issue #981 read-only Pilot" in agents
assert "guarded-hardware-no-sandbox" in policy
assert "Use native CLI, SSH, USB/TTY" in policy
assert "For Path 3-specific execution policy" in policy
assert "Do not reconstruct or apply their old restrictions" in policy

legacy = (
    ".github/workflows/plasma-codex-pilot.yml",
    ".github/workflows/plasma-codex-swpc-preflight.yml",
    ".github/workflows/plasma-codex-hil-tool-inventory.yml",
)
for path in legacy:
    data = (ROOT / path).read_text(encoding="utf-8")
    assert "\n  issue_comment:" not in data, f"Legacy Issue dispatch restored: {path}"
    for old in OLD:
        assert old not in data, f"Dead docs path in workflow: {path}"
print("PASS: current Path 3 authority; Issue 981 read-only docs retired; legacy dispatch closed")

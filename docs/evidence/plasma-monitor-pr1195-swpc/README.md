# PR #1195 SWPC host-only evidence correction

Overall acceptance: NOT_RUN; test suite: FAIL. Gate 2 Ready is not established.

Run 40686561861 executed the unchanged candidate d2fb3437ce46d8ec17ee974a0ed9bdd572275066 on SWPC-plasma-codex, non-root, under the assigned workspace-write sandbox. Trusted main from GITHUB_SHA: 84db10582d17a1a8e46d6c835912418414099e1b. No network verification was performed.

The actual command `python3 scripts/tests/test_plasma_engineering_monitor.py -v` ran 55 tests: 53 passed, two real private tmux tests errored, zero skipped. A captured subprocess rerun confirmed exit 1. Initial tests used normal temporary directories; the rerun set TMPDIR to the isolated candidate temporary directory. The latter has long absolute socket paths. An independent short relative private socket probe in a unique candidate temporary directory exited 1 with `Operation not permitted`, creating no socket. The absolute candidate socket probe exited 1 with `File name too long`. No existing tmux sessions or default socket were queried or modified.

No actual capture-pane output, terminal interactions L/J/K/C, terminal history, independent synthetic Path2 or Path3 terminal scenarios, or terminal functionality acceptance was obtained. These are NOT_RUN. Passed unit tests exercise separate stdout/stderr projection, incremental COMBINED output, command-start validation, redaction, bounded rendering and exit handling, but cannot substitute for those missing independent terminal observations. No code regression is established by the socket failures; source was unchanged.

CLI exit zero would establish only process completion. Previous run 40686097860 remains unusable for acceptance (receipt evidence_complete=false); this rerun makes no PASS claim from it. No hardware, deployed monitor, services, network, privileges, merge or deployment were used. No raw test output is retained because synthetic secret fixtures and private paths occur in it. JSON records sanitized test names and outcomes only.

Evidence hashes: ACCEPTANCE.json records SHA256 of this README and a canonical JSON hash of its scenarios (UTF-8, sorted keys, compact separators). Publication by the existing authorized publisher remains required; this offline task does not establish remote publication. Resume the missing terminal acceptance only with effective private tmux socket access in the approved sandbox and the same pinned source.

Publication blocker: `git add -- docs/evidence/plasma-monitor-pr1195-swpc/ACCEPTANCE.json docs/evidence/plasma-monitor-pr1195-swpc/README.md` exited 128: Git could not create index.lock because .git is read-only. Files are preserved but untracked, uncommitted and unpublished. The authorized publisher must add them; the tracked/publication criterion is NOT_RUN.

# PLASMA — SWPC Codex C11 Hello World Auto-Dispatch (Issue #981)

## Owner-approved dual-mode contract

Execution mode was explicitly selected as **SWPC Codex (Mode 2)** in
the original C11 task's Gate 1, implemented and merged through PR #1033.
This PR #1034 is a **separate owner Gate 1** to fix automatic handoff.
It does not change ChatGPT Mode 1 or switch actors.

The exact activation marker, recorded once in PR #1034's description:

    PLASMA-AUTO-DISPATCH: issue981-c11-hello-world/gate1-pr1033/executor-codex

**There is no additional Issue comment or manual dispatch command.**
The old Issue #981 command is no longer listened to by this Workflow.

## One-shot automatic handoff after Gate 2

1. Owner approves **Gate 2 of PR #1034**, explicitly understanding that
   merging this activation PR will start an actual SWPC Codex software
   write job after the checks succeed. The owner chooses squash merge.
2. GitHub pushes that squash commit to main, which triggers the existing
   Software-only Codex MVP Workflow. GitHub-hosted contract CI runs first.
3. A separate hosted, read-only authorization job obtains PR #1033,
   PR #1034, associated PRs for the current push commit, exact changed
   file list and GitHub squash-commit metadata. It **rejects** any push
   unless it has the exact owner, source actor, target PR, marker,
   head branch, squash-merge Commit SHA, only approved file changes,
   run attempt 1, active main ref and no force push.
4. Only after the hosted authorization job passes does the workflow
   schedule the real Codex job onto the dedicated
   SWPC-plasma-codex self-hosted Runner. The job rechecks the same
   GitHub run SHA and SWPC identity, then uses installed Codex CLI
   and existing ChatGPT account authentication. No API key is required.
5. Real Codex writes exactly one new file:
   examples/hello-world/main.c. Worker performs static admission and
   GCC -std=c11 -Wall -Wextra -Werror -pedantic -O0 compile; executing
   the approved tiny program must print exactly Hello, World! plus LF.
6. The separate GitHub-hosted Publisher receives a SHA256-bound patch,
   checks one allowed new file and source grammar without running model
   output, and opens a GitHub PR. It cannot merge that PR. A NEW owner
   Gate 2 is required for the resulting program.

## Safety, scope and known limitations

This activation is pinned to exact PR #1034 and its prior Gate 1
PR #1033. It is **not** a universal GitHub merge dispatcher:
unrelated PR merges, other main pushes, GitHub Action re-runs,
wrong actor, wrong job SHA, modified PR ownership, and non-squash
commits must fail closed. A normal rejected push may show an
authorization NO-GO check; that is not SWPC execution.

GitHub-hosted jobs handle GitHub trust and publishing. SWPC receives
no model credential except its **existing local** Codex login, and
no GitHub write token. Identity, denied groups, SSH agent, device-node
preflights and the workspace-write network option remain in force.
The tests performed in this implementation PR are **offline contracts**
and do not prove live Linux sandbox isolation, model authentication,
hardware isolation, or that the real Codex/Publisher pair will succeed.
If a preflight fails, the live run is NO-GO rather than a permission
to bypass it.

No SWPC installation, service restart, deployment, generic
Dispatcher, HIL, FPGA, Z2, USB Hub, LA2016 or DUT hardware action,
or auto-merge is authorized by this setup PR.

A GitHub Actions GITHUB_TOKEN-created PR may not trigger normal
pull_request CI workflows automatically; a later owner action or
approved publisher credential may be needed to validate that PR.
Do not claim the end-to-end pipeline passed before real evidence.

## Current operational state

- **This setup PR #1034 before Gate 2:** only hosted tests may run;
  real SWPC Codex must be skipped.
- **At Gate 2:** PR #1034 must be merged separately and only after
  fresh full CI, ruleset, review-thread and mergeability verification.
  This merge has a concrete **real Codex execution consequence**.
- **After Gate 2:** check actual hosted provenance admission, real SWPC
  Runner status, Codex authentication, GCC execution/stdout evidence,
  independent Publisher and resulting PR/CI.

The fixed old Issue #981 command /plasma-codex hello-c 981 has been
removed from this Workflow's triggers. No owner GitHub Issue comment
should be necessary for this authorized activation.

# PLASMA — Real Codex Software-only MVP (Issue #981)

## Goal and scope

Single PLASMA owner, one preapproved software-only task, real Codex code
generation, real GitHub PR, and a mandatory separate owner Gate 2.
This is a one-shot executable MVP rather than a generic Dispatcher.

Previous PR #1024 was FAKE Codex and Mock Publisher. This PR delivers
a real execution path but **does not claim it has been invoked**.
CI on the implementation PR tests only Git safety and event handling.

## Controlled runtime

Exact future Issue #981 command: **/plasma-codex software-mvp 981**.
This needs a separate new GitHub owner comment after the MVP workflow
is approved and merged to main; previous comments do not authorize it.

Four jobs, with one on SWPC:
- contract: GitHub-hosted, read-only Python and real local Git safety tests
- authorize: GitHub-hosted, validates trusted owner, Issue #981, exact body,
  actor choice (Codex), and original main SHA
- codex: existing dedicated **SWPC-plasma-codex** self-hosted Runner,
  Linux user **plasma-codex**, installed Codex CLI with existing ChatGPT
  account login (including Plus when available); uses workspace-write
  sandbox, explicitly disables spawned-tool network access, has a fixed
  single new documentation file target and an eight-minute model timeout.
  **No OPENAI_API_KEY secret or new GitHub-hosted Codex login is required.**
- publisher: a distinct GitHub-hosted job with GitHub write token, which
  validates the artifact's scope, SHA256, source SHA and trusted owner event,
  publishes a real GitHub PR; never runs Codex or merges PRs.

Only one new target path is permitted:
docs/development/plasma-codex-mvp-first-change.md

The Codex job **must** execute on SWPC, not the GitHub-hosted runner or
the existing `SWPC-plasma-ci` integration runner. It checks actual hostname,
worker identity, runner label/name, forbidden privileged groups, visible
hardware device access, and inherited SSH Agent; unexpected exposure is NO-GO.
No Z2, FPGA, USB, DUT, LA2016, deployment or general Dispatcher activation
is authorized. The Codex job has NO GitHub write credential; the publisher
job has no Codex session or model authentication. Both check out the event's
immutable SHA. Rerun attempts fail closed. No force push or cleanup.

**Security limitation:** This is an OS/group/device preflight and Codex tool
sandbox, not verified host-wide network isolation. The existing SWPC Codex
identity has historically been used by tightly scoped hardware workflows;
a fixed prompt alone is NOT a physical or credential security boundary.
Before any real software-write run, independently verify that the model's
spawned tools cannot reach laboratory networks, privileged SSH identities,
host credentials or device APIs. If that cannot be verified, keep the job
NO-GO rather than disabling checks.

## First-use acceptance and prerequisites

1. Gate 1: code, repository tests, draft-to-Ready PR only.
2. Gate 2: separate explicit merge authorization for this workflow PR.
3. Confirm the registered SWPC dedicated Runner is Online, the `plasma-codex`
   Linux account has a working authenticated Codex CLI, and the software-only
   sandbox and hardware/credential boundaries are verified. No API key needs
   to be provisioned to GitHub Actions. Check repository Actions permits
   creation of PRs.
4. Owner *explicitly selects Codex at Gate 1* for this fixed one-shot
   task, then posts an exact new comment on Issue #981. This is the
   separate owner-bound command that dispatches Codex to SWPC. A Gate 1
   approval selecting ChatGPT instead follows the direct GitHub tool
   development path and **must not** trigger the Codex workflow.
5. Independently verify Actions run, nonzero/timeout handling, artifact SHA,
   generated PR HEAD and all applicable CI. Gate 2 for that new PR is
   always a separate owner approval after full GitHub revalidation.

NOTE: GitHub Actions PRs created with GITHUB_TOKEN may place CI in an
owner-approval-required state. This is a known usability limitation.
It must be reported honestly, not described as fully unattended CI.
A separately approved narrow GitHub App token could address the gap.

## Status boundaries

This PR's passing CI is NOT proof that Codex has run in the hosted worker.
No live model, PR publisher, API key, GitHub ref claim, deployment, hardware
or generic Dispatcher has been executed as part of opening this PR.
If the SWPC login, isolation, permissions or repository settings are
missing, report truthful NO-GO. A passing CI contract does not prove a
live software-write sandbox has been qualified.

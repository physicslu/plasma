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

Four GitHub-hosted jobs:
- contract: read-only offline Python and real local Git safety tests
- authorize: enforce trusted owner, Issue #981, exact body, original main SHA
- codex: disposable hosted Ubuntu worker; read-only GitHub, separate
  OPENAI_API_KEY secret, Codex CLI 0.163.0 in workspace-write sandbox,
  a fixed single new documentation file, eight-minute model timeout
- publisher: separate hosted job with GitHub write token; validates artifact
  scope, SHA256, source SHA and owner event; publishes a real GitHub PR;
  never executes code from the model patch, never auto-merges

Only one new target path is permitted:
docs/development/plasma-codex-mvp-first-change.md

No SWPC/self-hosted/instrument runner, Z2, FPGA, USB, DUT or LA2016
activity, deployment or general Dispatcher activation is authorized.
The codex job has NO GitHub write credential, the publisher job has NO
Codex API key or model runtime. Both jobs checkout the event's immutable SHA.
Repeat workflow attempts fail closed. No force push or cleanup.

## First-use acceptance and prerequisites

1. Gate 1: code, repository tests, draft-to-Ready PR only.
2. Gate 2: separate explicit merge authorization for this workflow PR.
3. Confirm repository permits GitHub Actions to create PRs, and configure
   the repository Actions secret OPENAI_API_KEY. A ChatGPT subscription
   or existing SWPC login is NOT a verified GitHub-hosted API credential.
4. Owner posts exact new comment on Issue #981. Main-branch workflow
   will run real Codex, verify a genuine edit, then open a real GitHub PR.
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
If credentials or repository settings are missing, report truthful NO-GO.

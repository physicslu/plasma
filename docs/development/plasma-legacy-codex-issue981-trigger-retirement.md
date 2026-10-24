# PLASMA — Issue #981 Legacy Codex Runtime Trigger Retirement

**Gate 1 change; Gate 2 merge still required.** Baseline `main` `f9e13c6694514f19cb39df98366d930c577a7eda`. This is a reversible, host-only source change. No SWPC, Z2, USB, LA2016, FPGA, DUT, deployment or real Issue dispatch is authorized or executed by it.

## Decision

Remove only the `on.issue_comment` event registration from the nine historical `/plasma-codex ... 981` workflows:

- `plasma-codex-pilot.yml`
- `plasma-codex-software-mvp.yml`
- `plasma-codex-la2016.yml`
- `plasma-codex-la2016-direct.yml`
- `plasma-codex-la2016-diagnose.yml`
- `plasma-codex-z2-login.yml`
- `plasma-codex-z2-readiness.yml`
- `plasma-codex-swpc-preflight.yml`
- `plasma-codex-hil-tool-inventory.yml`

Retain each `pull_request` and `push` GitHub-hosted offline CI event. Existing `authorize` and self-hosted worker jobs remain in source for review/possible controlled recovery but are unreachable from registered events. The old commands are **not** silently remapped to the shared Dispatcher. After merge into `main`, new Issue #981 comments no longer start these nine workflows. Historical runbooks containing those commands are superseded by this decision.

## Retain and do not conflate

- Shared `plasma-engineering-runtime-dispatch.yml`, its Issue #981 admission, Path 2/3 Work Orders and protected Z2 Root Entry remain unchanged.
- Keep Z2 SSH/UART helper, `z2-login-smoke.json` single credential, pinned Host Key and tests, including HIL A2 dependency.
- Keep LA2016 supervisor/direct/diagnose, pinned instrument AppImage, device isolation, independent PWM OFF/watchdog, original waveform and negative tests.
- Keep `SWPC-plasma-ci` observer identity separate from `SWPC-plasma-codex`. Do not start either runner as part of this source change.
- Claim Canary, Issue #814 Control Bridge, other diagnostic/workflow_dispatch entries, private files and historical GitHub artifacts are out of scope.

## Contract and rollback

- Existing Software MVP hosted regression checks nine prohibited `on.issue_comment`, `on.workflow_dispatch`, `on.workflow_call` events, preserving `pull_request`/`push` CI.
- Six offline contract scripts now reject restored Issue events but preserve historical exact-owner event-denial tests. The original hardware safety tests remain in CI.
- If a retired workload is needed, propose a reviewed, owner-authorized Work Order on the existing shared Dispatcher or explicitly restore one bounded legacy event through a separate Gate 1; never silently auto-route or resume hardware retries.
- Hosted CI PASS does not establish real SWPC or LA/Z2 acceptance. Gate 2 remains a separate approval for the exact merge-ready PR.

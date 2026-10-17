# PLASMA Engineering Dispatch v1 — Gate 1A Offline Architecture

> **Status: Contract-only, NOT deployed; runtime dispatch disabled.**
>
> **Scope:** engineering/developer job orchestration via GitHub and Codex. This is
> **not** the Control Station → PPU → eight-site IC programming runtime scheduler.
> All existing `plasma-codex-*.yml` legacy workflows remain untouched. New
> engineering work will use this contract **only after** separate Gate 2 merge
> and subsequent new-route implementation/acceptance. Existing workflows migrate
> **individually at their next approved invocation**, not in a bulk rewrite.

## 1. Why this architecture exists

The [LA2016 Direct loopback](../development/plasma-codex-la2016-direct.md)
has already demonstrated one successful path: GitHub owner-approved Issue
comment → dedicated SWPC non-root Runner → Codex CLI → pinned KINGST tool →
actual PWM1/CH0 traces and hashes → GitHub evidence. This demonstrates
one path, not a multi-capability engineering dispatcher.

At review, the repository contains **11 distinct `plasma-codex-*.yml` workflows**
and 27 scripts prefixed `plasma-codex-` (including legacy wrappers and distinct
hardware contracts). Each legacy workflow retains its existing exact command,
GitHub authorization and independent hardware controls. **Do not change,
disable, rename or automatically reroute these triggers in Gate 1A.**

## 2. First-principle separation

```text
  immutable, versioned Work Order (checked-in reviewed commit)
                  |
       exact owner approval (Issue comment binds content SHA256)
                  |
  trusted GitHub event metadata + reviewed checkout SHA check
                  |
    authorization / capability / replay contract [Gate 1A OFFLINE]
                  |
            [NO RUNTIME EDGE YET]
                  :
  future isolated worker per capability → native engineering tool
                  |
   private diagnostic + sanitized receipt + evidence + PR
                  |
         independent human Gate 2 review / merge
```

Trust boundary: editable Issue body is not the authority. An owner comment
**only authorizes the exact canonical Work Order hash**, issue, revision,
capability, authorized kind and reviewed `main` SHA. The Work Order content
must be fetched from reviewed, immutable repository contents; no untrusted
Issue prose is evaluated as shell commands or allowed capabilities.
A future live GitHub adapter must supply verified `GITHUB_EVENT_PATH`,
`GITHUB_ACTOR`, `GITHUB_REPOSITORY`, `GITHUB_REF`, runtime run ID and
the **actual checked-out reviewed SHA**. Untrusted client-supplied `context`
JSON is suitable only for the offline reference tests, never as proof by itself.

## 3. Contract assets

- `specs/engineering-dispatch/work-order-v1.schema.json`:
  strict Draft 2020-12 JSON Schema, no additional top-level/scope keys;
  `schema_version`, `work_order_id`, revision, issue, repository,
  reviewed `main` SHA, authorization kind, objective, capability,
  executable **label** (never a shell string), scoped repository paths,
  forbidden resources, exact permission set, time budget, acceptance tests,
  evidence requirements.
- `specs/engineering-dispatch/capabilities-v1.json`: explicit immutable
  worker-class names and deny-lists, per-capability timeout and permission
  contract. **Every `runtime_enabled` is `false`.** Merely declaring a
  capability does not deploy an executable route or grant access.
- `scripts/plasma_engineering_dispatch_v1.py`: Python standard library
  validation, canonical SHA256 fingerprint, strict exact-comment matching,
  event and checkout-SHA checks, sanitized authorization plan and local
  atomic replay-ledger *reference implementation*. The CLI only returns
  JSON decisions and **never launches Codex, native tools, shell commands,
  GitHub API actions, HIL or CI jobs**.
- `scripts/tests/test_plasma_engineering_dispatch_v1.py`: offline hostile
  event, malformed schema, privilege/capability, stale approval, replay,
  concurrency and non-hardware workflow regressions.
- `.github/workflows/plasma-engineering-dispatch-contract.yml`: only
  hosted Ubuntu pull-request and main-push contract CI. **No
  `issue_comment`, `workflow_dispatch`, or self-hosted job.**

### Approval and replay semantics

Exact proposed comment format (not connected to any live Issue listener):

```text
/plasma-dispatch approve <work-order-id> rev=<revision> sha256=<canonical-sha256> kind=<gate1-implementation|hardware-one-shot>
```

The SHA256 is computed from JSON with sorted keys, compact separators and
ASCII encoding; order of object keys is irrelevant, but changed objectives,
capability, permissions or timeout changes the digest. Extra spaces,
suffix commands, newline, PR comments, forks, non-owner events, edited
comments, stale checked-out SHA and digest mismatch are **DENIED**.

A local file-based `claim_offline` uses exclusive 0600 creation inside a
pre-existing owner-only 0700 ledger, keyed by `issue + work_order_id +
revision`. Repeated comment IDs, duplicate Issue approvals and GitHub
re-run attempts are denied for the same Work Order revision. This is only
a **single-filesystem offline contract**: GitHub-hosted jobs have separate
filesystems, so they cannot use this local receipt as globally durable
de-duplication. **Before a future live dispatcher can be enabled**, require
a repository-scoped durable CAS/ledger or equivalent atomic storage, GitHub
concurrency for serialization, and crash/recovery receipts. If that ledger
is unavailable, refuse live execution (especially any hardware action).

### Gate segregation

`gate1-implementation` is only for non-hardware engineering tasks.
Capabilities that touch physical hardware require an independently reviewed
`hardware-one-shot` authorization kind with explicit approval and a separate
one-use claim. Gate 2 PR merge is a distinct independent owner action, never
derived from Work Order admission or generated agent output. Retain the
validated LA2016 watchdog/off evidence boundary and separate Z2 FPGA image
owner; hardware isolation must be enforced by OS/capabilities, **not only
by model prompts, job labels or deny-list text**.

Current declared capability classes:

| Class | Worker contract | Stage |
| --- | --- | --- |
| `software-readonly` | Hosted/offline, repo read | No runtime route |
| `software-pr` | Isolated software branch writer, no hardware | No runtime route |
| `la2016-loopback` | LA-only instrument identity and USB | No new route; legacy works independently |
| `z2-readonly` | Z2 read-only/SSH identity | No runtime route |
| `z2-privileged` | Independent audited privileged image owner | Disabled; requires later design and evidence |

## 4. Explicit staged migration

1. **Gate 1A now:** contract schema, validator, capability policy, exact
   approval digest, simulated de-duplication, negative tests and hosted-only
   CI. Build an independent PR. No merge, deployment or hardware operation.
2. **Gate 2 later:** inspect exact PR HEAD, latest `main`, CI and
   mergeability; merge only by explicit owner approval.
3. **New tasks after dedicated future authorization:** create a new
   production dispatcher adapter with globally durable replay prevention
   and one safe software-only worker acceptance. Do not activate new
   hardware routes by default.
4. **Legacy on-demand migration:** when a legacy task next requires work,
   migrate **that single workflow** to the new contract after separate
   Gate 1/2 review, parity/rollback and, if physical, one-shot approval.
   The current LA2016 Direct path remains the hardware regression baseline.
5. **Z2:** start with read-only inventory; MMIO, FPGA image reload,
   reset, DUT power and recovery remain independent physical permission gates.

## 5. Limitations and explicit NO-GO

This PR does not provide a production dispatcher, globally durable approval
database, deployed worker, GitHub owner action, model API connection, device
permission change, real LA2016 PWM measurement, Z2 HIL, eight-site production
programming or electrical OFF attestation. A standalone unit-test assertion
does not prove future sandbox device isolation.

No existing workflow is modified. No Work Order in this draft is actionable
by GitHub without a **new, separately approved runtime integration**.

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

## 6. Gate 1B: GitHub adapter + software-only acceptance contracts

> **Status (2026-10-17): Gate 1B proposed implementation in an independent
> PR; hosted/offline test only. New GitHub Issue dispatch is NOT active.**
> Gate 1A has been merged; the above earlier roadmap is historical
> sequencing, not a claim that this stage was deployed.

Owner migration decision: **all existing 11 `plasma-codex-*.yml` workflows
are unchanged.** After the new runtime architecture receives its own
separate approval, new work orders use the unified contract; older
workflows migrate **one at a time** only when next needed, with parity
verification and rollback. Never bulk-retire the LA2016 Direct path.

### 6.1 GitHub cross-run claim CAS

`scripts/plasma_engineering_dispatch_gate1b.py` builds a **GitHub
create-ref request** for the approved, immutable Work Order:

```text
POST /repos/physicslu/plasma/git/refs
{"ref":"refs/heads/plasma-engineering-claims/<issue>/<work-id>-r<rev>",
 "sha":"<reviewed-main-commit>"}
```

A successful HTTP **201** with the expected exact ref and SHA yields a
sanitized `CLAIMED_ONCE_GITHUB_REF_CREATE_CONFIRMED` receipt. An HTTP **422**
means an already-present or invalid ref and must fail closed. Any other
HTTP status, timeout, transport failure or malformed response also
fails closed; never retry an ambiguous claim write. This is an **atomic
GitHub ref create**, not the old local filesystem ledger, and the namespace
persists across runner filesystems and subsequent workflow executions.
It does not require a race-prone GET-before-POST query.

Security nuance: ordinary Git refs are **not inherently immutable against
owners with update/delete rights**; the method is create-only, but a
privileged actor or a misconfigured workflow can rewrite or delete the
ref. **Before activating runtime**, configure/verify GitHub rulesets that
protect this claim namespace from force updates/deletions, verify every
work order source is checked out by exact reviewed commit SHA, ensure
the Apps/Actions credential can create claims without granting write
authority to the Codex worker, and audit push-triggered workflows that
could run due to claim-branch creation. If any precondition cannot be
attested, fail closed and do **not** enable runtime. Claim records are
not automatically deleted; retention/capacity policy needs independent
approval. Crash after successfully claiming is a spent one-shot, not
permission to repeat automatically.

### 6.2 GitHub authorization and worker separation

The future GitHub adapter converts **trusted Actions environment**
(`GITHUB_EVENT_NAME`, `GITHUB_ACTOR`, `GITHUB_REPOSITORY`,
`GITHUB_REF`, `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, plus
independently checked-out `git rev-parse HEAD`) to the existing
Gate 1A authorization contract. Owner's exact comment SHA256,
revision and authorization kind must match an immutable reviewed
Work Order. A GitHub Issue body, edited comment or arbitrary user
JSON can never grant an executable shell command.

For `software-pr`, capability maps to the `software-isolated`
worker class only. **Do not use the SWPC `plasma-codex` account as
a general software worker:** its existing supplementary I/O group is
instrument-capable. A future live Software-only job must use a
fresh ephemeral GitHub-hosted runner, restricted repository write
boundary, no device access, a reviewed narrow sandbox, and separately
scoped credentials. The trusted claim step may need
`contents:write`; that token must **never be sent** to Codex or
injected into its workspace. The worker receives only its own
minimum access. A general `workspace-write` Codex flag by itself is
not an OS/device or network exfiltration boundary; evaluate the
runtime image and network policy separately.

`software_only_command` generates a fixed argument array, not shell
interpolation of Issue text. `offline_mock_codex_acceptance` runs
only a **deterministic FAKE executable** in a disposable test
directory and checks a sanitized content-hash receipt. This verifies
command contract and basic lifecycle, **not live Codex authentication,
network access, sandbox escape prevention, PR publishing, or device
isolation**. Actual Codex acceptance remains a separate post-Gate-2,
explicitly approved test.

### 6.3 New CI does not install a live Dispatcher

`.github/workflows/plasma-engineering-dispatch-gate1b-contract.yml`
runs only on pull-request / main-push path changes on
`ubuntu-24.04`, with `contents:read` and no credentials,
`issue_comment`, `workflow_dispatch` or self-hosted runners.
Offline tests simulate hostile event tampering, edited issue scope,
replayed work order across independent GitHub-runners, concurrent
claim races, interrupted HTTP, exact ref/SHA matching, protected
token transport, capability separation and FAKE Codex acceptance.

The adapter **contains no runtime trigger** and its CLI returns
`GATE1B_NOT_ACTIVE_NO_ISSUE_DISPATCH`. All capability policy
`runtime_enabled` fields stay `false`. Do not publish a broad
new production dispatcher or retire any legacy trigger in this PR.

**Gate 1B acceptance:** an independent PR + full hosted CI +
exact HEAD/mergeability check; **Gate 2 requires separate owner
approval**. Subsequent activation must separately qualify protected
GitHub claim refs and an actual isolated software-only Codex runner,
then obtain an independent explicitly approved one-shot smoke run;
a passed fake-model CI test is insufficient.

## 7. Gate 1C — security preflight and truthful NO-GO (offline only)

**Status: Gate 1C isolated-PR implementation, NOT runtime activation.**

The prior Gate 1B GitHub create-ref CAS is useful, but **create-once is not
immutable** if another principal can delete/rewrite the claim ref. We
independently checked repository state on 2026-10-17: only the active
`Protect Plasma main` ruleset (ID 20964250) exists and its branch selector
includes only `~DEFAULT_BRANCH`; no dedicated active claim namespace
ruleset exists. There are currently zero
`refs/heads/plasma-engineering-claims/**` refs. Both facts are a hard
**NO-GO** for live dispatcher activation, not a reason to relax gating.

The repository presently contains **322 YAML workflows** (baseline before
adding Gate 1C CI). `product-release.yml` is one concrete example of
`push.branches: ["**"]`; although it has `paths` filters, we will not
treat those as a proof of safety for a newly created ref. GitHub `create`
events also exist, and workflow chaining is possible. For this reason the
full checkout must be scanned and each potential exposure reviewed, rather
than assuming that all workflows only run on `main`.

### 7.1 Claim Ruleset Preflight

`scripts/plasma_engineering_dispatch_gate1c.py check-rulesets`
examines a read-only JSON snapshot of GitHub's **detailed** rulesets.
It requires an active branch ruleset with exact
`refs/heads/plasma-engineering-claims/**/*` selector, no excluded
patterns, no bypass actors, and protection rules `deletion`, `update`
and `non_fast_forward`. An active `main` rule, disabled or
evaluation-only rules, allowlisted bypass principals, or omitted
protection rules all fail closed. The positive fixture is **synthetic**
and may not be presented as the live repository configuration.

Important: GitHub's `update` restriction could prevent a normal claim
creator from working. A ruleset *configuration match* is not sufficient
to establish a viable write-once claim path: an independently approved
future canary must prove that the intended claimant **can create** a
ref but cannot subsequently update, force-push or delete it, including
after job cancellation. If GitHub policy cannot express this separation
without over-privileged bypass, use a different durable claim ledger.
Do not loosen the protection rules to make the canary pass.

This PR does **not** change any GitHub repository settings, configure
rulesets, create a real ref, or test a live GitHub API write.

### 7.2 Entire-workflow trigger audit

`audit-workflows --directory .github/workflows` statically enumerates
**every** `*.yml` and `*.yaml` file. It reports the exact count and
metadata-only per-file inventory. Any `create` event,
`push` event whose branch pattern can match
`plasma-engineering-claims/<issue>/<id>-r<revision>`, an unrestricted
push, `workflow_run` chaining, unreadable workflow, or unsupported
trigger syntax produces `NO_GO_WORKFLOW_TRIGGER_RISK`. The scanner
is **conservative**, does not execute workflow expressions, and does
not treat `paths` or job-level `if` conditions as hardware security
boundaries. It also surfaces indicators of self-hosted runners, secrets,
and write permissions for review.

New hosted-only Gate 1C CI requires that every checked-in YAML workflow
was scanned and emits a sanitized full inventory Artifact. A reported
`NO_GO` is an **expected honest finding**, not a green light for live
dispatch. Static parsing is not a proof of all GitHub YAML expression
semantics; unsupported cases are review-required. Before activation
also verify GitHub's actual event behavior and privilege scope for the
selected claim token. Normal `GITHUB_TOKEN` event recursion differs from
GitHub App/PAT event propagation; do not assume token interchangeability.

### 7.3 Credential isolation contract

`specs/engineering-dispatch/credential-boundaries-v1.json` describes
**four future job boundaries**, but does not provision credentials:

| Future job | Contents permission | Codex model | Scope |
| --- | --- | --- | --- |
| Owner authorizer | read | never | Exact immutable owner approval |
| Claim creator | write | never | Single atomic GitHub claim, no Codex access |
| Software-only worker | read | permitted later | Hosted disposable, no GitHub write token |
| PR publisher | write + pull-requests write | never | Broker publishes reviewed/sanitized change |

Each role must use ephemeral hosted execution, checkout
`persist-credentials:false`, no GitHub write credential in the
model-visible process, and a separate audited artifact handoff between
worker and publisher. **Do not** run the general software worker as
SWPC's existing `plasma-codex` hardware-capable account. Any role
combination, repository-wide write token in Codex's environment,
persisted checkout secret, unexpected permission or self-hosted worker
is an explicit negative test. The live token and OS sandbox boundaries
remain **unverified** in Gate 1C.

### 7.4 Migration and activation gates

The user's migration direction is authoritative: **do not touch the
existing 11 `plasma-codex-*.yml` workflows**. New tasks will eventually
use the unified architecture; each legacy task migrates independently
when next required and after parity/rollback validation.

This Gate 1C changes only new offline security-preflight code, tests,
fixtures, a new hosted-only CI workflow, and this documentation.
No Issue-comment listener, `workflow_dispatch`, new claim ref, active
Dispatcher, real Codex execution, SWPC login, LA2016, Z2, FPGA, hub
power or DUT action. Gate 2 merger is separately approved.

**Actual activation blockers:** claim namespace ruleset, validated
read/write token identity and protection behavior, classification of
every potentially exposed workflow, strict credential handoff, and
a separate one-shot *software-only* live Codex acceptance.

## 8. Gate 1D — Claim Namespace write-once qualification (new proposal)

> **Status: Gate 1D code-only PR; GitHub Ruleset NOT applied; Runtime remains NO-GO.**
> As of 2026-10-18 GitHub still reports only `Protect Plasma main`
> (Ruleset #20964250); no `plasma-engineering-claims/*` branches.
> The GitHub connector can read rulesets but does **not** expose a
> supported Create/Update Ruleset operation. Do not claim to have changed
> GitHub security controls.

### 8.1 Reviewed administrative configuration

`specs/engineering-dispatch/claim-protection-ruleset-v1.json` is an
**unapplied ruleset proposal**, not an active repository setting. The
intended rule for branch refs matching
`refs/heads/plasma-engineering-claims/**/*` is:

- `target=branch`, `enforcement=active`, no exclusions or bypass.
- **Restrict updates**, **Restrict deletions**, **Block force pushes**.
- **Do NOT enable Restrict creations** for this namespace: otherwise the
  intended actor cannot perform the initial write-once claim without a
  bypass, and that same bypass could defeat update/delete protection.
- **Do NOT** modify the existing `Protect Plasma main` ruleset. A
  dedicated new ruleset is required.

In GitHub repository Settings → Rules → Rulesets → New branch ruleset,
review `include` pattern, protection toggles, rule enforcement, and
app/role bypass list before any activation. Administrative setup must be
recorded with its GitHub Ruleset ID and an independently verified
read-back. Ruleset pattern semantics and effective permissions must
be qualified on GitHub itself, not inferred only from local glob
evaluation. Updating settings is outside the current connector's
supported write surface, so it requires a separately authorized
repository-admin action.

**Token identity risk:** `contents:write` is broader than a claim-only
permission; neither the Ruleset nor the Work Order JSON inherently
guarantees claim-only scope. The trusted Claimer must not share any
GitHub write token with Codex. Do not use a privileged App-token bypass
to make canaries pass. If the desired creation/update separation
cannot be enforced without an unacceptable bypass, choose a
different CAS store.

### 8.2 Deterministic negative canary (NOT executed in Gate 1D)

Only after a separate explicit one-shot authorization and verified
Ruleset installation, run **one** live canary under a narrowly scoped
trusted identity. Its expected observations, in this strict order:

1. **CREATE_ALLOWED**: atomically create exactly
   `refs/heads/plasma-engineering-claims/900003/ruleset-canary-r1`
   pointing to an approved existing commit.
2. **SECOND_CREATE_REJECTED**: attempt the exact same `POST /git/refs`
   again, require rejection; never retry an uncertain first write.
3. **UPDATE_REJECTED**: attempt a regular update with an expected old SHA;
   require rejection.
4. **FORCE_UPDATE_REJECTED**: attempt a force update; require rejection.
5. **DELETE_REJECTED**: attempt ref deletion; require rejection.
6. **READBACK_PRESERVED**: read back the original SHA after the tests,
   and audit all triggered GitHub Actions/workflow effects.

These are **security-negative probes**; abort and escalate if any
unexpected mutation succeeds. Never use the real `main` ref, a working
engineering Work Order, an actual production Claim, or an SWPC/
LA2016/Z2/DUT path for the canary. Do not try to remove a correctly
protected test ref automatically: it is intentionally permanent
until a separately authorized administrative retention procedure.

`scripts/plasma_engineering_dispatch_gate1d.py` checks proposal
fields, performs conservative read-only Ruleset read-back validation,
detects overlapping rulesets, and validates *synthetic canary receipt
shape*. **Receipt shape alone is not trusted proof of actual GitHub
behavior.** All outputs retain `runtime_enabled=false`. The
read-back implementation requires verified GitHub provenance and
must be paired with the real negative probes; synthetic JSON cannot
promote runtime readiness.

### 8.3 Workflow event risk and migration remains unchanged

GitHub's native `GITHUB_TOKEN` suppresses most recursively generated
events, but GitHub App/PAT tokens may generate further workflow runs;
do not interchange these token types without requalification. The
Gate 1C full-workflow audit still requires review of four possible
claim-ref event pathways; its findings are not suppressed by this
Ruleset proposal. The old eleven `plasma-codex-*.yml` workflows
remain untouched and only migrate one by one when next needed.

This Gate 1D PR has no claim creation, Ruleset API mutation, GitHub
`issue_comment` trigger, runtime activation, actual Codex, SWPC
deployment, hardware, or production batch scheduler changes.
**Separate Gate 2 is required for merging this code.** Real
Ruleset configuration and one-shot canary each require a distinct
operational authorization and successful environment readiness.

## 9. Gate 1 executor choice and SWPC hardware capability — simple dual-path contract

**Owner decision (2026-10-18): Gate 1 asks only who executes the approved
work: ChatGPT or Codex. Do not add another approval stage or require
Codex for simple ChatGPT/GitHub edits. Hardware access is NOT globally
forbidden merely because SWPC is the executor.**

### 9.1 One Gate 1 selection; two execution actors

At the end of a scoped task plan, offer two choices only:
- **Gate 1 — Approve, ChatGPT executes:** ChatGPT may modify scoped
  software directly through an available authorized GitHub connection,
  open a PR and read applicable CI. A ChatGPT proposal alone does not
  grant a GitHub owner identity or hardware access. Hardware tasks use
  an *existing separately authorized controlled SWPC channel*, never
  unrestricted cloud-to-device access.
- **Gate 1 — Approve, Codex executes:** An approved legacy dedicated
  workflow or, later, a qualified unified Dispatcher can route to Codex.
  The new unified Dispatcher remains OFF, so this choice is not evidence
  of actual dispatch or runtime qualification.

**Both routes** terminate in PR + CI + an *independent owner Gate 2*
merger. Automatic merging, silent retries and automatic actor
substitution are prohibited. GitHub CI is not equivalent to CD:
deployment, runtime installation, FPGA reload and device power/reset
operations require separate exact authorization.

The executor choice is **orthogonal** to the existing strict
Work Order capability (`software-pr`, `la2016-loopback`,
`z2-readonly`, `z2-privileged`, etc.). No Work Order schema
extension is needed to merely ask this Gate 1 question. Do not use
execution actor (`chatgpt` / `codex`) as a permission grant.

### 9.2 Hardware permission follows capability, not executor

For SWPC hardware tasks, the precise one-shot capability contract
defines which **existing controlled runner and device path** is
eligible:

| Capability | Allowed resource after independent one-shot owner approval | Not implied |
| --- | --- | --- |
| `la2016-loopback` | dedicated LA2016 USB, waveform capture and fixed off/watchdog boundary | Z2, FPGA reload, DUT power |
| `z2-readonly` | approved Z2 read-only SSH/inventory | MMIO writes, FPGA reload, reset |
| `z2-privileged` | separately supervised Z2 owner route within the approved HIL scope | arbitrary USB devices, DUT/hub power, root access |
| `software-pr` / `software-readonly` | repository/software only | any instrument or DUT |

Hardware tasks must carry `authorization_kind=hardware-one-shot`,
exact authorized resources, test/recovery/watchdog plan, and real
measurement or read-back evidence. Approval to run a Z2 SWD reset is
not an approval to reload FPGA or cycle target power. Existing
LA2016/Z2 one-shot legacy workflow checks stay intact; no new device
permission, self-hosted runner or privileged account is introduced.

### 9.3 Read-only contract artifact

`scripts/plasma_engineering_gate1_executor.py` is a **small offline
selection planner**. It validates the existing frozen Work Order and
capability policy, accepts only `chatgpt` or `codex`, and emits a
SHA256-bound route intent including Work Order hash, executor,
capability and reviewed main SHA. If a different actor is selected,
the route intent hash changes; no silent fallback or switch is
permitted. It does not modify the Work Order schema or bypass its
strict validation.

All planner responses explicitly report:
`github_owner_approval_verified=false`,
`hardware_permission_granted=false`,
`qualified_runtime_path=false` and `runtime_enabled=false`.
The plan is **not authenticated owner approval**, a real Codex
dispatch, GitHub claim, tool command, or hardware operation. Any
future runtime adapter must independently verify the selected
actor *as part of the exact approved owner action* before performing
work, and preserve the original GitHub provenance checks.

The new `plasma-engineering-gate1-executor-contract.yml` only runs
read-only hosted CI (PR/main-push); its regression tests cover both
actor paths, every current hardware capability, privilege escalation,
mandatory one-shot authorization, SHA change on actor change, and
no automatic actor fallback. This PR does **not** change any of the
eleven existing `plasma-codex-*.yml` workflows, install a new live
Dispatcher, or authorize physical lab equipment. **Gate 2 merge
requires a separate explicit owner instruction.**

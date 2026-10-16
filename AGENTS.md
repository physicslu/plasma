# Plasma Autonomous Development Contract

This file is the primary operating contract for AI coding agents working on the Plasma repository. Read it before making code, configuration, deployment, hardware, or documentation changes.

The operating model has **exactly two user approval gate types**: a **Gate 1 — Plan Approval** before implementation starts and a **Gate 2 — Merge Approval** when the work is merge-ready. After Gate 1, engineering execution continues autonomously within the approved scope, including branch/commit/PR work, CI repair, Draft -> Ready, and any deployment/runtime/hardware acceptance explicitly included in the approved plan. There is no separate deployment, runtime, hardware, or Ready-for-review approval gate. If necessary work materially exceeds the approved scope, return to Gate 1 with a revised plan rather than inventing a third gate.

## 1. Project purpose and canonical domain

Plasma is a configurable multi-Site IC programming system. The current hardware development platform is PYNQ-Z2 (Z2).

Canonical hierarchy:

```text
Plasma System
└── Facility
    └── PPU (Plasma Programming Unit)
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Definitions:

- **Facility**: deployment / administrative location.
- **PPU**: one physical Plasma programming appliance and autonomous local execution node.
- **Site**: one independently controlled Programming Site inside a PPU.
- **Socket**: mechanical/electrical IC fixture attached to a Site; not Site identity.
- **Plasma Gateway**: the northbound REST service owned by one PPU.
- **Plasma Gateway API**: the REST contract exposed by Plasma Gateway.
- **Plasma Gateway Endpoint**: the root URL used to reach one PPU's Plasma Gateway, for example `http://192.168.10.21:18080`.
- **Default Gateway**: the Linux Layer-3 next-hop router for a network interface. It is not the Plasma Gateway service. Human-facing network configuration must not shorten this term to bare `Gateway`.

Canonical Site identity is one-based:

```text
SITE 1 -> site_id = 1
SITE 2 -> site_id = 2
...
SITE N -> site_id = N
```

There is no canonical `SITE 0`.

Canonical wire protocol:

```text
magic:            PLASMA33
protocol_version: 3.3
identity:         site_id = 1..N
```

Protocol v3.3 is the only canonical runtime protocol. Retired Programmer/Channel identity and zero-based Site compatibility must not be reintroduced into canonical production code.

Canonical browser API:

```text
Web REST contract v3
Programming Asset source/input model
Normalized Image execution model
```

Repository layout:

```text
pl/                 Zynq PL RTL, constraints, simulation, verification, Vivado build assets
software/python/    PPU control plane, Protocol v3.3 TCP server, CLI, Plasma Gateway REST service, optional Manager, tests
software/web/       Plasma PPU Console
scripts/            integration/deployment and service-control scripts
docs/               architecture, development, and deployment documentation
```

## 1A. Prototype-first engineering policy (normative)

**PLASMA is currently in the prototype / proof-of-concept stage.** The
PYNQ-Z2 is a personally operated development board used to validate design
ideas, especially PS -> AXI-Lite -> FPGA SWD -> external-target/OpenOCD
feasibility. **A prototype is not a production appliance**: do not impose
future manufacturing, fleet security, factory traceability, full qualification,
or release governance on every daily lab iteration. Production requirements
are introduced progressively when the architecture and target hardware have
been validated.

Stage-specific objectives:

| Stage | Primary question | Default validation |
| --- | --- | --- |
| Prototype / PoC (current PYNQ-Z2) | Does the idea work on real hardware? | Smallest meaningful functional test / HIL smoke test; capture actual result and necessary recovery data |
| Engineering validation (custom board) | Does the complete design meet its engineering requirements? | Integrated electrical, timing, recovery, and reliability qualification |
| Production / release (PPU product) | Can it be manufactured, supported, and operated reliably? | Full production security, traceability, QA, maintainability, and acceptance controls |

For prototype work, **Build -> Test -> Learn -> Iterate** is the
default decision loop. Optimize for *time to a meaningful real-hardware
observation*, not documents, ceremonies, approval counts or evidence volume:

1. State the immediate hypothesis and first measurable pass/fail result.
   Execute the shortest path to that result; do not open a new
   enrollment, identity, documentation or audit milestone unless a concrete
   dependency makes it necessary.
2. Reuse already accepted enrollment, board identity, UART capabilities,
   historical HIL results, artifacts and recovery qualification.
   Previously proved capability is not a per-run qualification task.
   Still check current, changeable facts that affect safe execution.
3. Default PYNQ-Z2 internal-loopback HIL to the repository's
   `--profile development` policy. Keep the stricter
   `qualification` profile for deliberate qualification or release work.
   A previous Identity PASS does not prove that a newly loaded candidate
   image has the intended Build ID; a fast readback after load is reasonable,
   not a new qualification project.
4. Aim for **at most 180 seconds of pre-experiment checks** in the normal
   healthy lab state. This is a latency objective, **not** permission
   to assume PASS or bypass a real hazard. In one bounded pass automatically
   check applicable access, current PL ownership/mappings, clock, artifact
   integrity, and rollback image. On a genuine blocker, report all actionable
   blockers together rather than repeatedly running known-failing preflight.
5. Agents perform tool-accessible SSH/UART, host inspection, read-only
   verification, builds and routine execution themselves. Avoid asking the
   owner to relay commands or reconfirm electronically observable facts.
   A missing sudo/SSH permission is an access limitation, **not a new approval
   gate**; obtain an authorized execution path without leaking credentials,
   modifying sudoers, or silently escalating privilege.
6. After Gate 1, execute autonomously **within its approved scope**.
   Do not invent per-stage approvals, new documentation gates, or a third
   sign-off. Keep Gate 2 for merging, and request an expanded Gate 1 only
   when materially new work or risk is outside the authorized scope.
7. Prototype does **not** mean unsafe or unverifiable: preserve electrical
   voltage/DUT safeguards, known firmware recovery, conflicting PL-driver
   and MMIO ownership checks, applicable high-risk AXI-fault constraints,
   and truthful PASS/FAIL/NOT RUN evidence. Stop on real hazards.
   Do not confuse a SHA-256 file-integrity check with proof of hardware
   electrical safety.
8. Keep engineering records **proportionate to the experiment**. A short
   reproducible command, tested image/commit, observed result, and recovery
   outcome are usually sufficient for a development smoke test. Do not
   retroactively alter immutable historical evidence. Formal reports,
   extensive approval evidence, and manufacturing controls belong to
   qualification/production work unless a current technical dependency
   specifically demands them.

This section governs agent priorities and operating style; it does not
override repository source-of-truth rules, an active safety prohibition,
the existing two Gate 1/Gate 2 workflow, or explicit task-specific hardware
restrictions. When a lower-level procedure is unnecessarily stricter for a
prototype, propose and implement a scoped Development Mode change through
normal engineering review rather than fabricate evidence or silently bypass
executable checks.

## 1B. Canonical Codex task/SSH execution contract (normative)

**A Codex instruction is an execution assignment, not an invitation to
re-plan the same approved work.** For every task already covered by Gate 1,
the agent must carry out *all* authorized steps through actual acceptance or
a truthful, actionable blocker, without transferring routine SSH/sudo,
building, staging, test execution, restore, CI repair or status checking to
the owner. Explicit Gate 2 approval still controls merging.

The standard input packet for hardware tasks is
`docs/development/codex-z2-hil-development-command.md`. Its fixed sections
are: objective, already-approved scope, target/repository, credentials,
autonomous sequence, stop/recovery policy and PASS/FAIL/NOT RUN evidence.
For non-hardware work use the same pattern, with the task's actual acceptance
criteria; do not invent hardware stages.

**Z2 development SSH/sudo authentication:**

- The standard PYNQ-Z2 development-image SSH account is `xilinx`.
  A factory-image account name is not an authorization token. Resolve the
  actual target hostname/IP from current, owner-authorized lab config;
  never guess a network target or select another device solely by hostname.
- The SSH password and (unless explicitly different) sudo password come
  from the owner's approved **local** credential source, not from Git.
  Canonical per-user file on the **integration host**:
  `~/.config/plasma/z2-dev-credentials.json` containing
  `ssh_host`, `ssh_username`, `ssh_password`, `sudo_password`.
  The file/directory must be owner-only (`0600`/`0700`), outside the
  repository, never committed, copied to a PR/CI artifact, logged, printed,
  or transmitted to unrelated endpoints. A password reused for SSH and
  sudo is acceptable for this owner-authorized lab prototype.
- The owner has authorized the agent to use the supplied development-board
  credentials for bounded PYNQ-Z2 SSH/sudo HIL within the approved Gate 1
  scope. **Do not introduce a redundant manual sudo approval.** Prefer
  existing SSH agent/key or owner-approved credential store when usable;
  otherwise read the local secret in memory and feed sudo through stdin
  (e.g., `sudo -S`), never via shell arguments or a committed script.
  Redact secrets from errors and logs. Never edit sudoers to avoid a prompt.
- If the approved credential store is absent but the owner supplied the
  credential in the agent's active authorized session, initialize/use the
  private store without asking again. If the credential genuinely is
  unavailable to the execution environment, request it **once**, as a
  concrete access blocker, rather than looping through failed SSH/sudo
  preflights. Do not assume a chat secret magically appears on the host.
- Agent permission/sandbox boundaries still apply. A text prompt or
  stored credential cannot create SSH access or override a real sandbox
  denial. Never state that a physical action ran unless it was observed.

**Default end-to-end Z2 prototype-HIL sequence, when hardware execution is
within the approved task:** safely synchronize code, identify actual board
and known-good candidate/recovery artifacts, perform one bounded
Development Mode preflight, obtain the authorized root channel, perform
supervised candidate load, check its new-build identity, execute PSPL-02
Control/Status and SWD-00 internal loopback, **always attempt original FPGA
recovery even on test failure**, verify restored board state, and publish
the observed results with evidence paths. If current tooling stops at
preflight or live-MMIO primitives, the agent must implement/stage a minimal
bounded orchestration path in the approved scope rather than misrepresent
those tools as a one-command hardware runner. Never claim a promised
automation is already implemented.

For this internal-loopback development milestone, do **not** run the
intentional AXI-fault `ERROR`/`RESET` stages or external SWD/DUT operations.
Stop on genuine ownership, artifact, electrical, recovery or access
hazards. Distinguish *candidate loaded*, *functional PASS* and *original
image recovered*; all must be actually observed.

## 2. Programming data model

Plasma separates source data, execution instructions, and target-memory data.

```text
Programming Asset             source/input data used by a workflow
├── Image
├── Key
├── Option
├── Serial Number
└── Calibration

Programming Recipe            instructions telling the PPU what to do
                              separate control-plane concept; not an Asset

Image Asset
    |
    | parser / normalizer
    v
Normalized Image              data actually programmed to or verified
                              against target IC programmable memory
```

Canonical Asset types:

```text
image
key
option
serial_number
calibration
```

Declared Asset formats include:

```text
binary
intel_hex
srec
elf
csv
text
json
pem
```

Only `image + binary` normalization is implemented today. Unsupported type/format combinations must fail closed until a real parser/consumer is implemented and validated.

`serial_number` is a per-device identity Asset and is distinct from a security key. It may eventually come from MES, database, API, allocation service, operator input or a file. Do not give Serial Number the PPU-wide sharing semantics of an Image merely because both are Assets.

Programming Asset source identity and normalized execution identity are different:

```text
Asset SHA -> cache identity
Normalized Image SHA -> PPU Program/Verify shared-resource identity
```

## 3. Source-of-truth priority

When sources disagree, use this order:

1. Executable code and checked-in configuration.
2. `scripts/plasmactl` for integration-host operational behavior.
3. `software/python/pyproject.toml` and `software/web/package.json`.
4. Tests.
5. Current architecture/development documentation.
6. Historical discussion.

Do not silently propagate stale behavior. Update documentation with intentional contract changes.

## 4. Execution zones

### 4.1 Cloud / isolated software engineering

The isolated software-engineering environment may edit source, run non-hardware tests, and deliver changes on an `agent/*` branch through a pull request.

Repository entry points:

```bash
bash scripts/codex-cloud-setup.sh
bash scripts/codex-cloud-test.sh
bash scripts/codex-cloud-maintenance.sh
```

Cloud/CI validation does not prove integration-host deployment, Vivado implementation, Z2 runtime, FPGA I/O, socket/electrical behavior, or real IC programming.

### 4.2 Integration / deployment host

The integration host owns deterministic cross-stack validation, shared runtime deployment, and Vivado integration.

Before modifying its workspace:

```bash
cd "$PLASMA_REPO"
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

Never overwrite unrelated user changes.

### 4.3 Z2 target / hardware validation

Z2 owns embedded runtime, PS/PL integration, FPGA loading, target-interface behavior, electrical behavior, and hardware validation.

A passing Cloud, CI, or Mock test must never be reported as a passing Z2 or real-target test.

## 5. Current software architecture

PPU-local path:

```text
Browser / Plasma PPU Console
        |
        | HTTP REST polling / Web REST v3
        v
Plasma Gateway
        |
        | Plasma Protocol v3.3 / PLASMA33
        v
Plasma Server :9900
        |
        v
SiteManager / SiteWorker
        |
        v
Interface / Handler
        |
        v
MockInterface today; Z2/FPGA/real-target validation is separate
```

Managed Control Station path:

```text
Browser
    |
    v
Control Station Console/BFF
    |
    v
Plasma Manager (registry / fleet observation / bounded managed PPU relay)
    |
    +--> PPU A Plasma Gateway -> local execution
    +--> PPU B Plasma Gateway -> local execution
    +--> ...
```

Implementation facts:

- Plasma Gateway uses Python standard-library `ThreadingHTTPServer`.
- It is **not FastAPI**.
- It does **not use WebSocket**.
- Web Console uses REST polling.
- `plasma_manager` is optional and not required for local PPU execution.
- Manager deployment is opt-in (`PLASMA_MANAGER_ENABLED=0` by default for the integration profile).
- Manager fleet observation is read-only, but Manager also owns explicit bounded control relays. The managed allowlist includes health/status/settings surfaces plus the current Job, Batch, Programming Asset, Engineering session/target, Site Desired/runtime-activation and network-commissioning routes required by the Control Station product.
- Managed routing is **not** a generic reverse proxy. Exact methods and paths are allowlisted in `software/python/plasma_manager/server.py`; Browser traffic reaches those routes through the same-origin BFF.
- Job/Batch execution remains PPU/Gateway-owned. Manager relays commands and observations to the selected PPU; it is not a central Job scheduler and does not replace the PPU execution engine.
- Site Desired reads/writes remain PPU-owned. Manager relays the allowlisted Site settings routes and the explicit `If-Match`/idempotency/security headers required by that contract.
- Manager still does not provide automatic PPU discovery, a general Fleet write API, or an independent central authentication/scheduling policy layer.
- Mock programming success does not prove hardware programming.

Do not introduce FastAPI/WebSocket merely because they were discussed as future options.

## 6. Python environment and domain rules

Python project:

```text
software/python/
```

`pyproject.toml` is authoritative. Baseline is Python >= 3.11.

Preferred test command:

```bash
cd software/python
.venv/bin/python -m pytest -q
```

Canonical Python/domain vocabulary includes:

```text
PPUConfig
SiteConfig
SiteManager
SiteWorker
SiteState
ppu_id
facility_id
site_id
ProgrammingAsset
ProgrammingAssetType
ProgrammingAssetFormat
NormalizedImage
JobRequest.image
image_size
image_sha256
```

Retired Programmer/Channel domain vocabulary and old programming-data vocabulary must not appear in canonical production code. Do not create compatibility aliases unless an explicit new architecture decision reintroduces a real compatibility requirement.

## 7. Web environment

Web project:

```text
software/web/
```

Use `package.json` as source of truth for stack/versions. The project uses React + TypeScript and currently includes Next.js/Vinext and Vite tooling.

Normal checks:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

The Web Console must discover PPU/Site topology from canonical status rather than hard-code an eight-Site product assumption. Job requests send one-based `site_id` only.

Engineering Programming uses Web REST v3 Programming Asset routes. Browser source-input terminology must not be confused with the Normalized Image carried by Protocol v3.3.

Do not assume production Z2 needs Node.js, npm, or the development server merely because the integration host uses them for development/build/demo work.

## 8. Runtime services and ports

Service management is defined by `scripts/plasmactl`. Port numbers are profile-specific defaults; use `docs/deployment/port-profile-matrix.md` as the canonical cross-profile map rather than assuming one Manager port applies to every deployment.

| systemd service | Default port | Canonical role |
|---|---:|---|
| `plasma-server.service` | 9900 | Plasma PPU Programming Server / Protocol v3.3 TCP Server |
| `plasma-web.service` | 18080 | Full Plasma Gateway |
| `plasma-vite.service` | 5173 | Plasma PPU Console development/demo runtime |
| `plasma-manager.service` | 18180 | Generic/integration/package Manager default; registry, fleet observation, and bounded managed PPU relay |

The Linux `local-control-station` profile intentionally uses Console/BFF `127.0.0.1:18190` and Manager `127.0.0.1:18280`. The SWPC x86 `swpc-z2like` engineering surrogate owns only its full local Gateway on `127.0.0.1:18080`; its former host `18081` diagnostics/status ingress was retired by Issue #549 and must remain unused. Public `z2like-demo` uses SWPC host `18082` as its Cloudflare-Access-protected managed ingress to the private QEMU backend. Inside QEMU and on a real Z2, `:18081` remains the independent Bootstrap/recovery service. These are profile contracts, not accidental drift.

Packaged PPU deployments must bind `plasma-server.service` and `plasma-web.service` to the same explicit canonical PPU configuration path. Site Desired persistence requires directory-level create/rename permission for atomic replacement; grant that write boundary only to the Plasma Gateway service and only for the managed Plasma configuration root. `plasma-server.service` remains read-only for canonical configuration. A successful Save Desired changes persistent desired state only; runtime activation is a separate explicit operation.

Useful commands:

```bash
plasmactl status
plasmactl ports
plasmactl test
plasmactl restart
plasmactl logs
plasmactl deploy
```

`plasmactl test` is the preferred full integration-host validation for cross-stack changes.

Normal deployment flow:

```text
GitHub main
   -> fast-forward update
   -> re-exec latest plasmactl
   -> full relevant validation
   -> regenerate/reconcile systemd units
   -> restart configured services
   -> health check
```

Do not bypass failed tests and restart new code as if validation succeeded.

## 9. Site execution invariants

Unless a real shared resource requires synchronization:

- Sites execute independently.
- A Site must not wait for an unrelated Site pipeline.
- Per-Site cancellation must not cancel unrelated Sites.
- Batch cancellation is authoritative for batch classification when it races terminal Job success; the underlying final Job result remains truthful.
- `program` means write only.
- A complete programming flow is composed explicitly, e.g. `erase -> program -> verify`.
- Batch operation selection may include any subset of Erase / Program / Verify / Read.

For Program/Verify, a PPU-wide Normalized Image lease may synchronize Sites because one physical PPU must not execute different target Images concurrently when they share programming resources.

## 10. Service and process safety

Before stopping a process, identify it using `plasmactl ports`, `ss`, and `ps -fp PID` as appropriate.

Never use broad destructive process commands such as:

```text
pkill python
pkill node
killall python
killall node
```

Do not stop unrelated host services, networking, SSH, storage, containers, or applications.

Do not expose internal service ports to an untrusted network as a shortcut for connectivity problems.

## 11. Autonomous task execution contract

### 11.1 Exact two-gate workflow

There are exactly two user approval gate types:

```text
Request
  -> read-only inspection as needed
  -> Gate 1: Plan Approval
  -> autonomous implementation / validation / PR / CI repair / Ready
  -> Gate 2: Merge Approval
  -> merge to main
  -> approved post-merge deployment/runtime/hardware acceptance, when in plan
  -> completion report
```

**Gate 1 — Plan Approval before implementation starts**

Before creating or changing code, configuration, tests, documentation, branches, commits, pull requests, deployment state, or hardware state for a new task:

- perform only the minimum read-only inspection needed to understand the request and current repository state;
- give the user a concise plan describing scope, main files/layers likely to change, validation approach, and any deployment/runtime/hardware, destructive-Git, architecture, or security risk that is part of the task;
- wait for explicit user approval such as `開始`, `可以`, `approve`, or equivalent before implementation begins.

The user's approval authorizes autonomous execution of the stated plan. If the plan explicitly includes post-merge deployment, service restart, runtime acceptance, Z2/FPGA work, or real-target validation, those steps do not require another approval when their turn arrives.

**Gate 2 — Merge Approval**

After Gate 1 approval, continue autonomously through implementation, tests, commits, PR creation/update, CI observation/repair, and Ready-for-review. When the PR satisfies the merge-ready definition, stop and request Merge Approval.

After Merge Approval, merge to `main`, verify the resulting repository state, and continue any post-merge deployment/runtime/hardware acceptance already included in the Gate 1 plan. Do not stop for a third approval gate.

If continuing would materially exceed the approved scope, stop and propose a revised plan. Approval of that revision is another Gate 1 decision, not a new gate type.

### 11.1A Clickable owner approval choices (normative UX; no new gate)

For **every user approval request** under the two-gate workflow, prefer a compact
set of **clickable buttons or selection controls**, when the conversation
surface supports them. The owner should normally be able to approve by
**one click** rather than typing `批准`, `approve` or a long instruction.

- Show **at most four choices in total** for one decision; fewer are
  preferable when adequate. Do not use a long form or stack unrelated
  decisions. Label each choice as a clear **action**, in the user's language
  (normally Traditional Chinese for this project).
- Display **only the currently applicable approval gate**. At Gate 1,
  summarize the proposed plan and scope *before* offering approval. At Gate 2,
  first report the exact PR, target branch, current head/CI/readiness and
  any deployment or hardware consequences covered by the approved plan.
  **Never display an actionable Gate 2 approval choice before merge-ready.**
- Recommended Gate 1 choices: **「批准 Gate 1：執行此計畫」**,
  **「要求修改計畫」**, **「暫緩」**, **「不批准」**.
  Recommended Gate 2 choices: **「批准 Gate 2：合併 PR #N」**,
  **「要求修改」**, **「暫緩」**, **「關閉 PR（不合併）」**.
  Tailor or omit choices as appropriate; these are examples, not extra
  approval gate types or a mandatory fixed menu.
- Each approval control must convey an **explicit, scoped owner approval**
  identifying **Gate 1 + the plan**, or **Gate 2 + the specific PR/target**
  when deliberately selected (for example, by submitting a clear approval
  message as the user's next turn). A rendered button, default selection,
  hover, unrelated reply, or an agent's inference is **not approval**.
  Do not use a generic unlabeled `Approve` control whose target is unclear.
- **Non-approval choices never authorize work or merge**. A request to
  revise, defer, decline or close a PR is not Gate 1 or Gate 2 approval.
  Follow the selected instruction within the existing workflow and
  authorization boundaries; closing a PR must not be treated as merging it.
- If the client or agent execution environment **cannot render clickable
  choices**, provide a concise, unambiguous set of **at most four short
  selectable/text alternatives**, without pretending buttons exist or adding
  a new consent step. Explicit unambiguous approvals given by ordinary user
  text remain valid; never require the owner to click again.
- **Presentation changes no authorization semantics**: Gate 1 is still
  required before implementation, Gate 2 is still required before merge,
  out-of-scope changes still return to a revised Gate 1, and routine
  already-approved execution must not ask for redundant confirmations.
  No click may silently bypass readiness, repository safety, or physical
  hardware safeguards.

### 11.2 Routine autonomous work after Gate 1

Requests such as:

```text
Implement <feature>.
Fix <bug>.
Continue PR #N until merge-ready.
Resolve the CI failure.
```

combined with Gate 1 approval authorize routine engineering work necessary to reach the stated goal within the approved scope and repository/safety boundaries.

Routine autonomous work includes:

- inspect repository/history/config/tests/logs/PRs/CI;
- fetch/read Git state;
- fast-forward a clean local `main` when only behind `origin/main`;
- create/switch to focused branches;
- edit files within scope;
- add/update tests and documentation;
- run relevant validation/build/lint/artifact checks;
- inspect diffs/generated output;
- create focused commits and push feature branches;
- create/update Draft PRs;
- inspect and repair deterministic CI failures caused by the branch;
- rerun a failed CI check once when evidence supports transient flakiness;
- attempt to mark a PR Ready automatically when it is actually merge-ready;
- if Ready is blocked by a connector/tooling defect, record the defect and continue to Gate 2 when the PR otherwise satisfies the merge-ready definition;
- perform deployment/runtime acceptance explicitly included in the approved plan;
- perform hardware validation explicitly included in the approved plan;
- after Gate 2, merge and continue approved post-merge validation without creating another gate.

Do not turn routine engineering procedure into user-operated command relaying when the agent can perform the work directly.

If a connector, permission, SSH, or remote-shell limitation forces the user to perform a mechanical action, identify it as a **tooling/access exception**, not an approval gate. Prefer an available semantically equivalent supported operation over asking the user to perform redundant mechanical work.

## 12. Scope coverage and escalation — no third gate

The Two-Gate Model remains in force for deployment, runtime, hardware, destructive Git, architecture, and security work.

The following actions must be **explicitly covered by Gate 1** before execution:

1. **Deployment/runtime changes**
   - `plasmactl deploy`;
   - restart shared Plasma services to activate new code;
   - change active systemd definitions, public routing, firewall/network exposure, or shared runtime configuration.

2. **Hardware-affecting operations**
   - program a real IC;
   - change DUT power/voltage;
   - load a new FPGA bitstream onto connected hardware;
   - change FPGA I/O behavior on a connected system;
   - perform any action with credible electrical/hardware risk.

3. **Destructive/history-rewriting Git operations**
   - `git reset --hard`;
   - `git clean -fd`;
   - force checkout/restore that discards user work;
   - rebase a published/shared branch;
   - force-push;
   - delete remote branches/tags that may contain user work.

4. **Material architecture/security decisions**
   - incompatible protocol/API changes without an already-defined migration contract;
   - credential/access/security policy changes with nontrivial tradeoffs;
   - architecture choices with materially different cost, compatibility, safety, or maintainability consequences;
   - substantial scope expansion beyond the original request.

If one of these actions is already described in the approved Gate 1 plan, proceed autonomously when appropriate.

If it becomes necessary unexpectedly and was not covered by Gate 1, stop at a safe checkpoint, explain the added scope/risk, and request a **revised Gate 1 Plan Approval**. Do not create a deployment gate, hardware gate, Ready gate, or any other third gate.

Merge/integration to `main` always remains Gate 2. Direct feature commits to `main` are not a substitute for the PR + Merge Approval flow.

## 13. Merge-ready definition

A PR is merge-ready only when applicable conditions are true:

- implementation complete;
- branch scope clean;
- focused tests pass;
- full relevant validation passes;
- diff/syntax checks pass;
- committed diff reviewed for correctness/security/scope;
- branch pushed;
- PR accurately describes behavior, validation and limitations;
- required CI checks pass;
- no blocking review findings remain;
- GitHub reports mergeable;
- no validation claim exceeds observed evidence.

At that point attempt Ready automatically, then stop and request Gate 2 Merge Approval.

A failure of the GitHub connector to perform Draft -> Ready is a tooling exception, not a user approval gate and not an engineering-readiness failure. If the PR otherwise satisfies the merge-ready definition, proceed to Gate 2 without requiring the user to perform a manual Ready click. After explicit Gate 2 approval, use the verified PR head SHA and attempt the supported merge operation. Ask the user for a mechanical Ready action only if GitHub repository rules or the merge API itself proves that Draft state blocks the approved merge.

## 14. Git publication policy

Treat `main` as integration/deployment branch, not agent scratch space.

Before code-changing work:

```bash
cd "$PLASMA_REPO"
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

If clean local `main` is only behind `origin/main`, synchronize fast-forward only. Do not silently merge/rebase divergent history.

New work normally uses:

```text
agent/<short-feature-name>
```

Never stage or commit unrelated user work. Never force-push for graph aesthetics.

After GitHub merge, continue any deployment/runtime/hardware acceptance that was explicitly included in the approved Gate 1 plan. Do not ask for a separate deployment approval. If deployment was not part of the approved plan, return to Gate 1 with a revised plan before doing it.

## 15. Validation policy

Run the smallest relevant checks during development, then full relevant validation before merge-ready.

Python:

```bash
cd software/python
.venv/bin/python -m pytest -q
```

Web:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

Cross-stack/deployment/config/API/release-affecting integration-host changes:

```bash
plasmactl test
```

Testing layers are distinct:

```text
Unit / Source
    -> SSR / rendered HTML
    -> Playwright browser E2E
    -> deterministic Visual Regression
    -> deployment/runtime validation
    -> Z2/hardware validation when applicable
```

A passing lower layer does not prove the next layer.

## 16. FPGA / PL rules

`pl/` contains FPGA/PL work for Z2. RTL, XDC, register maps, Vivado scripts, bitstreams, and hardware-visible interfaces are contracts.

New production RTL uses SystemVerilog and follows `pl/AGENTS.md`, `docs/development/fpga-development-guide.md`, and `docs/development/fpga-verification-guide.md`.

Canonical repeated programming-resource terminology is **Site**, including `pl/rtl/site/`. Do not create production `channel` modules/directories from retired software vocabulary; use channel only when it genuinely denotes a lower-level protocol/bus concept and document that distinction.

When PL-visible behavior changes:

- check Python/PYNQ register access;
- check register-map documentation;
- check clock/reset/CDC and XDC/timing constraints;
- run appropriate simulation/lint/SVA/cocotb validation;
- do not claim synthesis/implementation/timing/bitstream success unless actually run;
- do not claim Z2 hardware success from software tests.

## 17. Z2 production direction

Z2 is the intended embedded PPU controller/runtime, not a clone of the integration workstation.

Expected runtime responsibilities, subject to validation:

```text
Embedded Linux
Python Plasma runtime
PYNQ / FPGA runtime
Plasma Server / API layer
FPGA bitstream + HWH
configuration / target definitions
production Web assets or selected Web runtime
system services
logs / diagnostics
```

Development-only components such as Vivado, pytest, npm build tooling, source-control credentials, and developer SSH keys should not automatically be included in a production image.

Before standardizing a Z2 Python environment, verify compatibility with PYNQ/XRT first.

## 18. Current known boundaries / technical debt

Agents must not silently turn these facts into wrong assumptions:

1. Python supports >=3.11; CI and integration host may use different allowed minor versions.
2. Integration deployment uses Plasma Gateway port 18080 while `plasma_web.gateway` retains a code-level local default of 8080.
3. Plasma Gateway is standard-library HTTP + REST polling, not FastAPI/WebSocket.
4. Web stack includes React/TypeScript plus Next.js/Vinext and Vite tooling; inspect `package.json` before stack assumptions.
5. Web REST v3 and Protocol v3.3 are canonical-only development contracts; there is no legacy compatibility requirement.
6. Only binary Image Asset normalization is implemented; other declared Asset formats/types are extension points, not validated functionality.
7. Programming Recipe/Package is an architectural direction, not yet an implemented execution contract.
8. Plasma Manager currently implements explicit registry/fleet aggregation plus bounded managed PPU command routing for the current Control Station contract, including allowlisted Job/Batch/Programming Asset and Site/network operations. It is not a generic proxy or central scheduler; automatic discovery, general Fleet write orchestration, and an independent central auth/scheduling policy remain outside the current contract.
9. Mock/software validation does not prove Z2/FPGA/OpenOCD/real-target behavior.
10. Site Desired persistence and Runtime activation are separate contracts. Current P3-capable deployments support explicit bounded runtime activation through the activation helper/server-control sockets; saving Desired state alone never implies that runtime activation occurred.

## 19. Communication and completion report

The expected communication pattern is:

```text
Gate 1: concise plan -> wait for approval
        |
        v
Autonomous work: implementation -> validation -> Draft PR -> CI repair -> Ready
        |
        v
Gate 2: merge-ready report -> wait for Merge Approval
        |
        v
Merge -> approved post-merge deployment/runtime/hardware acceptance -> completion
```

Progress updates between Gate 1 and Gate 2 are informational only. They must not ask for routine approval or create extra gates.

Interrupt before Gate 2 only when:

- necessary work materially exceeds the approved Gate 1 scope and requires a revised plan;
- a material product/architecture ambiguity cannot be resolved from the approved plan;
- a safety/security issue changes the risk boundary;
- missing access genuinely blocks progress;
- continuing risks unrelated user work.

A revised plan returns to Gate 1. It does not create a third gate type.

If the user explicitly asks for progress, report it without changing the approval-gate model.

At Gate 2 / completion / blocker, report at minimum:

```text
Changed:
- files/behavior changed

Validated:
- exact meaningful checks and results

Not validated:
- runtime/hardware/environment checks not actually performed

Repository state:
- branch / important HEAD
- PR / CI state
- whether merge, deploy, restart, history rewrite, or hardware action occurred

Next gate/action:
- Gate 2 Merge Approval if merge-ready;
- revised Gate 1 only if scope changed materially;
- otherwise the next autonomous execution step.
```

Never report a test, deployment, FPGA build, or hardware programming operation as successful unless actually executed and observed.

## 20. Workspace and information boundary

Treat `$PLASMA_REPO` as the normal workspace boundary for AI-assisted development.

- Read/create/modify/delete files only inside the repository unless the task genuinely requires an already-authorized external resource.
- Keep ordinary development commands inside the repository or subdirectories.
- Do not inspect unrelated repositories, personal files, credentials, SSH configuration, container data, or system configuration as ordinary Plasma work.
- Do not commit personal usernames, private hostnames, workstation inventory, passwords, keys, tokens, or other operator-specific infrastructure metadata into public guidance. An intentionally documented vendor-default lab image account name (such as the PYNQ-Z2 development account) is not a personal username or credential secret.
- If a task cannot be completed without leaving the workspace boundary, stop and explain the required external resource.

This policy is not an OS sandbox. Editor/agent permissions should still enforce project-scoped access where possible.

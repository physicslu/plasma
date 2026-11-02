# PLASMA — Embedded / PPU Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) for Z2 Linux, PS runtime, OpenOCD and device operations.

## Scope
- Z2 Linux, PS runtime, native OpenOCD, WordPort/Remote Bitbang, PS drivers, MMIO, PPU services, hardware ownership and recovery.
- Live OpenOCD and bit-level SWD execution belong on Z2 PS, not SWPC. PL performs the DUT electrical interface.
- Before any real hardware action verify current boot/source, paired image identity, permissions, owner/lease, electrical conditions and Golden recovery.
- Keep credentials private; no privilege escalation or sudoers changes. Use actual Linux permissions and protected Root guards.
- Changes to PL registers or ABI also load [FPGA](plasma-fpga.md). Changes to Gateway/Manager-facing API also load [Manager](plasma-manager.md).
- Record authentic PASS/FAIL/NOT_RUN; host-only tests cannot establish real programming qualification.

## Z2 production direction

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

## Hardware validation evidence boundary

Mock/software validation does not prove Z2/FPGA/OpenOCD/real-target behavior.

## Z2 SSH/sudo and hardware recovery boundary (normative)

The owner-approved Gate 1 scope is an execution assignment, not a new planning request. The executor must perform authorized work or report a real blocker; Gate 2 remains solely for merging. Path 3 Codex-specific execution and sandbox details live in [Path 3 contract](plasma-path3-codex.md). Path 2 fixed-CLI capabilities live in [Path 2 contract](plasma-path2-cli.md).

**Z2 development SSH/sudo authentication:**

- The standard PYNQ-Z2 development-image SSH account is `xilinx`.
  A factory-image account name is not an authorization token. Resolve the
  actual target hostname/IP from current, owner-authorized lab config;
  never guess a network target or select another device solely by hostname.
- The SSH password and (unless explicitly different) sudo password come
  from the owner's approved **local** credential source, not from Git.
  Canonical per-user file on the **integration host**:
  `~/.config/plasma/z2-login-smoke.json` containing
  `ssh_host`, `ssh_username`, `ssh_password`, and optional
  `sudo_password` only if Z2 sudo differs from the SSH password.
  Both Path 2 and Path 3 consume this exact same worker-local credential source.
  `z2-login-known_hosts` is the separately pinned **public host key**, not
  an alternate credential. Legacy `z2-dev-credentials.json` is no longer an
  execution fallback; migrate and retire only after verified continuity.
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
supervised candidate load, and check its new-build identity, then run the
functional tests within the approved scope. After a genuine successful FPGA Download receipt and confirmed
same-boot ownership and safe PL/electrical state, **Keep Loaded is the normal
default**; later Identity/ABI or DPIDR PASS, FAIL or NOT_RUN is a separate test
outcome and is not a Restore trigger. On functional failure stop further DUT
operations, close/reap active tools and retain the Image for debugging only
while electrical state and hardware ownership remain safe and known. Retain
qualified Golden recovery before load; invoke protected Restore only on an
explicit selection or documented fault-recovery need. UNKNOWN, failed load,
unsafe/in-flight state or unreaped owner must fail closed without blind retry.
Publish actual load, test and optional recovery receipts; never claim a
promised automation is already implemented. If current tooling stops at
preflight or live-MMIO primitives, implement/stage only the minimal bounded
orchestration path already in the approved scope; do not misrepresent those
tools as a one-command hardware runner.

Stop on genuine ownership, artifact, electrical, recovery or access
hazards. Distinguish *candidate loaded*, *functional PASS* and, when Restore
was invoked, *Golden recovered*; report each only when actually observed.

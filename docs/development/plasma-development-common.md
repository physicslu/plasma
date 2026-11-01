# PLASMA — Shared Development Contract

> **Normative detailed clauses.** The repository root [AGENTS.md](../../AGENTS.md) is the concise mandatory instruction entrypoint for Codex and other agents. This file preserves the previous complete engineering contract as the detailed, on-demand source of clauses. Apply its relevant sections before modifying affected domains, deploying, handling privileged resources, or working with hardware. In case of conflict, check the latest executable code, current root AGENTS.md and owner-approved task scope. Historical source: `main` b3caa1d289f375125f781f2a563fe1eb8b02204e.


The operating model has **exactly two user approval gate types**: a **Gate 1 — Plan Approval** before implementation starts and a **Gate 2 — Merge Approval** when the work is merge-ready. After Gate 1, engineering execution continues autonomously within the approved scope, including branch/commit/PR work, CI repair, Draft -> Ready, and any deployment/runtime/hardware acceptance explicitly included in the approved plan. There is no separate deployment, runtime, hardware, or Ready-for-review approval gate. If necessary work materially exceeds the approved scope, return to Gate 1 with a revised plan rather than inventing a third gate.

**Current default operating mode: DEVELOPMENT MODE (single-owner lab).**
PLASMA is being developed by one owner; unless the owner expressly declares
qualification, release or production work, prioritize the shortest working
Build -> Run -> Observe -> Fix loop. Do not silently apply future fleet,
factory, multi-tenant or enterprise security requirements to a prototype
smoke test. See Section 1A.1 and the route-specific Path 2/3 contracts. This is an engineering priority,
not a declaration that disabled executable controls are already enabled.

**Execution routing:** ChatGPT Direct is the default; use [Path 2](plasma-path2-cli.md) for SWPC CLI or [Path 3](plasma-path3-codex.md) for SWPC Codex only when the approved task requires that executor. Path selection belongs to Gate 1.

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

Z2 owns embedded runtime, PS/PL integration, FPGA loading, target-interface behavior, electrical behavior, and hardware validation. In the deployed PLASMA architecture, SWPC owns **Web / Controller / BFF**; Z2 PS owns the **OpenOCD process and PS-local WordPort/Remote Bitbang bridge**; Z2 PL owns the hardware SWD/SPI interface. SWPC may build and test OpenOCD offline, but must not host live OpenOCD or forward bit-level SWD transactions to Z2. See the normative [OpenOCD PS architecture](../architecture/ic-support-openocd-plan-executor.md); existing architecture-contract CI must reject placement drift.

A passing Cloud, CI, or Mock test must never be reported as a passing Z2 or real-target test.

## Domain contract ownership and loading

This common contract is normative for **all** engineering work. Its remaining clauses govern cross-domain behavior, source-of-truth, shared safety, Gate approvals, Git, evidence, execution zones, and workspace security. Do not move shared Z2 root/hardware recovery guards into a domain-only file: these safeguards apply to all paths and callers.

Domain-specific normative detail has one owner:

| Domain | Owner document | Load when |
| --- | --- | --- |
| FPGA / PL | [plasma-fpga.md](plasma-fpga.md) | RTL, XDC, timing, bitstream, PL ABI, MMIO |
| Embedded / PPU | [plasma-embedded.md](plasma-embedded.md) | Z2 Linux, OpenOCD, PS drivers, recovery |
| Manager / backend | [plasma-manager.md](plasma-manager.md) | Manager, Gateway, Controller, backend REST, Site routing |
| Web / frontend | [plasma-web.md](plasma-web.md) | Web UI, frontend and REST client |

Read [AGENTS.md](../../AGENTS.md) first. Select Path 2 or Path 3 execution instructions **independently** of the domains touched. Cross-layer changes load all affected domains and validate changed producer/consumer interfaces; unrelated domain contracts and full-system tests are not automatic requirements. Domain documents supplement shared safety and Gate rules; they cannot override them.


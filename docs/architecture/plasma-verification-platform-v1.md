# PLASMA Verification Platform v1 — Proposed Execution and Evidence Contract

> **Status: PROPOSED / Gate 1 documentation only; not yet adopted as an executable CI contract.**
> This document defines a target platform policy for FPGA/PS–PL verification.
> It **does not** authorize GitHub workflow changes, SWPC execution, Vivado
> XSim, FPGA Manager, real MMIO, Z2/PPU hardware, DUT power/reset, deployment
> or merge. Fixed Hardware ABI v1 **M1 remains NO-GO**.
> Follow the current [FPGA Verification Guide](../development/fpga-verification-guide.md)
> and existing scoped tests until an independent implementation Gate is approved.

## 1. Objective and authority

Provide one evidence-driven FPGA verification contract across PLASMA
**ChatGPT Direct**, **Codex Worker**, and **Hybrid** development routes.
Who writes a patch must not determine whether that patch passes validation.

Three independent dimensions must be recorded:

1. **Work executor:** ChatGPT Direct / Codex Worker / Hybrid.
2. **Validation executor:** GitHub-hosted runner / trusted SWPC runner / authorized HIL operator.
3. **Qualified claim:** precisely which tool, source/RTL, DUT model, hardware
   backend, and checks actually ran and passed.

A GitHub-hosted Cocotb PASS is **not** a Linux ARMv7 MMIO, PS7 AXI
Interconnect, FPGA timing, vendor-IP integration, physical electrical or
real-IC programming qualification. Generic green workflows or release
artifact builds cannot substitute for an identified FPGA verification lane.

The target FPGA platform is an **orchestration and evidence standard**,
not a separate execution framework competing with the existing unified
engineering dispatcher. CI implementation should extend reusable jobs/
validation entry points rather than create one YAML per protocol, Site,
manufacturer, or research task.

## 2. Environment baseline — measured versus proposed

| Component | v1 candidate / present evidence | Execution platform | Qualification boundary |
| --- | --- | --- | --- |
| OS (fast FPGA CI) | GitHub-hosted Ubuntu 24.04 | GitHub-hosted x86-64 | Runner image is mutable unless digest/manifest is pinned. |
| Python | 3.12 **minor line** in existing FPGA workflows; exact patch must be reported | GitHub-hosted | Do **not** claim Python 3.12.13 from an unpinned setup-python request. |
| pytest | `8.4.2` in current fixed-ABI host lanes | GitHub-hosted | v1 candidate for common host test runner; does not mean all legacy CI is pinned. |
| Cocotb | `1.9.2` in fixed-ABI and unified AXI host lanes | GitHub-hosted | Python testbench framework, **not** HDL simulator. |
| cocotb-test | `0.2.6` in fixed-ABI and unified AXI host lanes | GitHub-hosted | pytest-to-simulator integration. |
| Icarus Verilog | `iverilog` installed via Ubuntu apt; **exact version not pinned** | GitHub-hosted | Main behavioral RTL regression simulator. |
| Verilator | Already used for lint/RTL checks in selected existing workflows; **version unqualified for this v1** | GitHub-hosted | Lint/elaboration first; only claim functional simulation when a real Verilator test actually ran. |
| Vivado / XSim | SWPC workflow refers to `/storage/tools/xilinx/2026.1/Vivado/settings64.sh` | Trusted SWPC `plasma-ci` | Preflight is **not** proof that XSim runs or that license checkout succeeds. |
| Vivado synthesis / implementation | Existing trusted SWPC build workflows | Trusted SWPC | Resource and timing reports must be linked to actual target/device/build. |
| ARMv7 QEMU | Separate PS software acceptance routes exist | Hosted or separately scoped lab | QEMU alone does **not** execute PL RTL or prove a PS7 AXI bridge. |
| Physical Zynq / DUT | Hardware-gated HIL only | Approved SWPC + Z2 / future PPU | Outside this document-only PR; separate operator authorization required. |

Current pinned-reference workflows:

- `/.github/workflows/ppu-fixed-swd-site1-rtl-host.yml`
- `/.github/workflows/ppu-fixed-unified-axi-host.yml`
- `/.github/workflows/swpc-vivado-runner-environment.yml`

A later implementation Gate must measure `iverilog -V`,
`verilator --version`, `python --version`, `pip freeze`,
`xvlog -version`/`xelab -version`/`xsim -version` where available,
plus the runner OS image identity. **Do not infer** an exact installed
version from a package request. Lock reproducibility using a tested
container digest or equivalent immutable toolchain inputs after
qualification; do not change all legacy workflows in this PR.

## 3. Verification levels and execution ownership

The SIM levels below are **FPGA verification stages**, completely
unrelated to ADR-0002 IC Catalog L0–L3.

| Stage | Actual work needed for PASS | Default execution | Explicit non-claim |
| --- | --- | --- | --- |
| **SIM-0 — Static/contract** | RTL lint/elaboration, repository checks, machine ABI/RTL source-contract checks | GitHub-hosted | No cycle-accurate behavioral proof from static checks alone |
| **SIM-1 — RTL functional** | Icarus + Cocotb runs genuine RTL and checks AXI/SWD/control/negative cases | GitHub-hosted | No real ARM/Linux/PS7 transactions |
| **SIM-2 — PS control ↔ RTL** | **Same production PS control implementation** through injected simulated 32-bit MMIO adapter, Cocotb AXI BFM, actual RTL, independent virtual target | GitHub-hosted | Simulated ordering hook is not an ARM DMB/DSB or hardware access-width proof |
| **SIM-3 — Xilinx/vendor integration** | Real XSim batch compilation, elaboration and testbench results for identified Vivado/IP versions | Trusted SWPC, explicitly approved | Vendor simulation is not implementation timing closure |
| **SIM-4 — FPGA implementation** | Actual target-device synthesis, place/route, timing closure and resource report | Trusted SWPC, explicitly approved | No physical pin voltage, DUT behavior, Linux MMIO or socket safety |

**HIL** is separate from SIM-0..4 and has its own safe-operation approval.
A V4-style hardware result is **not** silently substituted for a missing
SIM-3 result, nor vice versa. A change may be merged with
`SIM-3=NOT_RUN`/`SIM-4=NOT_RUN` only if those stages were not a
declared mandatory acceptance requirement for that exact change and the
missing coverage is explicitly disclosed and tracked.

**SWPC trust boundary:** the existing Vivado environment workflow uses
manual `workflow_dispatch` restricted to reviewed `main` code and the
self-hosted `plasma-integration` runner. This document does **not**
authorize changing those restrictions, adding `pull_request_target`,
or running untrusted PR code on SWPC. Before any future pre-merge
mandatory vendor gate, design a separate safe execution strategy and
obtain approval; otherwise mark vendor tests as post-merge/qualification
and do not misrepresent them as a pre-merge gate.

## 4. Existing assets and integration coverage

Relevant already-established branches of evidence:

- **SWD-06:** synchronous production `SWDTransactionDriver` executes over
  Cocotb simulated MMIO into **legacy SWD-03** AXI/SWD RTL. This does **not**
  qualify Fixed Hardware ABI v1, whose register map differs.
- **Fixed ABI v1 Site 1:** a transport-neutral production
  `FixedABISWDController` (merged PR #1022) has been tested through
  Cocotb AXI BFM, the actual **standalone Site-1 RTL**, and a virtual SWD
  target. This does **not** qualify a physical `/dev/uio*` backend.
- **Unified 64-KiB PPU AXI:** merged PR #1019 provides the top-level
  `fixed_ppu_unified_axi_site1` router for Identity, Global Status
  and actual Site-1 RTL. In addition to the retained simulation-only
  `FixedSWDSiteSimDriver` cases, the SIM-2 increment in PR #1025
  executes the **same production `FixedABISWDController`** via the
  existing injected Cocotb AXI port and unified 64-KiB router.
  Directed cases cover virtual DPIDR, fatal timeout / global sticky FAULT
  and partial WSTRB refusal. Qualification applies only to the exact
  hosted CI commit whose run completed successfully. This does **not**
  prove physical PS7/ARM MMIO, XSim, FPGA timing or eight Site instances.
- **Site count:** the fixed ABI describes eight logical windows. Unified
  Site-1 RTL must report only the physically instantiated Site 1;
  `SITE_PRESENT=0x01` does not establish eight RTL engines.

SIM-2 Site-1 integration topology (implemented as a Host-only PR #1025 test increment; merge and other verification stages remain separately gated):
```text
FixedABISWDController (production PS control; explicit injected port)
        |
     Cocotb AXI-Lite BFM (32-bit words + independent AW/W/B, AR/R)
        |
   fixed_ppu_unified_axi_site1 (single 64-KiB entry)
        |                            |
 Global Identity / Status    actual Fixed ABI SWD Site 1
                                     |
                             SWD engine + virtual DUT
```
For **eight** independently implemented sites, add interleaved starts,
per-Site cursors/buffers, slow or failed Site isolation, retries, abort,
status and verification independence, shared data-port arbitration,
backpressure and measurable fairness/throughput constraints. Do not
claim the eight-Site suite PASS before eight actual engine instances exist.

## 5. Minimum acceptance matrix by changed artifact

| Change category | Minimum normally applicable evidence | Deferred / conditional evidence |
| --- | --- | --- |
| Documentation only | Documentation/index integrity, repo contracts | No forced Vivado or physical HIL |
| RTL logic / register decoder | SIM-0 + SIM-1; AXI negative tests | SIM-2 if PS software contract affected; SIM-3/4 on implementation/admission milestone |
| PS Driver / control semantics | Python contract tests + SIM-2 against the affected actual RTL and ABI | ARM MMIO access width/barrier and physical HIL separately qualified |
| Unified AXI/interconnect | SIM-0/1 + SIM-2 through **unified top** and production PS controller when implemented | XSim/vendor IP integration, timing and real interconnect |
| Shared buffer / 8-Site engine | SIM-0/1/2 only for **actual implemented** RTL: concurrency, abort, fairness, timeout, data isolation | Device-specific synthesis, timing, board-level throughput, power/signal integrity |
| Vivado IP/constraints/clock paths | Relevant SIM-3 + SIM-4 target reports under trusted execution authority | Hardware waveform/clock measurement and HIL |
| Physical DUT power/NRST/OE/SWD | Not signable by SIM-only | Explicitly authorized HIL, electrical evidence and restoration |

Use a change-impact classifier with **explicit paths → affected suites**,
but never use filename-only heuristics as proof of coverage. A modified
testbench must trigger its own real simulation. The target Workflow
Framework should expose reusable job interfaces, path coverage checks
(including negative path tests), bounded concurrency and explicit owners,
without recreating hundreds of per-catalog/per-family YAML files.

## 6. Reproducible evidence record (target interface)

Future SIM jobs should emit a machine-readable receipt such as
`verification-result.json` (schema and exporter are **not implemented
by this PR**) with at least:

```json
{
  "schema_version": "plasma-verification-v1",
  "commit_sha": "<40-hex source SHA>",
  "stage": "SIM-2",
  "status": "PASS|FAIL|NOT_RUN|BLOCKED",
  "runner_class": "github-hosted|trusted-swpc|authorized-hil",
  "runner_identity": "<recorded host and image identity>",
  "tools": {
    "python": "<measured exact version>",
    "simulator": "<name + measured exact version>",
    "cocotb": "<measured exact version>"
  },
  "rtl_top": "<actual instantiated simulation top>",
  "rtl_source_digest": "<content digest of tested RTL source set>",
  "driver_module": "<executed production control module or null>",
  "suite": "<test path and test selection>",
  "test_counts": {"passed": 0, "failed": 0, "skipped": 0},
  "seed": null,
  "ci_run_url": "<canonical Actions URL>",
  "artifacts": ["<simulator logs>", "<failing traces as applicable>"],
  "claims": ["<exact passing scenarios>"],
  "not_tested": ["<explicit nonclaims>"]
}
```

This is a **documentation example**, not a promise that current CI
generates such files. Record a test's real runner and whether execution
actually touched a host device; a successful mocked / dry-run job must
not masquerade as physical hardware evidence. `NOT_RUN` and `BLOCKED`
must never be collapsed into `PASS`. On failures preserve the test
selection, diagnostic log, waveform (if enabled), stimulus seed, and
relevant tool output with artifact provenance and retention policies.

Only compare outcomes when source/RTL scope, tool versions, test vectors,
model/board descriptor and verification stage are comparable. Explicitly
track **ABI revision** and **FPGA image identity** for vendor/HIL evidence.

### Phase 2 Core / Unified AXI evidence pilot (separate Gate 1)

The Phase 2 implementation increment adds a **Host-only SIM-2 pilot**, not a
blanket adoption of this proposed policy for every FPGA test:

- `pl/verification/verification-result-v1.schema.json`: versioned, strict receipt
  shape. `pl/tools/verification_evidence.py`: one reusable
  `run` / `validate` CLI for pytest-driven SIM evidence. The first enabled
  profile is SIM-2 against the Unified 64-KiB Site-1 RTL; existing
  `pl/tools/fpga.py` and other verification routes are preserved.
- Runner exports exact checked-out Git SHA, measured Python/pytest/Cocotb and
  Icarus versions, observed GitHub runner image identity, actual RTL source
  SHA256 list and aggregate digest, pytest JUnit case counts, logs and
  installed dependency fingerprint. Every reported PASS requires a real
  successful pytest command plus independently validated JUnit cases.
- The outer pytest wrapper counts as **one** case; nested Cocotb subcases are
  validated by the existing simulator runner but are **not** reported as
  separate counts in this receipt. Distinguish those boundaries in claims.
- Runner/Schema reject a false PASS, skipped-only run, missing toolchain
  fingerprint, mismatched source digest and contradictory NOT_RUN/BLOCKED.
  A tool, XML or source preflight problem is not silently coerced to PASS.
- Only the GitHub-hosted Unified AXI workflow emits this pilot receipt under
  `pl/build/verification/unified-sim2/verification-result.json` and uploads
  measured logs and receipts as Actions artifacts. It does not trigger
  SWPC, vendor tools or real-board activity.
- Full workflow inventory/migration, SIM-0/1 evidence parity, reusable GitHub
  workflow extraction, required-check policy, immutable image qualification,
  and SIM-3/4 XSim/Vivado remain **future independent work**. Preserve existing
  verification lanes until demonstrated equivalent; no green generic check
  may grant a stage that did not actually run.

The Phase 2 PR must pass Gate 1 CI and a **separate owner Gate 2** before
merging; an implementation proposal is not production acceptance.

## 7. Governance, rollout, and migration gates

**Gate A — this PR:** approve the target roles, definitions, exclusions,
version candidate table and future acceptance matrix. Documentation
and index only; no new CI, code, manifest exporter, runtime, hardware or
ruleset changes. Gate A PR is not a claim that the platform is operational.

**Gate B — separate owner approval:** merge these reviewed documents.
Before merge verify exact HEAD/main, applicable CI, mergeability and
review/ruleset requirements. Any changes require revalidation.

**Future independent implementation Gate 1:** inventory **all** relevant
existing FPGA workflows and real versions; select reproducible
toolchain/container strategy; implement reusable entry points, evidence
schema/exporter and migration/compatibility checks; integrate appropriate
SIM-0/1/2 cases without weakening assertions. Prove each legacy lane
has an equivalent replacement before retiring it; do not make an
unrelated migration a dependency of PR #1019 or current HIL.

**Future vendor/HIL Gate:** explicitly qualify XSim on SWPC (compile,
elaborate, simulate with a minimal RTL test, and check relevant licensing),
then synthesis/implementation targets under trusted-main restrictions.
Any future physical operation, FPGA reload, board/DUT and real MMIO test
requires an **independent explicit operator-approved HIL scope**.

## 8. Non-goals and precedence

This proposal does **not** revise the Fixed Hardware ABI v1, ADR-0002
catalog qualification, ADR-0003 driver/FPGA ownership boundaries,
existing security restrictions, GitHub branch/ruleset policy, or the
HIL evidence status. It does not start XSim, synthesize bitstreams,
merge another PR, authorize a real-board experiment, or promote M1
out of **NO-GO**.

Current implementation and test evidence take precedence over any
premature claim in this proposal. Contradictions must be resolved in a
separately reviewed and qualified change, never silently papered over.

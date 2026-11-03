# PLASMA M0–M4 — B/C Lifecycle, SWD Driver Decoupling and OpenOCD Roadmap

**Decision recorded:** 2026-11-03 (owner-requested roadmap, documentation only)  
**Status:** PLANNED / NOT AN IMPLEMENTATION APPROVAL  
**Product:** one embedded-Linux PS + FPGA PL PPU, ultimately eight independently programmable Sites, controlled by SWPC over the network.

This is a **prioritized engineering plan**, not evidence that a capability is implemented, deployed or HIL qualified. It does not override [AGENTS.md](../../AGENTS.md), current executable code, ADRs, or the separate approval gates. There is **no authorized merge, Z2 deployment, FPGA reload or DUT operation** in this roadmap PR. For each implementation tranche, obtain its own scoped **Gate 1**; merge a specific ready PR only with **Gate 2** approval. Changes to safety/privilege boundaries require evidence, not just fewer code paths.

## Product-level invariant

External operator workflow:

`Install Bundle → Run Job → Get Result`

Canonical install input remains **Bundle v3 → Packages → Files**. Do not introduce a separate unqualified Package install bypass. Internally, **B1 Receive → B2 Admission → B3 Install/Verify/Active**, and **C1 Job/Site Control → C2 Package/Programming Plan Resolution & Execution → C3 hardware/Site operation** are **responsibilities, not six Linux services**. No standalone B4 activation action, second deployment engine, second Job engine, hardware broker framework or duplicate OpenOCD RPC client.

Proposed execution responsibility:

| Boundary | Single owner of decisions |
| --- | --- |
| SWPC | Operator intent: Install, Run, Result; UI and network routing. No live OpenOCD or per-bit SWD on SWPC. |
| B1–B3 / Bootstrap | Receive, trust/admission, dependencies, verified installation, one atomic Active Asset Set selection. If an FPGA Image is present, standard Install **requests authorized guarded load by default**, then Image/ABI Identity PASS before publishing Active; if absent, select Active without PL reload. |
| C1 / Runtime SiteManager | Job authorization, exact selected Active Set/Package pinning, cancellation, PPU-wide Image reload exclusion, Per-Site Job ownership and scheduling. |
| C2 / Runtime | Resolve exact IC/profile/package/firmware and choose programming backend. Standard qualified OpenOCD operations should not require running an arbitrary Package process. Special Python/native-C Packages may use the existing sandboxed systemd executor. |
| C3 / Site Worker | One trusted control boundary for Site admission, operation execution, physical state, timeout/uncertain-outcome sealing and recovery. No bypass of verified Site ownership. |
| OpenOCD + `plasma_swd` native driver | OpenOCD owns SWD protocol, DP/AP and supported target Flash algorithms. Driver owns minimal low-level hardware transport/binding, MMIO ordering, Site/FPGA Image identity and mandatory hardware safety checks. FPGA PL owns deterministic SWD timing/FIFO. |

**Do not weaken** Root Guard / source trust, signed or otherwise authorized Manifest, Board/Part/ABI/Identity, FPGA reload fence, per-Site ownership, admission/voltage evidence, Golden recovery, no mid-Job Active pointer switch, `UNKNOWN` fail-closed or evidence-backed result classification. `ACTIVE` is not `JOB_READY`, and software/Host-only PASS is not physical IC Flash PASS.

## Ordered roadmap

| Milestone | Priority | Deliverable | Exit/acceptance |
| --- | --- | --- | --- |
| **M0 — restore hardware execution confidence** | **P0 / blocking** | Re-run Stage C D5 timeout/cancel cleanup after merged fix [PR #1280](https://github.com/physicslu/plasma/pull/1280); only after D5 PASS run D6 Site-2 probe and D7 seal recovery; independently fix [Runtime upgrade still executing old release #1263](https://github.com/physicslu/plasma/issues/1263). | Real Z2 process/cgroup cleared within bounded deadline; unconfirmed cleanup = `outcome_unknown` with safe resource exclusion; new Runtime release **actually running**, not merely new symlink/health of old PID; D6/D7 report real PASS/FAIL/NOT_RUN. |
| **M1 — bounded, read-only cross-layer Gap Audit** | **P0 / design prerequisite** | Inventory B1–B3/C1–C3/Root/OpenOCD/native SWD responsibilities, duplicate policy checks, IPC/process boundaries, Active Set states, timeouts/ownership, host-vs-Z2 evidence, and actual 1-/2-Site capacity. | Owner-reviewable responsibility matrix, source-backed minimal-delete/reuse plan, conflict list and explicit standalone PR scopes; no code, hardware or permission changes. |
| **M2 — minimal architecture implementation** | **P1** | 1) SWD Driver decoupling: OpenOCD controls protocol/Flash; native transport handles ABI/MMIO/hardware guards. 2) Standard B3 success = verified Active Set; default **explicitly authorized** FPGA load when Image present, no load when absent; align current staging-only gap in draft [#1278](https://github.com/physicslu/plasma/pull/1278). 3) C1/C2/C3 simplify standard Job path while preserving isolation for special Packages; select OpenOCD control method using measurements. | Focused PRs, Host-only and relevant ARMv7/QEMU regression, no duplicate decision owners; tests for aborted activation, Root guards, wrong image, Site conflicts, corrupted receipts, cancellation/recovery. HIL only after independently authorized deployment. |
| **M3 — single-Site physical programming product loop** | **P1 / primary product value** | First qualified STM32F103 Blue Pill Site-2 full SWD Probe → Erase → Program → Verify → Readback with exact ICPN/Flash geometry and electrical compatibility; SWPC Job submission and truthful Result/Receipt. | One actual PPU→FPGA→DUT end-to-end acceptance with immutable firmware/Active Set identity, matched readback, negative and cancel/fault cases. Host-only mock cannot substitute. |
| **M4 — Multi-Site expansion** | **P2 / after M3** | C1 Per-Site Job ownership and bounded scheduling, C3 per-Site admission and worker operations, OpenOCD per-active-Site lifecycle and independent ports/resources, global FPGA-reload fence; validate 1→2→8 Sites. | First two Sites concurrently execute and isolate faults, then eight-Site real HIL with CPU/RAM/PSS, latency/throughput, per-Site errors and recovery evidence; no assumption that two A9 cores can sustain eight full-speed processes. |

**Dependency order:** `M0 → M1 → M2 → M3 → M4`. Engineering spikes/Host-only benchmarks may overlap, but do not let an unfinished kill/recovery path control a DUT. M3 (one trustworthy physical Flash job) is a stronger milestone than PR count or refactor completion. M0 is not proven complete merely because #1280 merged.

## Three primary workstreams (owner request)

### A. SWD Driver decoupling

1. Enumerate every check in `plasma_swd_openocd5088_*.c`, Site admission, Root Guard and C3 adapter; tag as **transport mandatory**, **hardware privilege/ownership mandatory**, **device/target/Flash semantic**, or **duplicate policy**.
2. Keep protocol/target/Flash decisions with OpenOCD, not in MMIO primitives; keep physical authority at a non-bypassable trusted boundary. Never equate "remove duplicate checks" with "trust an unverified caller".
3. Reuse ABI v5 independent SWD engines and per-Site lock/reload-fence concept. Reconcile open drafts [#1189](https://github.com/physicslu/plasma/pull/1189), [#1218](https://github.com/physicslu/plasma/pull/1218), and [#1201](https://github.com/physicslu/plasma/pull/1201) before any implementation; none is automatically qualified for merging.
4. Verify negative wrong-Site, wrong-ABI, wrong-image, lock collision, concurrent reload, corrupted admission and unknown MMIO outcomes; preserve deterministic PL-owned SWCLK.

### B. B1–B3 / C1–C3 simplification

1. Avoid exposing internal phases as product actions. One operator Install result must not claim success unless the **new Set was selected Active**. Existing B3 `fpga_load:false` **currently stages only**; migration is code/API/receipt work, not accomplished by docs. Preserve explicit privilege-bearing `fpga_load:true` authorization for FPGA Image; product default never means silent escalation.
2. Keep Stage B and Stage C as distinct install and run transactions. Stage C must pin exactly one verified Set for a Job, reject any Active switch or FPGA reload while owned Sites run, and verify compatible FPGA/IC/Power/Site before physical execution.
3. Default qualified Flash route should be `C1 → C2 resolve profile → C3 → OpenOCD → PL`; keep the existing systemd isolated Package executor **only** for an actual Python/native-C Package need. Do not delete it before D5 safety and backward negative test requirements are met.
4. No extra Run/Activation/Result service, no browser direct FPGA API, no second Journal. Retain authentic Job/Flash receipts.

### C. OpenOCD operation choice

The repository **already contains** `plasma_interfaces.openocd_rpc.OpenOCDRpcClient` and `plasma_interfaces.openocd_worker.OpenOCDWorker`; see merged [#761](https://github.com/physicslu/plasma/pull/761) and port-lease fix [#823](https://github.com/physicslu/plasma/pull/823). **Reuse before introducing anything new.** Current C3 ABI-v5 adapter runs a one-shot OpenOCD CLI for Sites 1/2 `probe` only; its global running-OpenOCD guard and C1 PPU-exclusive Package lease block concurrent C3 Sites.

Evaluate on a common workload:

- **A:** current one-shot CLI per operation (baseline).
- **B (initial preferred candidate, to verify):** **one OpenOCD process per active Job/Site** with loopback-only Tcl RPC for all steps of that Job, then bounded stop/reap. Disable external GDB/Telnet/Tcl exposure.
- **C:** persistent per-Site OpenOCD over multiple Jobs only if data proves a compelling restart cost and reliable re-admission, complete prior-state clearing, FPGA identity/power revalidation, and crash recovery.

One OpenOCD native adapter instance currently binds one Site; Tcl RPC alone does **not** make one instance control eight independent adapters. Do not assume eight instances are needed at idle. Measure RSS vs PSS, CPU polling, and actual transfer/Flash throughput on Z2 before committing to eight concurrent processes. Avoid preemptive DMA, a new OpenOCD backend framework or custom Flash algorithm rewrite.

## Priority review of existing TODO / Issues

| Priority | Existing debt | Decision |
| --- | --- | --- |
| **P0** | [Stage C kill fix #1280](https://github.com/physicslu/plasma/pull/1280) merged; **real D5 requalification pending evidence** | M0 blocker. Do not infer Z2 PASS from merge/Host-only. |
| **P0** | [Runtime upgrade stale process #1263](https://github.com/physicslu/plasma/issues/1263) | Independent scoped fix before trusting installed-release HIL results. |
| **P0 before multi-IC physical production** | [IC Electrical Programming Profile / Voltage Capability Database](todo.md#ic-electrical-programming-profile--voltage-capability-database) | Integrate exact-IC and per-Site VDD/VPP/IO/current/power sequencing into admission, with manufacturer-backed evidence. A tightly scoped, controlled Blue Pill PoC need not wait for full manufacturer catalog coverage. |
| **P1 / align with M2** | [Generic FPGA Image Deployment #1170](https://github.com/physicslu/plasma/issues/1170), [B3 target draft #1278](https://github.com/physicslu/plasma/pull/1278) | One B3/Root contract; do not restore public B4. |
| **P1 / before independent parallel Sites** | [SWD independent Image/Owner #1189](https://github.com/physicslu/plasma/pull/1189), [UIO/Identity #1218](https://github.com/physicslu/plasma/pull/1218), [durable per-Site uncertainty #1201](https://github.com/physicslu/plasma/pull/1201) | Reconcile evidence and Root/Site recovery; Draft PR existence is not qualification. |
| **Production release prerequisite** | Security identity rollout in [TODO](todo.md#security-rollout-and-identity-integration) | Required before broadly exposing write APIs; not a reason to block safe lab Host-only exploration. |
| **Defer unless measured** | AXI DMA/split image data plane, mock convergence, UI profiles, display polish | Do not expand M0–M3 into speculative platform work. |

**Existing related TODO:** [Hardware API / OpenOCD Adapter Productization](todo.md#plasma-hardware-api--openocd-adapter-productization) remains a post-PoC design; do not claim UIO/IRQ/DMA/libplasma_hw is already production-current. The above roadmap is the coordination plan for near-term product behavior, not a blanket authorization to implement that entire future architecture.

## Verification and change control

- Before each scoped PR, check latest `main`, `AGENTS.md`, affected domain contracts, and existing open/merged PR overlap. Execute minimum relevant Host-only/CI and, when separately authorized, actual Z2 HIL.
- Record **exact SHA**, installed release and image identity, Platform and Site, Journal/Receipt, PASS/FAIL/NOT_RUN; never turn a Host-only pass into a physical PASS.
- This roadmap has no promised calendar dates, automatic action or background work. **No software behavior changes in this documents-only PR.**

# PLASMA M0–M4 — B/C Lifecycle, SWD Driver Decoupling and OpenOCD Roadmap

**Decision recorded:** 2026-11-03 (owner-requested roadmap, documentation only)  
**Status:** PLANNED / NOT AN IMPLEMENTATION APPROVAL  
**Product:** one embedded-Linux PS + FPGA PL PPU, ultimately eight independently programmable Sites, controlled by SWPC over the network.

This is a **prioritized engineering plan**, not evidence that a capability is implemented, deployed or HIL qualified. It does not override [AGENTS.md](../../AGENTS.md), current executable code, ADRs, or the separate approval gates. There is **no authorized merge, Z2 deployment, FPGA reload or DUT operation** in this roadmap PR. For each implementation tranche, obtain its own scoped **Gate 1**; merge a specific ready PR only with **Gate 2** approval. Changes to safety/privilege boundaries require evidence, not just fewer code paths.

## Product-level invariant

External operator workflow:

`Select exact MCU + Firmware + Sites → Resolve required Bundle/Packages → Prepare Once → Program Many → Release / Get Results`

The operator does **not** need to know or upload a Bundle before selecting the IC. SWPC resolves the content required by the chosen exact ICPN, firmware and Site capabilities. On a cache/Active-Set hit, skip B1 transfer and unnecessary B2/B3 install; otherwise stage the canonical Bundle v3 once during Prepare, with full authorization and freshness/identity checks. The same validated Programming Context can serve thousands of physically distinct DUTs without repeating Bundle transmission or PL configuration. **Every new DUT still requires its own Probe/target-state validation, electrical admission and truthful programming Result.**

Canonical install input remains **Bundle v3 → Packages → Files**. Do not introduce a separate unqualified Package install bypass. Internally, **B1 Receive → B2 Admission → B3 Install/Verify/Active**, and **C1 Job/Site Control → C2 Package/Programming Plan Resolution & Execution → C3 hardware/Site operation** are **responsibilities, not six Linux services**. No standalone B4 activation action, second deployment engine, second Job engine, hardware broker framework or duplicate OpenOCD RPC client.

Proposed execution responsibility:

| Boundary | Single owner of decisions |
| --- | --- |
| SWPC | Operator selects exact MCU, firmware and Sites; resolves required Bundle/Packages, initiates Prepare/Run/Release and observes Results. No live OpenOCD or per-bit SWD on SWPC. |
| B1–B3 / Bootstrap (**on-demand target**) | During Prepare only when required, Receive, trust/admission, dependencies, verified installation and atomic Active Asset Set selection; exit after a safe terminal transaction state. Preserve an **independently startable recovery path** even when Runtime/Gateway fails. A present FPGA Image requires authorized guarded load and Identity PASS; an absent or already compatible Image must not trigger unnecessary PL reload. The existing always-on Bootstrap is **not yet converted**. |
| C1 / `plasma-server` | Batch Programming Context lifecycle (PREPARING/READY/RUNNING/RELEASING/FAILED), Job authorization, pinned verified Bundle/Asset/Firmware identity, cancellation, PPU-wide Image reload exclusion, per-Site ownership and scheduling. |
| C2 / `plasma-server` | Resolve exact ICPN/profile/package/firmware and choose programming backend once per reusable Context, revalidating on material changes. Standard qualified OpenOCD operations should not require an arbitrary Package process. Special Python/native-C Packages may use the existing isolated executor. |
| C3 / **target: module inside `plasma-server`** | Integrate Job/Site hardware orchestration into the same long-running Programming Runtime process as C1/C2, rather than permanently operating a separate `plasma-site-worker.service`. M1 must audit migration/deletion and preserve Site admission, physical safety, timeout/uncertain-outcome sealing, recovery and non-bypassable hardware guards; current separate C3 Worker remains until an approved, qualified M2 transition. Linux privilege/group implementation is **deferred**, not waived. |
| OpenOCD + `plasma_swd` native driver | OpenOCD owns SWD protocol, DP/AP and supported target Flash algorithms. Driver owns minimal low-level hardware transport/binding, MMIO ordering, Site/FPGA Image identity and mandatory hardware safety checks. FPGA PL owns deterministic SWD timing/FIFO. |

**Target PS product-process lifecycle:** exactly **two always-running application processes** (`plasma-web` Gateway and `plasma-server` containing C1+C2+C3); **on-demand** Bootstrap for Prepare/install/recovery and **on-demand** OpenOCD processes only for active Sites, with optional safe reuse for multiple DUTs in one Batch. This is a **design target, not current Z2 service state**; count excludes ancillary OS processes and justified recovery/privileged helpers. Gateway remains distinct from SWPC Web/Controller/BFF. Whether the remaining privileged functionality needs a minimal helper is a separate technical audit, not a reason to assert existing C3 is already merged.

**Do not weaken** Root Guard / source trust, signed or otherwise authorized Manifest, Board/Part/ABI/Identity, FPGA reload fence, per-Site ownership, admission/voltage evidence, Golden recovery, no mid-Job Active pointer switch, `UNKNOWN` fail-closed or evidence-backed result classification. `ACTIVE` is not `JOB_READY`, and software/Host-only PASS is not physical IC Flash PASS.

## Ordered roadmap

| Milestone | Priority | Deliverable | Exit/acceptance |
| --- | --- | --- | --- |
| **M0 — restore hardware execution confidence** | **P0 / blocking** | Re-run Stage C D5 timeout/cancel cleanup after merged fix [PR #1280](https://github.com/physicslu/plasma/pull/1280); only after D5 PASS run D6 Site-2 probe and D7 seal recovery; independently fix [Runtime upgrade still executing old release #1263](https://github.com/physicslu/plasma/issues/1263). | Real Z2 process/cgroup cleared within bounded deadline; unconfirmed cleanup = `outcome_unknown` with safe resource exclusion; new Runtime release **actually running**, not merely new symlink/health of old PID; D6/D7 report real PASS/FAIL/NOT_RUN. |
| **M1 — bounded, read-only cross-layer Gap Audit** | **P0 / design prerequisite** | Inventory B1–B3/C1–C3/OpenOCD/native SWD, existing systemd process topology and IPC, Bootstrap service lifecycle/recovery, Context/cache/Active-Set behavior, multi-Site scheduling, timeouts and 1-/2-Site evidence. Evaluate the **two-daemon** target, on-demand Bootstrap and per-active-Site OpenOCD, and exact-IC-triggered **Prepare Once / Program Many / Release**. Identify conflicts with current implementation and safety boundaries; defer privilege/group design decisions. | Owner-reviewable **current-vs-target process matrix**, Batch Programming Context/state/identity contract, Bootstrap independent recovery/startup options, cache-hit/miss sequence, per-DUT revalidation requirements, measured/identified risks and smallest separately approvable M2 PR scopes. **Read-only; no service, code, hardware or permission changes.** |
| **M2 — minimal architecture implementation** | **P1** | 1) SWD Driver decoupling: OpenOCD controls protocol/Flash; native transport handles ABI/MMIO/hardware guards. 2) B3 success = verified Active; FPGA load still requires explicit authorization and is skipped when unnecessary; align draft [#1278](https://github.com/physicslu/plasma/pull/1278). 3) Implement exact-IC-selected Prepare/Context/cache and on-demand Bootstrap with independent recovery, only after verifying service activation feasibility. 4) Integrate C1/C2/C3 in one `plasma-server` product process; retain only indispensable narrowly scoped privileged functionality and special-Package isolation. 5) On-demand per-active-Site OpenOCD with safe multi-DUT Batch reuse subject to measurements/admission. | Focused PRs, Host-only and relevant ARMv7/QEMU regression, no duplicate decision owners; tests for aborted activation, Root guards, wrong image, Site conflicts, corrupted receipts, cancellation/recovery. HIL only after independently authorized deployment. |
| **M3 — single-Site physical programming product loop** | **P1 / primary product value** | First qualified STM32F103 Blue Pill Site-2 full SWD Probe → Erase → Program → Verify → Readback with exact ICPN/Flash geometry and electrical compatibility; SWPC Job submission, truthful Results and repeated-DUT handoff in one prepared Context. | One real PPU→FPGA→DUT end-to-end PASS plus separate-DUT repeat/handoff evidence **without repeat Bundle upload/install**, each DUT freshly probed/admitted, immutable firmware/Active Set identities, readback, negative and cancel/fault cases. Host-only mock cannot substitute. |
| **M4 — Multi-Site expansion** | **P2 / after M3** | Per-Site Context/Job ownership, scheduling, independent C3 orchestration, per-active-Site OpenOCD ports/resources and shared FPGA-reload fence; allow different exact MCU/Firmware/Profiles on Sites only when the same loaded FPGA Image and electrical resources are compatible; validate 1→2→8. | First two and then eight real Sites concurrently execute/isolate faults with CPU/RAM/PSS, throughput, per-Site Result and recovery evidence; conflicting required FPGA Images must reject/defer instead of mid-Job reload. |

**Dependency order:** `M0 → M1 → M2 → M3 → M4`. Engineering spikes/Host-only benchmarks may overlap, but do not let an unfinished kill/recovery path control a DUT. M3 (one trustworthy physical Flash job) is a stronger milestone than PR count or refactor completion. M0 is not proven complete merely because #1280 merged.

## Three primary workstreams (owner request)

### A. SWD Driver decoupling

1. Enumerate every check in `plasma_swd_openocd5088_*.c`, Site admission, Root Guard and C3 adapter; tag as **transport mandatory**, **hardware privilege/ownership mandatory**, **device/target/Flash semantic**, or **duplicate policy**.
2. Keep protocol/target/Flash decisions with OpenOCD, not in MMIO primitives; keep physical authority at a non-bypassable trusted boundary. Never equate "remove duplicate checks" with "trust an unverified caller".
3. Reuse ABI v5 independent SWD engines and per-Site lock/reload-fence concept. Reconcile open drafts [#1189](https://github.com/physicslu/plasma/pull/1189), [#1218](https://github.com/physicslu/plasma/pull/1218), and [#1201](https://github.com/physicslu/plasma/pull/1201) before any implementation; none is automatically qualified for merging.
4. Verify negative wrong-Site, wrong-ABI, wrong-image, lock collision, concurrent reload, corrupted admission and unknown MMIO outcomes; preserve deterministic PL-owned SWCLK.

### B. B1–B3 / C1–C3 simplification

1. Avoid exposing internal phases as product actions. One operator Install result must not claim success unless the **new Set was selected Active**. Existing B3 `fpga_load:false` **currently stages only**; migration is code/API/receipt work, not accomplished by docs. Preserve explicit privilege-bearing `fpga_load:true` authorization for FPGA Image; product default never means silent escalation.
2. Keep Stage B and Stage C as distinct install and run transactions **inside one operator-selected Prepare workflow**. Resolve required Bundle contents *after* exact MCU/Firmware selection. A valid cached Set skips transfer and reinstall, not freshness/authorization/identity checks. Stage C pins the verified Set for the Context/Job, rejects incompatible Active switch or FPGA reload while Sites run, and verifies FPGA/IC/Power/Site before physical execution.
3. Target the **single `plasma-server` process** for C1/C2/C3 modules: `C1 Batch/Job → C2 resolve profile → C3 Site operations → OpenOCD → PL`. Audit and retire the separate C3 daemon/IPC only after explicit fault, cancel, seal and independent Site ownership validation. Keep the existing isolated systemd Package executor **only** for actual Python/native-C Package needs; do not delete it before D5 safety/negative coverage is met.
4. **Programming Context contract (M1 design):** one Prepare obtains READY binding exact ICPN, firmware SHA256, canonical Bundle/Active Asset Set identity, Programming/Electrical Profile, Site(s) and compatible FPGA Image ID/ABI. READY can be reused for multiple DUTs, but each physical target needs fresh Probe, electrical/identity/ownership validation and its own Result/Receipt; a material change invalidates/re-prepares the Context. In M4 allow different Site Contexts only when all share a compatible global Image; pin active artifacts so another Site's setup cannot silently replace running content.
5. **On-demand Bootstrap contract (M1 design):** require an independent trigger/recovery path with safe journal reconciliation and no transaction interruption on idle exit. Evaluate socket activation vs bounded start-on-demand; current HTTP service is not assumed socket-activation-ready. No extra Run/Activation/Result service, no browser direct FPGA API or second Journal.

### C. OpenOCD operation choice

The repository **already contains** `plasma_interfaces.openocd_rpc.OpenOCDRpcClient` and `plasma_interfaces.openocd_worker.OpenOCDWorker`; see merged [#761](https://github.com/physicslu/plasma/pull/761) and port-lease fix [#823](https://github.com/physicslu/plasma/pull/823). **Reuse before introducing anything new.** Current C3 ABI-v5 adapter runs a one-shot OpenOCD CLI for Sites 1/2 `probe` only; its global running-OpenOCD guard and C1 PPU-exclusive Package lease block concurrent C3 Sites.

Evaluate on a common workload:

- **A:** current one-shot CLI per operation (baseline).
- **B (baseline implementation candidate):** **one OpenOCD process per active Job/Site** with loopback-only Tcl RPC for the Job, then bounded stop/reap; measure startup costs against long repetitive Batches. Disable external GDB/Telnet/Tcl exposure.
- **C (product Batch target, subject to proof):** start OpenOCD **once per active Site/Programming Context**, reuse across successive physical DUTs in a Batch, and stop on Release/timeout/error. Require a fresh target Probe and per-DUT validation, cleared previous target state, retained FPGA/Power identity, bounded cancellation and crash recovery; adopt only if HIL supports isolation and measured overhead justifies it.

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

# NXP MKL25Z128VLK4 — Runtime Qualification Readiness (Host-only Gate 1)

**Scope:** One exact commercial ICPN, `NXP/MKL25Z128VLK4`. Existing OpenOCD 0.12.0, source `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.

**Verdict:** `RUNTIME_READINESS_HOST_ONLY` is an evidence category, **not** a new Catalog Level or a qualified programming capability. The exact ICPN remains **L1 CANDIDATE**, NXP L2 remains **0**, Job and Execution authorization remain **false**.

## Minimal executable proof

Reuse existing `.github/workflows/z2-ps-release.yml` on GitHub-hosted x86_64 and ARMv7/Ubuntu 22.04 build/install candidates. Do not deploy to SWPC or Z2.

Inside an ephemeral container with the **already-installed** OpenOCD candidate:
1. Read release/source pin and source-only review v2. Check the exact ICPN, all non-admission flags and historic current-source blob locks.
2. Verify existing PLASMA install receipt (`/opt/plasma/install/openocd-runtime.json`): architecture, source commit, runtime_id, artifact SHA256, payload SHA256 and `hardware_runtime_ready=false`.
3. Measure **real executable SHA256** and prove ELF architecture matches the install receipt.
4. Measure installed `kl25.cfg`, `klx.cfg`, `swj-dp.tcl` bytes. Check their **Git blob SHA-1** against the pinned upstream exact-source review. Also emit these files' SHA256 for the per-run artifact.
5. Run the **real binary** `--version`, followed by strictly whitelisted `-c noinit -f interface/dummy.cfg -c "transport select jtag" -f target/kl25.cfg -c "echo ..." -c shutdown`. Reject any added `init`, `reset`, memory access, flash operation or replaced Tcl.
6. Upload the result to a per-commit GitHub Actions evidence artifact for each architecture. This proof does **not** establish reproducible binary output across independent builds; provenance is scoped to the measured artifact and binary.

The dummy **JTAG** transport is deliberately used only for Tcl parser registration. It is **not** a SWD probe or runtime qualification. The source's `swj_newdap` chooses transport from a session; no real adapter, debug DP, FCF, target power/reset, silicon revision or operational Flash behavior is tested here. The pinned `kinetis.c` Git blob is a **source review reference**, not a measured match between that source file and executable machine code. Build provenance from the existing packaging system is not installed-on-SWPC proof.

## Flash Configuration Field — contiguous full-image gap

- Device's expected 128 KiB main Flash: `[0x00000,0x20000)`.
- FCF bytes: `[0x400,0x410)`; **protected full sector**: `[0x400,0x800)`.
- Existing `KL25OpenOCDPlanCompiler` rejects **any PROGRAM overlap** with the entire protected sector and ERASE of that sector. It deliberately does not grant `SUPPORTED`.
- A **single contiguous full-image PROGRAM** starting at 0 and covering 128 KiB must FAIL at planning. It cannot silently truncate, implicitly erase, synthesize or modify FCF.
- Two partial image sections `[0,0x400)` and `[0x800,0x20000)` can be compiled **separately**, subject to all higher admission gates. This is not complete-firmware support: the omitted 1-KiB sector may hold essential vector/security/application bytes; no implicit composition into one Job is allowed.
- A sector erase outside FCF can be represented by the planner, not executed; `[0x400,0x800)`, mass erase, unprotect and security recovery remain outside approved scope.

The added unit regressions exercise full images, intentional holes, boundary straddles and exact one-sector erase only; passing tests do not prove silicon behavior or make these operations executable.

## Qualification evidence admission contract

The host-only JSON must state:
- `evidence_boundary=HOST_ONLY_NOINIT`, `host_parser=PASS`, `parser_adapter=dummy`, `parser_transport=jtag`.
- `swd_session_qualified=false`, `real_silicon_observed=false`.
- `software_state=CANDIDATE`, `catalog_level=1`, `job_selectable=false`, `execution_authorized=false`, `installed_runtime_attested=false`, `hardware_runtime_ready=false`.
- `READ/VERIFY/PROGRAM/ERASE_SECTOR=UNKNOWN`; no operation is certified.
- Future missing gates: real SWD/debug-ID, exact SDID/revision/FCFG geometry, FCF/security mutation proof, operation-level DUT results, independent qualification review.

The validator **fails closed** on altered receipt identifiers, mismatched SHA, modified installed Tcl, attempts to turn any negative gate into `SUPPORTED`/`true` or unknown operations into qualified operations. A manually written positive JSON statement is **not** admissible as evidence. Real target evidence must come from a separately scoped, reviewed and verifiable run; a report with a string `PASS` does not prove physical behavior. No production or L2 promotion is implemented.

## CI and safety boundary

- Path 1 only: GitHub-hosted CI in isolated temporary runners; reuse existing OpenOCD release cache.
- No new self-hosted Runner, SWPC, PYNQ-Z2, FPGA, LA, DUT or socket use; no OpenOCD target initialization or Flash commands.
- No Catalog maturity migration, Job Picker, Execution or Release deployment; no PR merge before explicit Gate 2.
- Required evidence: new Python unit cases; both x86_64 and ARMv7 real binary host-only receipts; existing Catalog Promotion Framework regression and all required PR CI.
- If KL25 target Tcl fails to register with the official dummy JTAG adapter, treat runtime smoke as **FAIL** and investigate it, not by silently enabling a real SWD interface or deleting noinit.

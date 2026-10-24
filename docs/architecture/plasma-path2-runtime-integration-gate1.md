# Path 2 Runtime Integration — historical offline Gate 1 baseline

**Original PR status:** offline/fake-device integration candidate; the initial
Gate 1 did not authorize Z2 hardware. Historical base: main
`8e909769601cd8cea82120c16b5c171b176c358d` (#1076/#1077/#1079).

**Current main:** Path 2 is a fixed CLI execution method, not a globally
Host-only mode. Build remains host-side; owner-authorized fixed Download,
Testing and Restore stage tasks route through the trusted-main Dispatcher,
`plasma_development_stage_transport.py` and protected Z2 root entry.
The old SWPC Bridge / separate approved-SHA PIN installer is obsolete.
Actual Z2 execution still depends on installed root source integrity and
fresh per-run authorization, observations and recovery evidence; the offline
results on this page cannot establish hardware PASS.

## Existing building blocks; no duplicate Build or Supervisor

- Trusted owner-only Issue #981 `plasma-engineering-runtime-dispatch.yml` and
  `scripts/plasma_development_dispatch.py` retain the trusted-main / immutable-PR-SHA
  separation and reuse the single SWPC runner when explicitly dispatched later.
- Existing `scripts/plasma_vivado_host_build.py` remains the only Vivado engine,
  with the fixed F1-B Project/Tcl, license admission and artifact verifier.
- Existing `scripts/plasma_path2_stage_orchestrator.py` manages individual
  `build`, `download`, `test` requests, independent transitions and receipts.
- Existing `scripts/plasma_path2_f1b_adapters.py` implements typed Build,
  held Download and Identity callback contracts; existing
  `scripts/plasma_path2_persistent_lease.py` provides an offline host-side
  test ledger; it is **not** the protected Z2 root checkpoint.
- NEW, narrow `plasma_path2_build_qualification.py` checks exact on-disk
  BIT/HWH, five Vivado reports, stdout/stderr hashes and build success marker,
  and **reuses** `pl/projects/z2-fixed-unified-site1/verify_hwh.py`.
  It produces a Build Qualification decision only when real files from the
  pinned worktree agree; it is not an additional Vivado implementation.
- NEW, narrow `plasma_path2_runtime_integration.py` attaches that decision
  to the existing F1-B Adapter and Stage Orchestrator. Real privileged
  Download/Testing providers were NOT supplied or installed by this
  **historical integration PR**; later trusted-main Stage Transport wiring is
  separate from these original candidate tests.

## Three separately triggerable reviewed task identities

| Historical owner Issue #981 command examples (not executed by this document) | Meaning |
| --- | --- |
| `/plasma-dispatch run z2-path2-build 981` | Run existing fixed Vivado Build **once**, independently check host outputs, deliver Build stage receipt |
| `/plasma-dispatch run z2-path2-download 981` | Historical candidate had no real Provider; current main routes an individually authorized Download through protected Stage Transport |
| `/plasma-dispatch run z2-path2-testing 981` | Historical candidate had no real Provider; current main routes independently authorized Testing through protected Stage Transport |

The historical `fixed-site1-vivado-host-build` command remains backwards
compatible. `z2-path2-build` invokes the **same** fixed engine, never a new
Build Engine. No command is sent to Issue #981 under this Gate 1.

For the new tasks only, `--auto-download` (Build) and `--auto-testing`
(Build/Download) are separate owner-selected per-run options. Both default
`false`. The existing Orchestrator treats `--auto-testing` on Build with
`--auto-download` false as Build only. Any Build request that could continue
to Download is rejected **before** launching Vivado by the Build-only adapter boundary. Individually authorized real
Download/Testing use the separate trusted-main Stage Transport, with root
integrity and live target checks; unqualified requests still fail closed.
Untrusted flags, wrong task, wrong SHA, PR metadata, replayed attempts,
arbitrary scripts, and unsupported capabilities remain denied.

The new Build receipt has scope `ADAPTER_RECEIPTS_ONLY` and
`status=RECEIPTS_VALIDATED`, meaning only a reviewed **Host-only**
build-stage result. This does not assert `z2_hil=PASS`, Site 1 programming,
ABI deployment, or any eight-Site feature.

## Physical safety boundary (still NO_GO)

Do **not** use historical `one_shot.run_live` as a persistent standalone
Download; it restores `base.bin`. Do **not** replay the dated temporary
passive-UIO exception from Path 3. The new task names and opt-in flags do not
grant SSH, sudo, MMIO, FPGA Manager or device-file capabilities.

Actual Download/Testing continue to require owner-approved Gate 1 scope and
verified trusted target safeguards covering:
1. fresh authenticated Z2 boot/FPGA loaded-image/manager facts and trust in
   origin of image receipts and BIT→BIN conversion;
2. exclusive *hardware-global* lock and Persistent Lease across separate
   triggers, atomic restore intent **before** writing, and lease renewal/expiry
   ownership while the image is held;
3. bounded AXI quiescence or an explicitly approved development risk policy,
   retained UIO/driver and process/VMA/FD observation, cancellation and
   child reaping on SIGBUS/AXI uncertainty;
4. real Download & guarded Restore backends, independently authorized and
   verified `base.bin` recovery, manual `UNKNOWN` treatment rather than blind
   retries/restore on unproven conditions;
5. native aligned 32-bit F1-B Identity callback, exactly three readbacks and
   zero writes from the **currently held** image; exact Boot/Lease/Source SHA
   revalidation before every separately triggered Test;
6. actual SWPC Run ID, checked-out source SHA, signed/reviewed origin evidence,
   device-log, exit codes and complete recovery verification.

The Persistent Lease is a host-side claim ledger and does not authenticate
device observations. The Host-only tests intentionally use fake backends and
file fixtures. **Neither the success of hosted CI nor the earlier Path 3
F1-B one-shot implies Path 2 held Download / Testing readiness.**

## Historical Gate 1 offline qualification (not hardware acceptance)

- Single existing Workflow; the `offline-contract` job executes only on
  GitHub-hosted `pull_request` or `push`; this Draft triggers no Issue #981
  comments, SWPC runner job, Vivado process or physical hardware.
- `scripts/tests/test_plasma_path2_runtime_integration.py` tests owner and
  immutable source admission; independently named stage contracts; the two
  flags and negative cases; no-op hard denial for unbound hardware; exactly
  one mock Build call; real local artifact digest mismatch and stage
  qualification; no hidden hardware PASS.
- The preexisting Path 2 / F1-B / Persistent Lease Host-only test suites
  continue to check the shared underlying contracts and default OFF policies.
- GitHub CI results and exact PR HEAD are recorded separately; no one may
  infer a CI PASS before it is observed.

No SWPC operation, FPGA reconfiguration, deployment, or merge is authorized
by this change.

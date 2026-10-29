# Path 2 Real Provider Integration — Development Gate 1

**Historical Gate 1 status:** the original offline candidate provided fake-target
Download / Testing / Restore contracts; it did **not** qualify live Z2 operation.
Original main base: `bcf500685f749fb8eb056248c518ed4fc1f4c285`
(includes #1076, #1077, #1079, #1081).

**Current Path 2 boundary (supersedes the candidate-only routing below):**
The trusted-main Dispatcher admits dynamic guarded-hardware `operator-cli`
Work Orders without a fixed F1-B Stage/Profile. It rejects the former
`z2-root-operation` Work Order. The retained Stage Transport and protected Z2
Root Entry can be invoked only as independently authorized, guarded tools;
they are not a mandatory Dispatcher route. The old SWPC Bridge / separate
approved-SHA PIN deployment is obsolete. This historical page's offline
tests do not prove current Z2 enrollment or a fresh real HIL PASS.

## What is actually implemented

- `scripts/plasma_path2_bin_provenance.py`: verify **separate** BIT/HWH/BIN
  SHA256, real file contents and F1-B raw Zynq Bootgen byte mapping, bind a
  Build-stage receipt to separately authenticated Bootgen execution evidence.
  Parsed JSON alone is **not** execution authentication; the trusted runner/
  target must validate its origin. The returned scope is strictly
  `BYTE_EQUIVALENCE_ONLY`, not loaded hardware.
- `scripts/plasma_path2_held_provider.py`: one shared core using the **existing**
  `LeaseLedger` and F1-B identity ABI, with a typed external
  `TargetPort`. Three entry functions have no CLI or default device access:
  `download_held`, `testing_held` and `restore_guarded`.
  The `bind_injected_stage_callbacks` function wires these as the existing
  F1-B Adapter's `held_download` and `identity_test` callbacks, allowing
  the **unchanged** Orchestrator to run independently triggered Download
  and Testing. It is a pure callback factory, **not** a trusted Dispatcher
  registration or an independently qualified target transport.
- Host-only unit tests use an explicitly fake target and a real local
  fsync/flock-backed ledger file. Negative cases include AXI/owner denial,
  image/Bootgen mismatch, competing persistent lease, expired lease, wrong
  boot, load failure, native-child SIGBUS and restore failure.
- `pl/hil/path2_z2_target_guard.py`: root-only **passive** Z2 observer,
  shared one-shot F1-B FPGA supervisor lock, protected fixed
  `/lib/firmware/base.bin` and F1-B BIN digest check, exact Site1
  AXI-window UIO/Platform-driver and process FD/VMA enumeration. Findings
  are emitted as actionable blockers. It never writes Manager firmware,
  authorizes a native MMIO child, installs a background daemon or registers a
  privileged route. A process lock + durable lease coordinates cooperative
  processes, not kernel DMA or unrelated privileged writers. Independent
  AXI isolation and active image attestation remain unproven even if all
  passive scans succeed; never substitute a one-shot owner risk waiver.
- `scripts/tests/test_plasma_path2_z2_target_guard.py`: filesystem
  simulation/negative tests for overlapping UIO, kernel resource overlap,
  retained `/dev/mem` FD/VMA, incomplete observation and denial of all
  unregistered write/test/restore methods.
- The privileged read-only collector ties the single overlapping
  Platform Driver to the **same resolved device** as `uio1`, not merely a
  similarly shaped name. `RootZ2TargetPort.inspect_cross_trigger()`
  reacquires the private persistent Lease and checks Boot ID, current manager
  `operating`, fresh nonconflicting process mappings, exact candidate filename
  in the current-boot Manager last-load trace, and unexpired held state before
  separate Testing/Restore. `MANAGER_LOG_ONLY_UNATTESTED` deliberately does
  **not** claim a loaded FPGA image has been cryptographically attested; its
  result explicitly grants no FPGA write capability. Test fixtures cover
  wrong Platform Owner, expired/unknown Lease, changed Boot ID and stale
  image load logs. No privileged route is registered or installed by these
  Host-only checks.
- The existing common GitHub Actions Workflow runs those tests in its
  **pull_request GitHub-hosted offline-contract job only**. It does not
  introduce any new self-hosted runner or workflow.

## Minimal repeatable Site1 F1-B Development Mode — current implementation

**Decision, 2026-10-21:** normal Download, Testing, and Restore must be
**repeatable under the same Site1 session**. The hardware lock serializes
operations; the state file records current observed image, Boot ID, last
operation, counts and error evidence. Neither a fixed Lease ID, an
everlasting once-only claim, nor attempt-count limits may prohibit a
normal operator-initiated repeat. The general Host-only `LeaseLedger`
contract is left unchanged for other providers; the **minimal target
runner** uses a simpler persistent checkpoint instead of reproducing
that excessive one-shot state machine.

The root-local candidate `pl/hil/path2_f1b_minimal_stage.py` exposes
exactly three **independently triggered** commands:

```text
export PLASMA_DEV_RISK_ACK=PLASMA_PATH2_F1B_SITE1_20261021_ONCE_BOUND_PASSIVE_UIO
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage download
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage test
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage restore
```

This is an interface specification **only after** a separately reviewed
root-owned installation of the exact code and trusted SWPC→Z2 invocation.
The literal waiver name is retained for traceability to the owner's
initial one-physical-experiment authorization; it is **not a blanket
approval** to run unattended future hardware experiments. The PR does not
install or register this runner and does not itself execute Z2 HIL.

The target-specific checkpoint `.plasma-f1b-site1-development-state.json`
is fsynced and atomically replaced in a root-protected persistent directory
before a firmware write or native MMIO child. It survives reboot but will
**reject a changed Boot ID until reviewed**, rather than assuming the PL
still contains the earlier image.

- **Download:** verify actual `base.bin` or F1-B currently loaded by
  the bounded Manager trace, exact candidate/recovery SHA256, accepted
  Site1 `uio1` exception and common FPGA lock. Persist
  `DOWNLOAD_IN_FLIGHT`, then call the existing Manager writer.
  On verified success record `F1B`; repeat requests are valid while
  the device remains safely observable. Never trigger Test automatically.
- **Testing:** require current F1-B and Boot ID, persist
  `TEST_IN_FLIGHT`; supervise a bounded native ARMv7 read-only child,
  read exactly three F1-B Identity words, zero writes; on success record
  `F1B` and increment the test counter. Repeat is supported.
- **Restore:** when F1-B is current, persist `RESTORE_IN_FLIGHT`,
  load pinned `base.bin`, verify Manager state and trace, record
  `BASE`. When `base.bin` is already verified, respond
  `ALREADY_RESTORED` without another bitstream write. A new Download
  remains possible afterward.
- **Genuine exceptions:** failure/SIGBUS/timeout/unreaped child or
  unresolved Manager image keeps `UNKNOWN` or in-flight state; do not
  blindly reconfigure. Review/recover the actual board state before
  admitting another write. AXI isolation remains
  `UNPROVEN` under the explicitly approved Development-only risk.

The exact native ABI (little-endian Zynq ARMv7, CPython 3.12.13)
is checked **before** any Load and again before native MMIO. Normal
repeat operations have no 900-second arbitrary Lease expiry. Neither
new firmware Build nor DUT/LA/power operation is included.

The GitHub-hosted offline tests use an injected fake FPGA Manager and
cover multiple Download/Test/Restore actions in one session, exact
three-word readback, no auto-chaining, changed boot or image, failures,
and safe idempotent restore. **Host-only tests are not real HIL**.
The historical candidate registered the three Task identities
(`z2-path2-download`, `z2-path2-testing`, `z2-path2-restore`), but its then-
planned SWPC Bridge installation prerequisite has been superseded. The live
Dispatcher no longer registers these fixed hardware stages; the protected
Root Entry remains an independently guarded tool. Missing root installation,
source-manifest mismatch, credentials, target ownership or recovery readiness
must fail closed. GitHub-hosted fake-device CI cannot prove a real Z2 stage.

## Evidence reuse / target admission (as of 2026-10-21)

The owner confirms Z2 is physically connected as before. This confirms
**physical availability**, not a current target session or OS-level AXI proof.
Reuse the fixed F1-B candidate Build/BIT/HWH/BIN hashes and the existing
one-shot Z2 Identity/Restore transcript. Do **not** rebuild Vivado or repeat
the previous one-shot HIL solely to satisfy a new checklist.

The new `RootZ2TargetPort` uses the same protected
`/run/plasma-z2-swd05/supervisor.lock` as the historical one-shot loader.
It checks current root, FPGA Manager state, candidate/recovery file hashes,
bound UIO and platform resources and per-process MMIO FD/VMA facts,
without touching any actual registers or writing a bitstream.
The local lock claim is tied to its thread/process and cannot be reused
across a fork. Vanishing/inaccessible processes make the scan incomplete,
never implicitly safe. This is **passive**, nonprivileged-to-command
diagnostics implemented as root-only code in a PR, not proof it has
been deployed or run on the actual connected Z2.

Only the following facts must be refreshed for any new physical trigger:
current authorized root identity/target code, boot ID, firmware and protected
recovery digests, FPGA Manager identity/load history, exclusive owner,
kernel/driver/DMA and process access, AXI quiescence mechanism and bounded
recovery operator route. Read-only refresh is not a repeat of Vivado or HIL.

**Current hard blocker:** prior F1-B one-shot retained
`uio1/uio_pdrv_genirq` at `0x40000000..0x4000FFFF` under an **explicit,
one-run owner risk exception**. The documented result was
`AXI isolation UNPROVEN_OWNER_ACCEPTED_RISK`. The Path 2 contract requires
independent safety admission of a held image across triggers; neither this
owner acknowledgment nor an idle IRQ counter provides that admission.
This PR intentionally leaves hardware writer and self-hosted trusted
Dispatcher activation **unregistered**. No FPGA Manager Download/Restore
or SWPC/Z2 HIL may be reported as run until those conditions are solved.
The owner has since approved the narrowly bounded development-risk
exception documented below; it does **not** bypass remaining root execution,
provenance, durable Recovery, or independent trigger gates.

### Fresh Z2 connection evidence — read-only, 2026-10-21

Real [GitHub Actions Z2 SSH-only readiness run #39522633934](https://github.com/physicslu/plasma/actions/runs/39522633934)
was dispatched via the already-reviewed owner-only
`/plasma-codex z2-readiness 981` Issue command on **trusted main**.
The sanitized, SHA256-included Action artifact reported exit `0`:

- authenticated SSH from SWPC to Z2: **PASS**;
- actual Linux, ARMv7, Zynq-7000 family: **PASS**;
- FPGA Manager state: `OPERATING`;
- Fabric and Audio UIO detected, both driver links visible (`count=2`);
- four PLASMA services (`plasma-bootstrap`,
  `plasma-runtime-activation`, `plasma-server`, `plasma-web`): `ACTIVE`;
- `baseline_result=BASELINE_PASS_PARTIAL`;
- `clock_fclk0=NOT_OBSERVED_UNPRIVILEGED`,
  `bitstream_identity=NOT_QUALIFIED`,
  `board_identity_exact=NOT_QUALIFIED`, `hardware_go=false`;
- `mmio_access=NOT_RUN`, `fpga_reload=NOT_RUN`,
  `uart=NON_BLOCKING_NOT_RUN`.

This **confirms current reachability**, not root-level F1-B Driver/AXI
isolation or Restore feasibility. The executed script was pinned trusted
**main**; the candidate branch's new `RootZ2TargetPort` has **not**
been executed on Z2. None of these current live results, nor the historical
one-shot AXI risk waiver, may promote `hardware_go` to true.

## Owner's amended Gate 1 — precisely bounded Site 1 development risk

**Approved owner instruction:** one PYNQ-Z2 Site 1 F1-B Development HIL
may accept the already observed `uio1/uio_pdrv_genirq` bound-passive
state while AXI isolation is `UNPROVEN`. This explicitly accepts the
chance of external abort, SIGBUS or unrecoverable AXI stall **for this
one development experiment only**. It does not provide AXI proof or
authorize Production, unattended execution, retries, further Sites,
DUT/LA/power changes, deployment or merge.

`pl/hil/path2_f1b_dev_risk.py` implements a **read-only** exact-state
policy and root-target observation: original `base.bin` active-load
dmesg provenance, the pinned candidate/recovery SHA256, same-boot root
facts, exactly `uio1/uio_pdrv_genirq` at the fixed 64-KiB aperture,
runtime PM suspended, zero observed fabric IRQ counts, one corresponding
bound platform device, no other overlapping driver, complete /proc FD/VMA
scan without relevant retained mappings, and active baseline services.
Any deviation is `NO_GO`. A checked policy result is **not** a
hardware-writing capability or independent AXI isolation proof.

Before executing even this amended development-risk HIL, a separately
reviewed and physically installed **root-owned Z2 command** must still
supply target-side privileged ownership across independently triggered
stages, immutable trusted source SHA, verified Bootgen execution provenance,
durable one-time recovery intent, original-image validation, bounded/reaped
native MMIO child, trustworthy actual loaded-image attribution, terminal
unknown/manual-recovery handling, and checked successful Restore route.
This paragraph described the **original Gate 1 gap**, before the protected
root entry and shared Stage Transport were wired into an earlier main. Their
fixed Stage task registration has since been retired; any live Z2 root
installation and all current
safety observations must be proved per authorized run. Neither the original
offline contracts nor a Dispatcher policy check establish FPGA Manager Download
or HIL PASS.

## Stage contracts and durable state

**Download** (separate Owner stage, future trusted target implementation):
validate exact Build/BIT/HWH/BIN identity and externally authenticated
Bootgen provenance. Acquire a **target-global exclusive lock**; require current
root route, global hardware owner, AXI idle isolation, kernel/driver/process
visibility, no retained consumers, verified protected original `base.bin`
and functional Restore route. Persist `RESTORE_REQUIRED` in the **target's
trusted ledger**, fsync. Transition `claim_load` **before** the only allowed
FPGA Manager write. Verify fresh observed manager and current loaded BIN
within the same boot. Return a Download Adapter receipt referring to the
original **BIT** SHA while the Lease pins the **BIN** SHA. FPGA remains
`LOADED_AND_HELD`; no automatic base restore at the end of Download.

**Testing** (independently triggered): reacquire target-global lock; reread
target facts and `LOADED_AND_HELD` lease; require exact source/target/boot/BIN
SHA, same load receipt, exclusive owner, still-safe AXI. Transition
`claim_test` and invoke the *future* native aligned-32bit isolated child.
Require exactly the fixed three F1-B read-only words, zero writes, exited
successfully, reaped, and no timeout. On success remain
`LOADED_AND_HELD`. A previous Download receipt by itself never grants Test.

**Restore** (independent privileged future stage; not a trusted Issue
command): reacquire lock, verify current candidate, process quiescence and
protected recovery bytes. Transition `claim_restore` **before** exactly one
recovery firmware write. Independently observe original manager state,
original services and UIO hashes before `RESTORED_VERIFIED`. On any
uncertainty write `UNKNOWN_MANUAL_RECOVERY`; never blind retry or
unconditional restore after SIGBUS, AXI stall, or unreaped child.

## Historical TargetPort admission gaps and continuing hardware safeguards

The original Gate 1 did not install the physical root provider; the old
`PATH2_LIVE_PROVIDER_NOT_REGISTERED` description is a historical baseline,
**not** the current trusted-main registration state. Current main uses
dynamic `operator-cli` for reviewed hardware scripts; the protected Z2 Root
Entry remains available only through independently authorized calls. An injected
callback/fake never authenticates target state. GitHub-hosted CI cannot post
an Issue #981 hardware command merely to qualify these contracts.

For each new owner-authorized physical attempt, the following safeguards
remain applicable. Historical gaps are not automatically marked PASS merely
because the Stage Transport now exists:
1. A trusted **target-local** executable (root-owned, exact code SHA,
   non-world-writable), authenticated transport from the pinned SWPC command,
   actual root permissions, and protected immutable Z2 recovery file/hash.
   Do not execute candidate PR Python as root merely because it passed CI.
2. A hardware-global persistent FPGA Configuration Owner shared by
   independently triggered tasks (not just SWPC's JSON lock). The owner must
   hold/reconcile the target's exclusive state across trigger gaps. A process
   `flock` held during one command **is not** a cross-trigger owner.
3. A **credible** independent AXI-quiescence or reviewed risk mitigation,
   including bound UIO Driver state, all kernel AXI users and retained
   `/dev/mem`/UIO FDs/VMAs. Prior Path 3 bound-`uio1` one-shot
   exception is not transferable; the observed AXI isolation remained
   UNPROVEN. A callback returning `axi_idle_isolated=True` is not
   independent evidence.
4. Actual Bootgen 2026.1 execution log/source custody, review of both BIT and
   BIN hashes, and target-side confirmation that the BIN remains the
   running FPGA image. `fpga_manager/state=operating` and dmesg alone
   cannot cryptographically identify loaded configuration.
5. Target-local trust-root for fresh kernel/boot/manager/image observations;
   bounded native child execution and SIGBUS containment; restoration
   operator/UART/recovery route; timeout and power-failure policy. Lease TTL
   is at most 900 s; **no watchdog, lease auto-extension, or unconditional
   timeout restore exists**.

Hardware root/Z2 facts are unobservable from GitHub-hosted CI. The original
Gate 1 was hardware NO_GO; the current route is registered but may run only
when the owner-authorized scope and live root/target prerequisites all pass.
Any unverified or failed condition remains NO_GO / NOT_RUN for that attempt;
no fake hardware PASS may be reported.

## Historical Gate 1 validation scope (not a fresh execution authorization)

Review the exact PR HEAD, common workflow's `offline-contract` job, all
GitHub-hosted CI, Rulesets and Review Threads. Do **not** invoke the shared
self-hosted Runner or owner Issue #981 merely to exercise callbacks. Do not
merge, deploy, reprogram FPGA, use DUT/LA or alter power. The candidate
should remain Draft until available evidence is independently reviewed.

**Current acceptance requirement:** verify the installed root-owned Z2
entry, source manifest, pinned work/source identity, hardware-global owner,
recovery and per-run current-boot/AXI observations under the existing trusted
Dispatcher. The original Gate 1 test results alone do not establish these
facts and are not permission to operate SWPC/Z2.

# Path 2 Real Provider Integration — Development Gate 1

**Status:** Candidate **Host-only implementation**, with bounded held Download /
independent Testing / separate Restore transaction contracts. **Z2 hardware
execution is NOT qualified or registered.** Existing main base:
`bcf500685f749fb8eb056248c518ed4fc1f4c285` (includes #1076, #1077,
#1079, #1081).

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
- The existing common GitHub Actions Workflow runs those tests in its
  **pull_request GitHub-hosted offline-contract job only**. It does not
  introduce any new self-hosted runner or workflow.

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

## The missing *real* TargetPort: hardware NO_GO

This PR deliberately does **not** provide a trusted Z2-side root
`TargetPort` implementation or register it in
`scripts/plasma_path2_runtime_integration.py` or the Dispatcher.
`z2-path2-download` and `z2-path2-testing` still fail closed with
`PATH2_LIVE_PROVIDER_NOT_REGISTERED`. An injected callback/fake can never
be treated as actual target observation. No Issue #981 command may be
posted by GitHub-hosted CI.

Before a real implementation may be registered, these **missing** facts must
be established and independently reviewed:
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

Hardware root/Z2 facts are unobservable from GitHub-hosted CI. Until a
reviewed endpoint and all five items exist, **hardware operations are NO_GO**
despite the user's Gate 1 scoped permission. No fake hardware PASS can be
reported. The user authorized conditional real HIL, not bypassing these
preconditions.

## Validation scope / Gate reporting

Review the exact PR HEAD, common workflow's `offline-contract` job, all
GitHub-hosted CI, Rulesets and Review Threads. Do **not** invoke the shared
self-hosted Runner or owner Issue #981 merely to exercise callbacks. Do not
merge, deploy, reprogram FPGA, use DUT/LA or alter power. The candidate
should remain Draft until available evidence is independently reviewed.

**Next required hardware milestone:** implement and qualify the concrete
root-owned Z2 TargetPort + mutual hardware-owner lock and safe
current-boot/AXI attestation, then submit a separate reviewed branch-SHA
execution on SWPC **only if** all stop conditions pass. This Gate 1 has not
made those target facts true.

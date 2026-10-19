# PLASMA HIL-A2 — gated Path 2 native Cortex-A9 CPU-only candidate

**Gate 1: software and GitHub-hosted offline contracts only. NOT_RUN on SWPC or Z2; M1 NO_GO.** No dedicated workflow, merge, deployment, USB, FPGA, MMIO, DUT, hub power or physical HIL operation authorized.

## Baseline

- Base main 121a7b3da6ecc1513b47d397ad70e68c9820f789, after PR #1049 merge.
- Existing reusable workflow: .github/workflows/plasma-engineering-runtime-dispatch.yml (Development Mode).
- Existing SWPC-plasma-codex nonroot worker: fixed CLI Path 2; no Codex invocation.
- Registry: specs/engineering-dispatch/development-tasks-v1.json. HIL-A2 is a fixed reviewed task; there is no per-run activation switch.
- Work Order: specs/engineering-dispatch/work-orders/hil-a2-cpu-only-r1.json. Its reviewed_main_sha is the original contract baseline; each trusted owner event pins the real execution main SHA separately, without editing the Work Order for every run.
- Production runtime-activation-v1.json and capabilities-v1.json remain disabled; the new z2-cpu-only definition is not a live runtime route.

## Immutable HIL-A1 inputs

| Attribute | Pinned expected |
| --- | --- |
| Source GitHub run | 39192248348 |
| Artifact ID | 12160282344 |
| Artifact name | plasma-armv7-hil-a1-pr-39192248348 |
| Filename | libplasma_mmio_barrier.so |
| ELF SHA256 | 435e8a1e14b644396a5a14b52211bb50535176448442c08b4b55aed1a0463956 |
| Export | plasma_mmio_dmb_sy |
| Calls | exactly 1,000 |

Artifact expires 2026-11-02 02:56:05 UTC unless its exact content and provenance are preserved through a separately reviewed process. Expired or missing artifact is BLOCKED, never silently rebuilt. Reuse the existing A1.5 seven-file pinned verification and ELF32 EABI5 metadata checks.

## Shared Dispatcher integration — fixed contract, per-comment owner authorization

The potential future owner command is `/plasma-dispatch run hil-a2-cpu-only 981` on GitHub Issue #981. **This Gate 1 only changes code and hosted CI; it does NOT approve posting that comment or operating physical hardware.** A later explicit owner Gate 1 must name the allowed Z2, native CPU-only test, safe readiness/recovery conditions and repeat policy.

The immutable main-checked-out Registry and Work Order describe **what** the command can do; they do not require changing Registry, Work Order, Repository Variable or source files for every experiment. Each newly created exact owner Issue comment provides one specific approved attempt:

1. GitHub-hosted `development-authorize` verifies owner/comment/repository/Issue/created-only/main checkout and validates the fixed hardware-one-shot Work Order against the disabled-capability Policy. The Issue comment ID, SHA of frozen Work Order JSON, and trusted actual main commit produce one deterministic Claim ref.
2. GitHub-hosted `development-claim` gets `contents:write` **only within this job**. It atomically creates `refs/heads/plasma-engineering-claims/981/a2-<comment-id>-<digest-prefix>-r1` pointing to the reviewed main SHA, reads the ref back and records a sanitized Claim Artifact. Active repository Ruleset #25329605 prevents updating, rewriting or deleting claim refs. If token cannot create, if ref already exists, or if readback fails, **no SWPC job may start**. No automatic retry, cleanup or Ruleset bypass. Actual CREATE enforcement under the Actions identity remains untested; CI mocks do not qualify the live claim.
3. The existing shared `development-execute` SWPC job permits A2 **only after** successful Claim output exactly matches the hosted authorization. PR/push jobs never dispatch SWPC. Existing `nine-nine-path2` still uses the original non-hardware path.
4. Before SSH, the SWPC CLI rechecks event owner/Issue, exact comment, pinned SHA, source Work Order digest, Claim ref, `GITHUB_RUN_ATTEMPT == 1`, non-root worker and artifact hash. A rerun of the same GitHub Actions attempt is rejected; a new valid owner comment has a fresh Claim ref and can represent a **separately authorized** attempt.

This avoids state toggles while preserving fail-closed replay control. A successful offline test of this architecture is **not** proof that the live GitHub Claim can be created nor that Z2 is safe or reachable. The shared worker's existing Linux device groups do not provide hardware-level isolation; CPU-only restrictions are contractual and the remote Python code has an explicit allowlist.

The shared workflow downloads only the pinned A1 Artifact for an authorized, claimed A2 attempt and uploads a sanitized JSON receipt + SHA256 and hosted Claim Artifact. A2 remote execution uses the existing worker-specific 0600 password credentials and independently verified pinned known_hosts; no private host, credentials or raw output are published. The remote Python program writes the verified ELF to a non-root temporary folder, loads it with ctypes.CDLL, calls the barrier exactly 1,000 times and cleans up. No `/dev/mem`, `/dev/uio`, FPGA Manager, USB, UART, JTAG, LA, reset, NRST, hub power, DUT or deployment operations.

## Evidence contract: plasma.hil.a2.z2.cpu-only.v1

The report is separate from HIL-A1.5 QEMU. It requires execution_target ENROLLED_REAL_Z2_CORTEX_A9, ARMv7 CPU part 0xc09, ELF32 little-endian user space, Zynq-7000 device tree, enrolled SSH, verified binary SHA, successful library load, function plasma_mmio_dmb_sy, exactly 1000 calls, and temporary_cleanup PASS.

A sanitized GitHub receipt adds source run, source artifact ID, runner name, GitHub Run ID, pinned SHA, digest check and exit code. Mark board_identity_exact NOT_QUALIFIED, mmio_uio NOT_RUN, fpga_reload NOT_RUN, dut_programming NOT_RUN, hub_power NOT_RUN and M1 NO_GO. A QEMU report, unexpected fields, missing cleanup proof, incorrect digest, SIGILL, timeout or SSH failure cannot be relabeled as native A2 PASS. The SHA256SUMS manifest is required for uploaded evidence.

CPU DMB SY execution alone proves no PS7-to-AXI/PL posted-write completion, mapping attribute validity, MMIO safety, eight-Site qualification or DUT programming.

## Offline acceptance and future blockers

Hosted CI runs scripts/tests/test_plasma_hil_a2_cpu_only.py: positive synthetic native receipt; negative wrong CPU, machine, hash, count, forbidden hardware claims and extra fields; wrong task paths and Issue events; fake Claim-bound valid and replay-denied admission; existing Path 2 and Path 3 regression. No real SSH or Z2 HIL is executed by these tests.

Before any future real HIL, verify the live Claim-ref CREATE/readback canary under the same Actions identity and enforce actual safe Z2 site ownership and recovery facts; a generic Zynq-7000 Device Tree and Cortex-A9 do not establish exact PYNQ-Z2 board identity. The historical hardware-capable Linux worker group cannot be called a true OS sandbox.

**This PR stops at Gate 2 review. Real Z2 A2 = NOT_RUN; M1 = NO_GO.**

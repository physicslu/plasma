# PLASMA HIL-A2 — gated Path 2 native Cortex-A9 CPU-only candidate

**Gate 1: software and GitHub-hosted offline contracts only. NOT_RUN on SWPC or Z2; M1 NO_GO.** No dedicated workflow, merge, deployment, USB, FPGA, MMIO, DUT, hub power or physical HIL operation authorized.

## Baseline

- Base main 121a7b3da6ecc1513b47d397ad70e68c9820f789, after PR #1049 merge.
- Existing reusable workflow: .github/workflows/plasma-engineering-runtime-dispatch.yml (Development Mode).
- Existing SWPC-plasma-codex nonroot worker: fixed CLI Path 2; no Codex invocation.
- Registry: specs/engineering-dispatch/development-tasks-v1.json. HIL-A2 activation defaults to DISABLED_GATE1.
- Work Order: specs/engineering-dispatch/work-orders/hil-a2-cpu-only-r1.json. It is a planning baseline pinned to the original main SHA; a future independently approved hardware Gate 1 must rebind that SHA after merge.
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

## Shared Dispatcher integration — deliberately disabled

The possible future owner command is /plasma-dispatch run hil-a2-cpu-only 981, but posting or executing it is NOT authorized by this Gate 1.

A separate physical Gate 1 must first approve a reviewed main SHA, current hardware state, pinned SSH host, work scope, replay prevention, cleanup plan and exact one-shot authority. The currently checked-in registry activation and Work Order runtime_status are DISABLED_GATE1. Only a later reviewed change can set both to OWNER_APPROVED_ONE_SHOT. Even then, the repository variable PLASMA_HIL_A2_CPU_ONLY_ENABLED must be separately set to true. No variable is changed by this PR.

The existing shared Workflow alone will perform hosted owner admission and then fixed CLI execution on the existing SWPC-plasma-codex runner. The A2-specific download of the exact GitHub A1 artifact is conditional on authorized A2 selection. Pull requests and main pushes run only hosted contract checks.

A2 remote execution uses the existing worker-specific 0600 password credentials and independently verified, pinned known_hosts. It does not invent or enroll a host or expose secrets to artifacts. The candidate remote program writes the exact SHA-verified ELF only to a temporary folder as a nonroot user, loads it with ctypes.CDLL, calls 1,000 times and cleans up. This is CPU-only: no /dev/mem, /dev/uio, FPGA Manager, USB, UART, JTAG, LA, resets, NRST, hub power, DUT or deployment.

## Evidence contract: plasma.hil.a2.z2.cpu-only.v1

The report is separate from HIL-A1.5 QEMU. It requires execution_target ENROLLED_REAL_Z2_CORTEX_A9, ARMv7 CPU part 0xc09, ELF32 little-endian user space, Zynq-7000 device tree, enrolled SSH, verified binary SHA, successful library load, function plasma_mmio_dmb_sy, exactly 1000 calls, and temporary_cleanup PASS.

A sanitized GitHub receipt adds source run, source artifact ID, runner name, GitHub Run ID, pinned SHA, digest check and exit code. Mark board_identity_exact NOT_QUALIFIED, mmio_uio NOT_RUN, fpga_reload NOT_RUN, dut_programming NOT_RUN, hub_power NOT_RUN and M1 NO_GO. A QEMU report, unexpected fields, missing cleanup proof, incorrect digest, SIGILL, timeout or SSH failure cannot be relabeled as native A2 PASS. The SHA256SUMS manifest is required for uploaded evidence.

CPU DMB SY execution alone proves no PS7-to-AXI/PL posted-write completion, mapping attribute validity, MMIO safety, eight-Site qualification or DUT programming.

## Offline acceptance and future blockers

Hosted CI runs scripts/tests/test_plasma_hil_a2_cpu_only.py: positive synthetic native receipt; negative wrong CPU, machine, hash, count, forbidden hardware claims and extra fields; wrong task paths and activation; disabled owner gate; existing Path 2 and Path 3 regression. No real SSH or Z2 HIL is executed by these tests.

Before any future real HIL, fix one-shot replay prevention: the current Development Mode Issue command can be posted repeatedly and is NOT a durable hardware claim. Also require current safe Z2 site ownership and recovery facts; a generic Zynq-7000 Device Tree and Cortex-A9 do not establish exact PYNQ-Z2 board identity. The historical hardware-capable Linux worker group cannot be called a true OS sandbox.

**This PR stops at Gate 2 review. Real Z2 A2 = NOT_RUN; M1 = NO_GO.**

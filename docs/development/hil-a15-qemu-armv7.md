# PLASMA HIL-A1.5 — Pinned ARMv7 Barrier Library QEMU execution

**Status: Gate 1 candidate. QEMU is simulation, NOT PYNQ-Z2 HIL-A2. M1 NO-GO.**

## What is being verified

The exact A1 artifact is `libplasma_mmio_barrier.so`, produced on GitHub-hosted by the cross-compiler and verified by static ELF/ABI/`dmb sy` inspection. HIL-A1.5 adds a separate **runtime** proof: an actual 32-bit little-endian ARMv7 Linux Python process `ctypes.CDLL`-loads this binary, calls the exported `plasma_mmio_dmb_sy` function 1,000 times, checks exit status and records environment and digest. It never performs MMIO stores. QEMU may emulate a barrier without reproducing Cortex-A9/PS7/AXI memory-ordering effects; simulated success is NOT hardware acceptance.

## Frozen upstream A1 identity (immutable inputs)

| Field | Exact value |
| --- | --- |
| Repository | `physicslu/plasma` |
| A1 Run | [39192248348](https://github.com/physicslu/plasma/actions/runs/39192248348) |
| A1 run branch HEAD | `4f79aea1744333bb08720aa9cbda555140523066` |
| Artifact ID | `12160282344` |
| Artifact name | `plasma-armv7-hil-a1-pr-39192248348` |
| .so SHA256 | `435e8a1e14b644396a5a14b52211bb50535176448442c08b4b55aed1a0463956` |

Download always pins the exact run/repository/artifact name and uses read-only `actions: read` permissions; the offline verifier additionally fails on an unrecognized file, symlink, unexpected manifest name, duplicate/path traversal, unsigned receipt provenance, incorrect ELF32 little-endian ARM EABI5 header, mismatched .so SHA, A1 `receipt.json` mismatch, or any SHA256SUMS mismatch. The artifact is retained for 14 days; an expired archive is a **blocking dependency**, never permission to silently substitute another build. A zip/digest or SHA256 alone is evidence of content identity, not proof of target CPU ordering.

## Gate 1 PR CI: isolated GitHub-hosted QEMU

Files: `.github/workflows/plasma-hil-a15-armv7-qemu.yml`, `scripts/hil-a15-armv7-qemu.py`, `scripts/hil-a15-gh-hosted-qemu.sh`, `scripts/hil-a15-contract.py`, and offline negative tests.

- PR-only trigger and one `ubuntu-24.04` GitHub-hosted job. **No** `workflow_dispatch`, self-hosted Runner, SWPC CI, Z2 SSH, production Docker or hardware permission.
- Pin the artifact source, `actions/download-artifact` revision, QEMU binfmt action and image; QEMU image reuses PLASMA's existing pinned `arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c`.
- The temporary GitHub-hosted VM registers ARM emulation through pinned `docker/setup-qemu-action`, then launches an **ephemeral, isolated** ARMv7 Docker container with `--network none`, `--cap-drop=ALL`, `--read-only`, limited memory/processes, a private `/tmp` and read-only artifact/source mounts. This is not the persistent SWPC `plasma-z2like-demo-qemu` container.
- Host verifies A1 archive before the container starts; inside ARMv7 Linux, the probe verifies it again before any `ctypes` load. It requires `platform.machine()` = ARMv7, 32-bit pointer size and little-endian userspace.
- Only `plasma_mmio_dmb_sy` is called, exactly **1,000 times**, with `argtypes=[]` and `restype=None`. Process timeout is 120 seconds. Failure, SIGILL, loader/ABI errors or digest mismatch are **FAIL**, never inferred PASS.
- A fresh `qemu-execution.json` plus `SHA256SUMS` is uploaded as GitHub CI Artifact on PASS. Report explicitly sets `real_z2_a2=NOT_RUN`, `mmio_uio=NOT_RUN`, `fpga_dut=NOT_RUN`, `m1=NO_GO`.

**PR test success qualifies only GitHub-hosted QEMU, not the existing SWPC QEMU.** Do not call the persistent SWPC test PASS without a real, logged, separately authorized run on SWPC.

## Planned SWPC Z2-like QEMU execution (design only, NOT RUN)

SWPC already hosts one canonical Z2-like QEMU backend (`scripts/z2like-demo-qemu.py`, container `plasma-z2like-demo-qemu`), which is currently production-like simulation infrastructure serving the remote Control Station. For this Gate 1, **do not run `docker exec`, `docker cp`, `plasmactl`, SSH, any hardware command, or modify the persistent container.** No SWPC job/dispatch is added to the PR.

After a separately approved execution scope, use this design:

1. Check the actual SWPC runner/session identity, `docker inspect` canonical container image/digest/ARMv7 architecture, current container health, and temporary scratch-space allowance. Abort on unexpected container state; do not restart, update or alter published networking/ports.
2. Stage the exact A1 artifact through a controlled, read-only source with the frozen run ID, artifact name, SHA256SUMS and binary SHA. Reject mutable local files unless matched to the frozen evidence. Do not modify service volumes, `/opt/plasma`, binaries or PLASMA Gateway.
3. Prefer an **independent ephemeral ARMv7 QEMU container** attached to no network rather than instrumenting the persistent public backend; document any difference in image/libc/Python from the live `plasma-z2like-demo-qemu`. Only if owner explicitly approves service-adjacent validation should the test enter the existing container, and then only from private `/tmp`, without writes outside its test directory.
4. Use the same `scripts/hil-a15-armv7-qemu.py verify/execute` contract; record CPU, Python, `ctypes` status, 1000 calls, library digest before/after, total process exit code, SIGILL/timeouts and cleanup state. Explicitly label the report `SWPC_QEMU` rather than `GITHUB_HOSTED_QEMU`.
5. Always preserve the existing z2like-demo backend and Control Station service state. Never touch actual Z2, `/dev/mem`, `/dev/uio*`, FPGA Manager, bitstreams, SWD, NRST, power, or DUT.

**A2** remains a separate future experiment on the true PYNQ-Z2 ARMv7 Cortex-A9 after power-up and its own scope authorization. Even Z2 CPU-only success does not prove PS7→AXI/PL posted-write completion. M1 remains **NO-GO**.

# PLASMA HIL-A — GitHub-hosted ARMv7 cross-build (A1) / Z2 CPU execution (A2)

**Status: Gate 1 candidate, independent PR; no merge without Gate 2. M1 NO-GO.**

## Why the build host changed

Original A1 SWPC run [#39190582095](https://github.com/physicslu/plasma/actions/runs/39190582095) reached real `SWPC-plasma-ci`, passed authentication/checkout and then exited 2 before compilation: ARM cross compiler or binutils missing from the Runner PATH. This is not an ARMv7 compiler defect or Z2 HIL observation.

The new A1 moves **only compilation and static ELF inspection** to GitHub-hosted Ubuntu. A2 stays future Z2 ARMv7 native CPU execution and remains **NOT_IMPLEMENTED / NOT_RUN**. No SSH, physical MMIO/UIO, FPGA configuration, DUT, deployment or SWPC runner is invoked by the new A1 workflows.

## A1 workflow & reproducible toolchain

- Manual/main-only workflow: `.github/workflows/plasma-armv7-barrier-hil-a.yml`; only `workflow_dispatch`, repository `physicslu/plasma`, `refs/heads/main`, actor `physicslu`, GitHub-hosted `ubuntu-24.04`.
- PR build: `.github/workflows/plasma-armv7-barrier-hil-a-contract.yml`. All PR jobs execute on GitHub-hosted `ubuntu-24.04`; they run negative/contract tests **and real ARMv7 ELF cross-compilation**, not just a synthetic `objdump` fixture. This PR route is not a hardware dispatch.
- Both workflows call exactly the same committed `scripts/armv7-barrier-hil-a1-hosted.sh` script. The script uses `docker run --platform linux/amd64` **on the GitHub-hosted VM** (never the user's SWPC Docker host).
- OCI base: `debian:bookworm-20261005@sha256:bc49dc1918ee1a47a93e65b5e4676e8680fb754b133197b92ca52bfe6731d5f0` (pinned official Debian amd64 manifest).
- Package archive: `http://snapshot.debian.org/archive/debian/20261005T000000Z/`, `bookworm main`, Debian package signatures still verified by APT over the HTTP bootstrap transport (minimal OCI image lacks CA certificates); date-pinned package indexes. TLS downgrade is limited to the APT bootstrap and does not disable GPG signature validation. Packages: `python3`, `git`, `gcc-arm-linux-gnueabihf`, `binutils-arm-linux-gnueabihf`, `libc6-dev-armhf-cross` (ARM runtime startup objects) and dependencies. No host package install, host sudo or privilege escalation.
- Checked-out source is mounted **read-only**, build results are written to the ephemeral runner temp directory. `contents: read`, pinned GitHub Actions revisions, no persisted checkout token, Docker default restricted capabilities with NET_RAW removed (APT needs UID/GID switching).
- `scripts/armv7-barrier-hil-a1.py` compiles `software/python/native/armv7_mmio_barrier.c` with `-march=armv7-a -marm -mfpu=vfpv3 -mfloat-abi=hard -O2 -fPIC -shared`, validates ELF32/little-endian/ARM/EABI5/v7/VFP registers/global symbol and exactly one `dmb sy` instruction within `plasma_mmio_dmb_sy`.
- On PASS, each run uploads `libplasma_mmio_barrier.so`, `receipt.json`, `SHA256SUMS`, four readelf/objdump reports as GitHub Actions Artifact (14 days). Receipt records GitHub event SHA, source/library SHA256, compiler path/version, fixed OCI reference and archive snapshot. A missing artifact is a **hard failure**.
- The pinned environment constrains input provenance. **Bit-for-bit rebuild reproducibility is NOT asserted** without two observed clean-run binary hash matches; artifacts do not constitute a signed release or Z2 qualification.

## Acceptance and risk boundary

1. Host PR security contracts PASS, including mutations that would introduce self-hosted execution, unapproved actor/ref, SSH commands, unpinned image/snapshot, weakened read-only checkout, or skipped compilation.
2. The PR CI actually compiles and verifies ARMv7 ELF and uploads SHA256 evidence on GitHub-hosted.
3. After an explicit **Gate 2 merge**, the reviewed main workflow can be manually triggered for A1. This Gate 1 does not authorize SWPC/Z2 operations; there is no A2 Job here.
4. Compilation and `dmb sy` disassembly are **A1 Host PASS only**. They cannot establish executable native Z2 behavior, MMIO memory attributes, AXI posted-write completion or production SWD readiness. M1 remains **NO-GO**.

## A2 — future Z2 CPU-only run, not implemented here

Preserve the existing controlled design:

1. Select approved A1 GitHub artifact and verify run SHA/receipt/source/ELF SHA256, ABI and package dependencies.
2. Use a separately approved, authenticated Z2 operator/SSH route to validate the actual Z2 ARMv7 Linux environment and install the library only in a temporary, non-system directory.
3. Call `plasma_mmio_dmb_sy` in an isolated subprocess under an external timeout; inspect result, architecture, SHA256, relevant dynamic dependencies and signal/exit code. Do **not** open real MMIO/UIO, touch FPGA Manager, power, reset, I/O or DUT.
4. Report true A2 PASS/FAIL/NOT RUN; separate HIL-B remains necessary for PS7/AXI memory-ordering and FPGA qualification.

This PR does not create A2 transfer scripts, Z2 jobs, credentials, SSH endpoints, bitstreams or privileged access. Issue #1026/#1029 remain deferred.

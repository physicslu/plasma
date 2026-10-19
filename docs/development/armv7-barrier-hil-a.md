# PLASMA HIL-A — ARMv7 Native Barrier, SWPC A1 / Z2 A2

**State: Gate 1 implementation candidate. Host-only acceptance; no SWPC or Z2 execution. M1 NO-GO.**

## Objective and boundary

The Fixed ABI Site 1 controller requires a qualified write_barrier() between eight setup register writes and COMMAND. The merged source at software/python/native/armv7_mmio_barrier.c implements an ARMv7-A `dmb sy` candidate, but GitHub-hosted x86 tests cannot prove a compiled ARMv7 shared library or its behavior on the Z2. This experiment isolates that question from PS7/AXI/PL tests and real target programming.

HIL-A is explicitly divided into **A1 (SWPC compilation and static ELF proof)** and **A2 (future Z2 CPU-only execution)**. A successful A1 must **never** be called ARMv7 live execution. A successful A2 must **never** be called MMIO Ordering or physical SWD qualification.

## A1 — fixed Workflow, reusable manual runs

Workflow: `.github/workflows/plasma-armv7-barrier-hil-a.yml`.

- Only `workflow_dispatch`, on `refs/heads/main`, by GitHub actor `physicslu`; no PR/push/issue_comment trigger.
- Hosted authorization job runs first. Self-hosted A1 runs only after authorization on `[self-hosted, linux, x64, plasma-integration]` and verifies actual Runner Name `SWPC-plasma-ci`, hostname `SWPC`, non-root Linux user `plasma-ci`, no SSH agent, reviewed Git commit.
- Checkout is exactly GitHub event SHA, with `persist-credentials: false`. No shell payload input, unreviewed PR checkout, artifact download, SSH, FPGA, `sudo`, real /dev/mem, real /dev/uio or Z2 instruction execution.
- `scripts/armv7-barrier-hil-a1.py build` invokes the installed ARM hard-float cross-tools with fixed argv, without `shell=True`:
  - `arm-linux-gnueabihf-gcc -march=armv7-a -marm -mfpu=vfpv3 -mfloat-abi=hard -O2 -fPIC -shared -Wl,-z,relro -Wl,-z,now -o <runner-temp>/libplasma_mmio_barrier.so software/python/native/armv7_mmio_barrier.c`
  - `arm-linux-gnueabihf-readelf -h/-A/-Ws` and `arm-linux-gnueabihf-objdump -d --disassemble=plasma_mmio_dmb_sy`
- Verify ELF32, little-endian, ARM, EABI5, ARMv7 attributes, hard-float calling convention, defined globally exported barrier symbol, and exactly one `dmb sy` inside that function; reject missing/mismatched ABI and unexpected call/trap.
- Save `receipt.json` with main SHA, source SHA256, ELF SHA256, compiler triplet/version, absolute compiler paths and inspection hashes. Output directory is a child of GitHub Runner TEMP. Always mark Z2, real MMIO, FPGA and DUT as NOT_RUN.
- Upload bounded logs/ELF/receipt as a 14-day GitHub Artifact. A workflow Run is **one execution**; the YAML stays versioned for later dispatch.

**A1 acceptance:** one explicitly authorized run on actual SWPC Runner reports PASS, demonstrates real ARM cross tool versions and accepted ELF/disassembly hashes; evidence corresponds to the exact main SHA. Cross-compiler availability/licensing/environment **not yet observed**. A1 currently NOT_RUN.

## Host-only CI / pre-merge safety

Workflow: `.github/workflows/plasma-armv7-barrier-hil-a-contract.yml`; triggers only on PR changes and always uses GitHub-hosted Ubuntu, never the self-hosted Runner.

- Static executable-policy guard validates trigger, owner/main, trust boundary, runner identity, pinning, absence of a Z2 job, and read-only GitHub credentials.
- Synthetic ELF/disassembly negative tests exercise missing `dmb sy`, wrong instruction variant, wrong architecture, wrong hard-float ABI, undefined symbol, extra calls and branch changes.
- Negative workflow mutation tests reject changes that weaken actor/ref/runner constraints, add PR/push triggers, add a Z2 job, or redirect PR tests to SWPC.
- `python3 -m py_compile` validates source syntax. No ARM compiler or target is invoked in this CI.

## A2 — Z2 native CPU execution design ONLY (NOT IMPLEMENTED / NOT RUN)

A2 must be a separately designed, owner-scoped hardware execution stage. **No A2 job, SSH transfer, dynamic runner command, access token or Z2 endpoint is created by this PR.**

Proposed controlled sequence after approval and an explicit transport capability:

1. Pin the verified A1 `receipt.json`, exact main source SHA and ELF SHA256; verify the chosen artifact download/checkpoint against GitHub's immutable run metadata and independent SHA256. A digest proves file integrity, not authorization.
2. Verify Z2 identity, enrolled SSH trust, non-root OS user, and exact 32-bit little-endian ARMv7 environment; confirm Python 3.12.13 and required shared-library dependencies/loader compatibility; do not invent a Z2 IP or credentials.
3. Transfer the single digest-pinned shared library into a private, non-system temporary directory. Refuse symlinks and unexpected ELF dependencies. Do not overwrite installed Python/PL components.
4. On Z2, call the exported function via a minimal dedicated `ctypes` child process under a bounded external timeout. Check exit code, SHA256 before and after, CPU/ABI/OS metadata and repeatability, with failure reported FAIL (never guessed PASS). CPU-only execution requires no FPGA Manager, bitstream, Device Tree mutation, real MMIO or DUT.
5. Clean up temporary files and upload sanitized run receipt; log any observed failure honestly. Loss of SSH, timeout or abnormal signal are FAIL/INCOMPLETE, **not** evidence of a safe AXI barrier.

**A2 acceptance:** exact Z2 native CPU execution PASS with matching ELF hash and validated ABI, plus an explicit no-hardware-MMIO/no-FPGA/no-DUT audit. Even then PS7 → AXI order/completion is **not qualified**; that remains HIL-B after a physical Unified AXI bitstream has been approved and tested.

## Engineering risks and next decision

- SWPC `plasma-ci` Runner toolchain availability has not been proven for `arm-linux-gnueabihf-*`. Missing cross compiler should cause A1 FAIL with a concrete dependency, not installation or privilege escalation.
- GNU `dmb sy` confirms the compiler emitted a CPU instruction; it does not prove ARM/Linux Device memory mapping, posted AXI write completion, or that Python MMIO emitted 32-bit transactions.
- A2 execution and A1 manual dispatch are **not authorized by this Gate 1**. Do not run either before Gate 2 and a separately explicit execution authorization. No deployment, FPGA changes, device access, network hardware tests or changes to production MMIO Driver are included.
- Existing #1026 / #1029 BFM/VIP investigations remain deferred. M1 remains NO-GO.

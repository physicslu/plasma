# PLASMA P0 — Fixed ABI Site 1 native-word MMIO adapter

> **Host-only P0 candidate; not a board-level driver PASS.** M1 remains NO-GO.
> No SWPC, Vivado, Z2, hardware MMIO/UIO, FPGA Manager/reload, DUT or deployment.

## Shortest path, reusing the existing driver

The legacy SWD-05 LinuxMMIO already implements ARMv7 native aligned 32-bit memoryview('I') reads/writes, explicit register allowlists, cooperative Site lease ownership, and lifecycle management. Retain it, including the correction of the historical byte-store/SIGBUS issue.

The new FixedABISWDController (the production command-sequencing class for the fixed ABI) additionally requires write_barrier() between its eight setup writes and COMMAND. The native SiteMMIO lease does not expose that third method. This pilot adds an explicit word-port adapter for **Site 1 only**; current Unified RTL does not instantiate Sites 2–8.

## Deliverables and honest scope

- software/python/plasma_interfaces/fixed_abi_mmio_port.py: Fixed ABI Site1 aperture offsets match pl/verification/fixed_image_abi_v1_gate1.json; wraps an already-open, Site1-owned SiteMMIO; no implicit hardware open or reload.
- ARMv7DMBBarrier: explicit 32-bit little-endian ARMv7-A only, caller-selected absolute shared library with SHA256; no auto-loading, compiling or probing hardware.
- software/python/native/armv7_mmio_barrier.c: source of an ARMv7-A DMB SY compiler-clobber ordering primitive. **Its real ARM execution and placement in PS7 is NOT RUN**. DMB is not proof of posted-write completion, device-memory attributes, isolation, or immunity to SIGBUS/AXI Stall.
- Synthetic host_test_barrier injection is permitted **only** with a regular-file MMIO fixture; symbolic links and device nodes are explicitly refused.
- Existing FixedABISWDController is exercised in Host tests via the adapter. It must write setup registers, call the barrier, and only then write COMMAND. Barrier failures poison both controller/backend and forbid command launch or blind retry.
- Existing Cocotb Unified RTL regression remains separate; file-backed fake completion is not an RTL/DUT/real board PASS.

## Physical critical path (outside this Gate 1)

1. Build and validate a PS7 -> Unified 64-KiB AXI Site1 **actual** PYNQ-Z2 bitstream, pin/clock/reset constraints and recovery path. Existing base/MS01/LT02/SWD-03 images cannot be presumed to implement this ABI.
2. Qualify the ARMv7-A shared library on the exact target runtime: ELF digest, DMB disassembly, memory attributes and valid register transactions. Python Host CI cannot establish ARM device ordering or handle AXI Stall/SIGBUS.
3. Obtain a distinct **explicit Gate 1 hardware scope** before running live readback, writes, SWPC Vivado, Z2/PPU or DUT experiments. Start with known-valid read-only Identity and exact image identity. Maintain approved power/OE/NRST isolation and known-good restoration.
4. For the first STM32F103C8T6, prove external SWD IDCODE and safe voltage, then real Erase/Program/Readback Verify under an actual target algorithm. Internal virtual DPIDR is not this proof.
5. Wire the admitted physical Site1 programming engine to the existing PPU Job / Gateway / Control Station. Do not enable FPGAInterface on hardware until readiness and physical safety are qualified.

## Governance

This is a software/Host-only P0 integration increment. User requested P0 progress, not unsupervised real hardware execution. Continue to Gate 2 for merge of this PR, but **do not merge without separate approval**. Issue #1026 cocotbext-axi and #1029 AMD AXI VIP remain deferred; M1 remains NO-GO.

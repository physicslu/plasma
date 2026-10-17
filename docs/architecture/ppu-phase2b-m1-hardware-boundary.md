# PLASMA Phase 2B — Kernel / Bridge ownership and M1 isolation boundary

**Status: Gate 1 Host-only candidate; M1 Architecture Freeze = NO-GO.**
This assessment follows merged Phase 2A.3 (PR #994) and the **Proposed**
[ADR-0003](../adr/0003-runtime-fpga-driver-reconfiguration-boundary.md).
No live device operation, driver binding change, FPGA load, Kernel module or
PL control is authorized by this work.

## Immediate decision and falsifiable hypothesis

**Hypothesis to test on an explicitly approved future Z2 experiment:**
"Linux can change the PL image with PS→PL AXI masters quiesced, with
all old mappings excluded, electrical outputs safe and independent recovery
available, while SSH, network and Plasma Gateway remain alive."

**Current answer: NOT PROVEN.** UIO and per-Site software leases control
cooperating processes; they do not exclude users with other MMIO privileges
or Kernel/DMA traffic. A completed syscall, `fpga_manager/state=operating`,
an empty process snapshot, `flock`, a driver unbind or a bitstream SHA alone
cannot demonstrate bus drain or safe reconfiguration.

The [Zynq isolation review](zynq-fpga-manager-isolation-ownership-review.md)
records actual PYNQ-Z2 read-only observations: Linux
`6.6.10-xilinx-v2024.1-g3c0eca68c652`, bound
`zynq_fpga_manager` and `of-fpga-region`, a Fabric
`uio_pdrv_genirq` `map0` at `0x40000000` / `0x10000`,
**no registered FPGA Bridge**, and **no exact matching target Kernel
source + patch attestation**. The generic Xilinx v2024.1 driver sources
are a *reference*, not proof that this target binary uses the same locking,
AXI-reset, region or failure semantics.

## Enforced offline review (what this Gate 1 actually adds)

`pl/tools/runtime_fpga_m1_gate.py` takes existing Phase-1 inventory
**JSON** from `pl/tools/runtime_fpga_phase1.py`. It requires the
documented Z2 map0 topology, explicit read-only / not-authorized flags,
and nonempty boot/kernel/Manager/bridge observations. It classifies the
absence or mere presence of `fpga_bridge` sysfs entries without treating
either condition as actual bus isolation. Missing, mismatched or
"hardware-ready" inventory is rejected. No active `/sys`, `/proc`,
`/dev`, subprocess, network, MMIO or bitstream call is made.

```sh
python -m pl.tools.runtime_fpga_m1_gate --inventory path/to/sanitized-inventory.json
python -m pytest -q pl/tests/test_runtime_fpga_m1_gate.py pl/tests/test_runtime_fpga_phase1.py
```

A well-formed report always says `M1_NO_GO`,
`hardware_ready=false`, `reload_authorized=false`. A malformed
record returns exit code 2 and the same denial, with no raw boot ID
or private endpoint echoed. This is an **offline diagnostic**, not a
credentials verifier, an attested source scanner, or a runtime permission
service. Do not connect this output to a hardware load authorization.

## Actual physical M1 blockers, in engineering order

| Gate | Evidence needed (not Host fixture booleans) | Present disposition |
| --- | --- | --- |
| K0 exact Kernel | Match deployed `vmlinux`/config/build provenance to the *specific* source tree + patches; inspect actual manager, region, bridge, UIO, DMA consumer paths | **UNKNOWN / NO-GO** |
| K1 exclusion | OS/device-node access boundary, all legal users, persistent UIO/de-vmem VMAs, kernel clients and DMA lifecycle; serialized mapping admission, not just a `/proc` scan | **NOT ENFORCED / NO-GO** |
| K2 PS–PL drain | Identify each AXI master/path and how pending writes/reads complete or fault safely *before* asserting PS–PL reset or level shifters; prove on exact Kernel/board | **UNPROVEN / NO-GO** |
| K3 external IO | Independent DUT socket safe-state for power/OE/reset, clock/reset and electrical behavior during PL transition | **NOT QUALIFIED / NO-GO** |
| K4 recovery | External recovery operator and independent UART/SSH/power observer, including unresponsive AXI/Kernel cases; no blind retry | **NOT QUALIFIED / NO-GO** |
| K5 image / ABI | Real v1 RTL + signed/hashed source/BIT/HWH/BIN, image A/B compatibility, independent register identity and baseline restoration | **NOT IMPLEMENTED / NO-GO** |

A registered bridge would remove the **inventory absence** fact, but
not K2 without *independent* evidence of isolation/drain under stress.
The Manager firmware sysfs path and FPGA Region path are not equivalent:
the latter's bridge list cannot be credited to a direct Manager load.
A printed source revision prefix or SHA-256 of a local file is not
source-to-target-binary reproducibility.

## Shortest safe next experiment — separate bounded Gate 1

1. **Read-only source/binding reconciliation:** obtain actual deployed
   Kernel build provenance/patches or a defensible binary behavior review;
   fresh board boot ID, FPGA Manager/Region/Bridge symlinks, relevant
   Device Tree properties, UIO map and declared IRQ/DMA consumers.
   Capture command result classes with sanitized hashes and current boot;
   do **not** infer live exclusive ownership.
2. **Choose a concrete exclusion design:** compare UIO + a single privileged
   broker (cooperating writers only) with a purpose-built Kernel driver for
   non-cooperating access control. Require a plan for DMA clients and
   retained mappings before choosing. UIO alone cannot make an all-process
   hardware ownership guarantee.
3. **Review PS–PL physical isolation and external safe-state:** list the
   exact Zynq-7000 reset/shifter/AXI paths and measurable pass/fail
   observables. Prepare a specifically scoped HIL plan with independent
   recovery and no speculative MMIO offsets.
4. **Only with separate explicit hardware scope**, execute controlled
   load/isolation/recovery proof on approved known-good images. Unknown AXI
   progress, external IO state or boot/source ownership means STOP; do
   not assume Python timeouts can abort hung Kernel/bus transactions.

**Architectural alternative:** reduce or eliminate risky full reloads via
one fixed FPGA image with generic SWD/SPI/JTAG-like engines and software
algorithm changes. This may be a faster product path if measured capacity,
timing and protocol coverage are sufficient. Reconfiguration capability is
not intrinsically a product requirement; switching target protocols without
reboot is the requirement. Benchmark the fixed-image route before investing
in complex reload isolation.

## Gate policy

This PR is **Gate 1 implementation + Host-only verification**, with a
separately approved Gate 2 required for merge. No work in PR #972.
No real FPGA Manager write, Driver unbind/rebind, bridge, /dev/uio*,
 /dev/mem, USB Hub, LA, DUT, Z2 operation, bitstream reload or deployment.
A Host CI green check is **not** M1 hardware acceptance.

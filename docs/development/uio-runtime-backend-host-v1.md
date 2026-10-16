# PLASMA UIO Runtime Backend — Phase 2A Host-only Candidate

> **Status: Implemented and CI-qualified on synthetic Linux sysfs/regular files ONLY.**
> Never use this work as authorization to open a real `/dev/uioX`, unbind a device,
> reload FPGA, perform MMIO against Z2, or run HIL-B/C.
>
> References: [ADR-0003 Proposed](../adr/0003-runtime-fpga-driver-reconfiguration-boundary.md);
> [Zynq ownership review](../architecture/zynq-fpga-manager-isolation-ownership-review.md);
> [Hardware ABI v1 Proposed](../architecture/runtime-fpga-hardware-abi-v1.md).

## What this actually implements

- `software/python/plasma_interfaces/uio_backend.py` provides `UIOPin`,
  `UIOBackend` and `UIOSiteLease`; this new Python module is separate from
  the existing production `LinuxMMIO`, which remains untouched.
- Accepts an **exact reviewed** `uioN` name, UIO label, platform-device basename,
  bound driver basename, `mapN` index, physical base, size and UIO page offset.
  Every opening and access checks these against read-only synthetic sysfs.
  A missing/changed map or competing UIO overlap is rejected, not guessed.
- Host-only ordinary-file fixture is mandatory. A symbolic link, character
  device or `/dev/...` device path is refused **before opening it**. Physical
  `/dev/uioX` remains unusable; there is intentionally no live enable flag.
- Actual UIO `mmap` offset is **`N * PAGE_SIZE`**, not the AXI physical
  address. The exact mapped word index is
  `(map.offset + address - map.addr) / 4`. Requested Site apertures must
  be wholly contained in one approved map. A future per-Site UIO topology
  needs separate owner/DT design; **only one UIO device is supported here**.
- The backend never exposes an unrestricted parent `read32/write32`:
  operations require a live, non-transferable one-Site lease and each
  register's immutable RO/WO allowlist. Uses native `memoryview(...).cast("I")`
  and 32-bit aligned accesses; never `struct.pack_into`.
- Explicit `open()` acquires the **same advisory file lock** as `LinuxMMIO`.
  Site leases are unique by Site number **and** aperture, with a short RLock
  across a single u32 access. A Supervisor-supplied generation is captured
  in each lease. Final `close()` and `quiesce_for_reload()` invalidate all
  leases and retire the instance permanently. The in-process generation
  increments on retirement; a global monotonic image-generation authority
  **is not implemented** by this module.
- A failed map/read/write or changed sysfs binding poisons the backend:
  further operations fail, and no replay or implicit recovery is performed.
  `MMIOStats` counts only Python operations that returned successfully,
  **not** independently observed AXI bus acceptance.
- The existing `SWDTransactionDriver` can use a `UIOSiteLease` through
  its injected `WordMMIO` contract. This Host file-backed integration
  **does not** make the proposed Hardware ABI v1 present in RTL.

## Example — ordinary-file test fixture only

```python
from pathlib import Path
from plasma_interfaces.linux_mmio import MMIOAperture
from plasma_interfaces.uio_backend import UIOBackend, UIOPin

pin = UIOPin(
    device_name="uio3", label="fabric",
    platform_device="40000000.fabric", driver="uio_pdrv_genirq",
    map_index=0, physical_base=0x40000000, size=0x10000,
)
site1 = MMIOAperture(base=0x40004000,
                     readable=frozenset({0x00, 0x04}),
                     writable=frozenset({0x04}))
# /tmp/fake-sys must contain a synthetic UIO sysfs device, plus matching
# 'device' and 'device/driver' symlinks. The mock is a REGULAR FILE.
with UIOBackend(pin, (site1,),
                sysroot=Path("/tmp/fake-sys"),
                device_file=Path("/tmp/ordinary-uio-simulation"),
                owner_lock=Path("/tmp/plasma-mmio-simulation.lock"),
                generation=1, readonly=False) as backend:
    with backend.claim_site(1, site1.base) as port:
        port.write32(site1.base + 0x04, 7)
```

Do **not** change `device_file` to `/dev/uio0`: Phase 2A explicitly refuses
real device nodes. A proper live UIO adapter is a **later Gate 1 phase** after
M1 prerequisites and explicit real Z2 risk acceptance.

## Host acceptance

```bash
python3 -m pytest -q software/python/tests/test_uio_backend_host.py
python3 -m pytest -q software/python/tests/test_linux_mmio.py
```

The Phase 2A CI executes the above tests with ordinary files and synthetic
`/sys/class/uio` trees only. Required fault cases: wrong pin, driver/binding
drift, deleted map fields, competing partial overlap, map2 selector and page
offset, duplicate claim, RO/WO policy, 2-/8-Site synthetic concurrency, fork
PID mismatch, lock conflict with legacy DevMem, failed mmap poisoning, and
retired generation/lease reuse rejection.

## What it does NOT establish

1. **UIO is not an ownership firewall.** `flock` is advisory and Site leases
   are process-local. A privileged, noncooperating process or Kernel DMA can
   still race a one-time audit. The FPGA Configuration Owner and live
   ownership arbitration are outside this module.
2. **Neither file-backed mmap nor Python can guarantee recovery from a real
   AXI stall/SIGBUS.** ARMv7 native memoryview width/device barriers and
   actual UIO map IO remain unqualified.
3. Does not instantiate a real map, manage interrupts, DMA, FPGA Manager,
   Bridge, FCLK, DT, bitstream/receipt, PPU power/reset or Gateway status.
4. The current `base.bin`, LT02, and MS01 Images **do not implement**
   proposed Hardware ABI v1. Eight synthetic Site loops do not prove eight
   FPGA physical Sites or Zynq-7010 utilization/timing.
5. Does not change the current `SiteConfig` per-Site target/interface
   contract; same exact IC per PPU batch is a separate admission migration.
6. **M1 remains NO-GO.** Matching target Kernel source provenance, physical
   PS–PL AXI isolation/drain and B1 real handoff remain unqualified.
   Neither Host PASS nor merging this code removes those blockers.

## Next stage / qualification contract

- Review exact Kernel source/DT and physical bridge/SLCR conditions; produce
  independent external recovery and board/electrical safe-state procedure.
- Review whether an independent Kernel-issued owner lock or custom driver is
  required to exclude non-cooperating software.
- Obtain separately approved scope before enabling a real UIO character
  device, performing actual identity readback or HIL; never expose an
  `allow_live=True` shortcut solely because the fake-sysfs tests passed.

Reference: [Linux 6.6 UIO HOWTO](https://docs.kernel.org/6.6/driver-api/uio-howto.html)
(`mapN` selector and `offset` semantics).

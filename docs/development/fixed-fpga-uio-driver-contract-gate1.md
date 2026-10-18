# PLASMA Fixed Image v1 — Linux UIO Driver Design Contract (Gate 1)

**Status: architecture proposal + offline Host contract ONLY; M1 NO-GO.**
**Do NOT open real `/dev/uio*`, `/dev/mem`, run target MMIO, unbind Kernel drivers, reboot, load FPGA, deploy, or infer physical qualification.**
Canonical ABI candidate: [fixed-fpga-hardware-abi-v1-gate1.md](../architecture/fixed-fpga-hardware-abi-v1-gate1.md).
Current implementation [`uio_backend.py`](../../software/python/plasma_interfaces/uio_backend.py) intentionally supports regular-file fixtures only. The corresponding real-device adapter is **not built by Gate 1**.

## Choice and limitations

A single PPU-wide **UIO `map0`** covering the reviewed 64-KiB candidate window is the recommended first implementation path for the Zynq-7020 fixed image. The product SHALL not assume a fixed UIO ordinal or absolute AXI address in business logic. A purpose-built Kernel driver remains an alternative if required hardware arbitration, DMA/IRQ or independently enforceable permissions cannot be proved with a single privileged broker.

**UIO does not enforce Site or even process-global isolation.** User-space `flock`, `RLock`, a Site token or a one-time /proc scan cannot exclude a privileged noncooperating mapping, a retained VMA, Kernel-IP access or DMA. In fixed-image v1, disable **all normal runtime FPGA reload paths**, greatly reducing a major hazard, but still control live MMIO ownership and external DUT IO.

## Board Descriptor and exact discovery

Approved descriptor fields: exact Board/PL image artifact identity, full source and manifest digest, expected FPGA `magic/ABI/build/image`, approved PPU window physical base and size, UIO *label*, platform-device identity, driver binding, `map_index`, `map.addr`, `map.size`, `map.offset`, byte order and access policy. Absence or ambiguity is a refusal, not discovery by best guess. A DEV build may use lab-specific pinned descriptor; do not silently ship its address to a product board.

The broker may enumerate read-only `/sys/class/uio/uio*/maps/mapN` and follow bounded symlinks to device and driver. It matches **uniquely by reviewed Resource/Binding properties**, not `/dev/uio0`. Issue #1004 actually observed `uio1` after historical `uio0` with unchanged physical `0x40000000 / 0x10000`; this is why `uioN` ordinal is not stable identity.

If a second UIO resource overlaps the selected physical window, any resource field changes, device identity is ambiguous, a sysfs read fails, or selected maps change between discovery and opening: **fail closed**. A re-read reduces time-of-check/time-of-use exposure but does **not** prove exclusive OS ownership. Revalidate after permission/udev or hot changes; a real adaptation needs explicit Kernel resource and open-file identity checks.

For an actual UIO map `mmap(fd, offset=map_index * PAGE_SIZE)` chooses mapN; it is **not** an AXI physical byte address. Register byte index from map is `sysfs_map.offset + (register_physical_addr - map.addr)`. Check overflow, containment, page-alignment and native 32-bit boundaries before any access. The Host checker `select_uio_resource()` accepts synthetic descriptors only, never actual `/sys`.

## Runtime adapter obligations (future, separate Gate 1)

- Only the dedicated PPU Hardware Broker service account can open the device. Gateway and worker processes receive **semantic IPC**, never file descriptors, `/dev/mem`, MMIO addresses, `mmap` or FPGA Manager credentials.
- On `open`: exact Board/Image/Boot/Device Tree resource admission, UIO uniqueness, exclusive authorized process identity, binding/permission policy, image Identity readback and mapped generation verification. If *any* element is UNKNOWN, do not issue writes. Hold broker ownership for the entire PPU runtime.
- Device uses little-endian 32-bit naturally aligned loads/stores; match memory attributes/order on actual ARMv7. Native `memoryview.cast("I")` was qualified on one development path, **not** automatically through every UIO memory mapping. Explicit barrier/ordering semantics and strict RTL register access widths must be independently qualified.
- Pin register reads/writes against machine-reviewed immutable `ro/wo` offsets. No read-modify-write of `WO`; never probe reserved offsets or invalid AXI addresses. Support a single PPU-level mapped window and per-Site subwindows; do not expose an unguarded global parent MMIO read/write route.
- Failures: reject changing resource identity, unexpected disappearance, stale generation, forked broker owner, retry after ambiguous write, incorrect DONE_SEQ, orphan Site Job, double ACK, or wrong protocol capability. Don't pretend a Python exception can catch a hung AXI transaction. A child process crash does not certify the shared bus was released.
- Require external Site Safe-Off/NRST/OE control outside configurable PL; no voltage, power, reset operation is implemented or authorized in this Gate.
- `FPGA Manager` operations **not part of normal runtime**. Operational image replacement is a separate maintenance workflow (quiesced, qualified, signed, approved) and not exposed via REST/Job/Worker.
- Product implementation: privilege hardening, crash reconciliation, independent recovery runbook and noncooperating consumer policy. Kernel-driver alternative remains GO if these cannot be enforced.

## Versioned interface / acceptance

`HardwareBroker.open(board_descriptor)` -> read-only identity/admission receipt;
`claim_site(site_id, batch_exact_ic, generation, epoch)` -> Site transaction capability;
`execute_site_command(lease, protocol, opcode, bounded_params, payload)` -> sequence-scoped completion;
`release_site(lease)`; `seal_new_admissions(reason)`; `fault_site(site_id, evidence)`; `close()`.
These signatures are **design-only**, not shipped HTTP endpoints or an implemented real driver.

For host-only proving, run `pl/tools/fixed_image_abi_contract.py` and `pl/tests/test_fixed_image_abi_contract.py`; additionally retain existing UIO and ownership synthetic regression. No test result licenses the real char-device adapter.

Acceptance for later hardware work: exact verified Z2 image/ABI + independent readback; live UIO map open without Kernel conflict under approved engineering setup; safe aligned read-only Identity; permitted per-Site bounded read/write; fork/crash/close/mapping-generation rejection; independent observe SSH/Gateway recovery and source/image provenance. First authorized live work requires a **new scoped Gate 1**.

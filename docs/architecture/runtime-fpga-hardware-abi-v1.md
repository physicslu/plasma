# PLASMA Proposed Runtime FPGA Hardware ABI v1

> **Status: Proposed / Phase 1 host-only contract. NOT frozen, NOT present in existing PYNQ Base, LT02, MS01, or an approved product FPGA image.**
>
> Scope: PPU-level discovery, image compatibility and independent Site discovery. The **data-plane command/FIFO/IRQ/DMA** registers are intentionally **not** defined here. Source of machine-checkable candidate layout: [`runtime_fpga_abi_v1_proposal.json`](../../pl/verification/runtime_fpga_abi_v1_proposal.json). Review with [ADR-0003](../adr/0003-runtime-fpga-driver-reconfiguration-boundary.md).

## 1. Why a fixed hardware ABI

The Linux Runtime Driver must not depend on every IC algorithm or special Bitstream having its own arbitrary AXI address table. A future two-image A/B HIL must be able to:

1. Select an approved, signed/hashed candidate by requested protocol *capability* (not by unverified file name).
2. Quiesce all Site operations and close all relevant mapped resources.
3. Reload PL using the proper FPGA Manager/Bridge path with Linux still running.
4. Re-discover a common read-only Identity/Capability ABI **before** opening any writable Site data-path register.
5. Recreate leases, mapping generation and Site workers for the new Image; reject old handles and outstanding jobs.
6. Fail closed or restore the known-good prior Image when identity/ABI/load/readback diverge.

**ABI compatibility is necessary but not sufficient**: a compatible register layout does not prove a safe PS↔PL transition, electrical state, or valid new image digest. PPU operation requires separate FPGA Manager receipt, boot identity, all owner reconciliation, Clock/Reset health, and Board Supervisor policy.

## 2. Memory model (candidate Z2/Zynq-7000 address layout)

~~~text
Phys base 0x4000_0000  [64 KiB PPU candidate Window; not current product truth]
          +0x0000    [Identity + Capability | 4KiB]
          +0x1000    [PPU control RESERVED | 4KiB]
          +0x2000    [Shared engine 0 RESERVED | 4KiB]
          +0x3000    [Shared engine 1 RESERVED | 4KiB]
          +0x4000    [Site 1 | 4KiB]
          +0x5000    [Site 2 | 4KiB]
                 ...
          +0xB000    [Site 8 | 4KiB]
          +0xC000–FFF [RESERVED]
~~~

Formula (candidate): `site_base(n) = ppu_base + 0x4000 + (n-1)*0x1000` for `1 ≤ n ≤ 8`. Capacity 8 is **not** proof of eight physical Sites; only enumerated `site_present_bitmap` plus Image/Board verification permits runtime admission.

The exact physical base, 64-KiB resource ownership and map composition are **not yet frozen** for the eventual MYIR Zynq-7010 board. A Driver implementation should receive the registered physical Resource/Board Descriptor, not hard-code the Z2 address in business logic.

**UIO distinction:** if `/dev/uioX` presents one 64-KiB `map0`, the `mmap` file offset is **0**, and a Site's location is an offset within this mapping. If UIO exposes multiple mapN entries, file offset is `N*PAGE_SIZE`, and `mapN/addr,size,offset` must be checked. A UIO map selector is **not** a PL physical address. Source: [Linux UIO HOWTO](https://docs.kernel.org/driver-api/uio-howto.html).

## 3. Proposed read-only Identity (all little-endian aligned u32)

| Byte offset | Name | Proposal / semantics |
| --- | --- | --- |
| `+0x000` | `magic` | `0x4D534C50` (little-endian bytes `PLSM`); candidate, **not implemented** |
| `+0x004` | `abi_version` | `major:u16 << 16 | minor:u16`; Major = 1; incompatible Major => no writable access |
| `+0x008..+0x014` | `image_id_w0..w3` | Four u32 words identifying logical Image variant; byte/word assembly convention to be frozen |
| `+0x018..+0x024` | `build_id_w0..w3` | 128-bit diagnostic build identity; **not** a substitute for full SHA256 artifact provenance |
| `+0x028` | `capabilities_lo` | Low 32-bit image Capability bitmap; bit definitions pending |
| `+0x02C` | `capabilities_hi` | High 32-bit bitmap |
| `+0x030` | `site_present_bitmap` | Bit (Site ID−1) = physical Site declared by *this image*; also verify actual Board topology |
| `+0x034` | `site_ready_bitmap` | Bit (Site ID−1) = local Site Ready; no admission until global/Image proof succeeds |
| `+0x038` | `ppu_status` | Firmware status word; bit definition pending; read-only observation is not hardware isolation |
| `+0x03C` | `hardware_revision` | Board/implementation revision candidate; encoding pending |

The readonly identity fields should be stable between authorized FPGA reloads and must return valid response for all reviewed images, before **any** command, reset, power, or DUT operation. No speculative MMIO reads at reserved offsets. A load receipt and confirmed manifest supply authoritative Image SHA and expected register values.

## 4. Proposed Site discovery block (4 KiB per physical Site)

| Offset | Name | Access | Note |
| --- | --- | --- | --- |
| `+0x000` | `site_id` | RO | One-based site number matching computed slot |
| `+0x004` | `site_abi_version` | RO | Site ABI Major/Minor; mismatched Major refuses admission |
| `+0x008` | `site_capabilities` | RO | Per-site capability subset, bitmap assignments TBD |
| `+0x00C` | `site_status` | RO | Site running/error/idle semantics TBD |
| `+0x010` | `site_error` | RO | Error decoding TBD |

**No Site command, data-buffer, per-DUT power, or timing register is authorized or specified by this document.** Future evolution requires distinct register-level contracts, exact read/write allowlists, safe state diagrams and native ARMv7 HIL. 'Reserved' slots must never be accessed just to detect a device.

## 5. Version and mapping transition

| Condition | Software behavior |
| --- | --- |
| Unknown / missing magic | Refuse hardware access; status `INCOMPATIBLE_IMAGE` |
| ABI Major mismatch | Refuse runtime MMIO write; require matching software/Image |
| Newer compatible Minor | Permit only registered offsets/fields understood by software; no guessing |
| Site count/site ID mismatch | Refuse Site admission; preserve PPU fault evidence |
| Capability missing | Refuse selected protocol or choose approved compatible Image with **quiesced runtime switching** |
| Image file, hash, receipt or actual register readback mismatch | Refuse programming; supervisor recovery/FAULT |
| Same ABI but driver mapping changed unexpectedly | Refuse; new Device Tree / Kernel resource review required |
| Reload while Site Busy | Refuse until *all* Sites quiesce; no software timeouts assumed to solve AXI stall |

`abi_version` is a **register contract version**, not Plasma Protocol v3.3, catalog ADR-0002 Levels, Job Profile Revision, Site Desired Version, Linux UIO driver version, or firmware semantic release version.

## 6. Current-to-proposed migration gaps (explicit)

- Current `main` `LinuxMMIO` uses `/dev/mem` with SWD-03/loopback-specific address allowlists. `FPGAInterface` is not yet wired. No UIOBackend or product hardware ABI v1 exists.
- PR #972 MS01 maps Identity/Control/SWD/Transaction/LT02_0/LT02_1 to six 4-KiB apertures at `0x40000000..0x40005FFF`. **Matching window addresses do not imply matching register semantics**; the LT02 Site ID registers and ABI above are **not implemented in that image**.
- `site_count` and `max_supported_sites` are different: a PS-only PPU with no real Site is valid. Identity Site presence must not invent physical Sites.
- Existing `docs/architecture/ppu-site-configuration.md` lets each Site specify `target/interface` Desired; the new same-exact-IC-per-batch requirement is **not enforced**. It must be resolved with an explicit PPU Batch Profile admission policy while allowing unique per-site serial/payload content. Avoid incorrectly declaring current Site settings impossible.
- Existing `base.bin` is a PYNQ overlay used for **known-good recovery** in development; it does not implement PLASMA v1 ABI and is not an intended production workload image.
- Safety-critical DUT power/enable/reset requires out-of-PL stable control, to be reviewed with actual socket design; Site status alone cannot enforce safe switching.

## 7. Phase 1 acceptance and prerequisites for M1

- [ ] ABI document and JSON proposal are structurally consistent (host-only tests).
- [ ] Real Z2 read-only UIO/kernel/FPGA Manager inventory, boot ID, Device Tree/bridge facts obtained via separately authorized on-board read-only inspection (NOT yet collected by this PR).
- [ ] UIO mapN physical-range translation, offset checks and missing-resource behavior exercised on Host fake-sysfs.
- [ ] New Image A/B RTL and firmware evidence produced **after** ABI approval, not fabricated from existing MS01.
- [ ] Image-change interlocks and rollback independently reviewed before live Phase 2–4 HIL.
- [ ] Separate Gate 2 merges any approved PR; M1 Architecture Freeze requires an owner-reviewed engineering decision, not just a merged Proposed ADR.

**Verdict now:** Proposed, Host-only. Do not promote to `Current` or claim FPGA HIL PASS.

# MMIO-LT-02 — PS ↔ PL AXI4-Lite Loopback v1

Status: implementation candidate. **Not** a qualified FPGA bitstream, Z2 HIL result, PL diagnostic API, or deployed UI feature.

## Scope and architecture

The production `LinuxMMIO` backend performs aligned native 32-bit accesses on ARMv7. A **new** PL loopback scratchpad receives those exact writes, returns independently stored words on read, and counts successfully admitted DATA writes and reads:

```
Control Station / existing Engineering Loopback Test UI (PL disabled until proven)
   -> Manager bounded relay -> PPU Gateway -> Plasma Server
   -> (future PL loopback endpoint adapter) -> LoopTestDriver
   -> production LinuxMMIO -> PS GP0 AXI4-Lite -> new LT02 RTL
```

The currently merged SWD-03 four-aperture internal DPIDR fixture is unchanged and **does not contain this new block**. A separate five-aperture Z2 source/build candidate now exists at [z2-lt02-axi](../../pl/projects/z2-lt02-axi/README.md); it still requires an actual Vivado implementation, handoff and verified Bitstream before HIL. Do not use the old SWD-03 FPGA image receipt or claimed Build ID to authorize a new image. This initial integration includes no Z2 load, service deployment, real MCU, external PL I/O, or IC programming.

The existing `software/web/app/engineering/loopback-test.tsx` already owns the eight deterministic patterns, lengths, repeat/delay and CRC display. Do not create another page or accidentally enable the PL selector. PL becomes enabled only after an actual PPU PL service with hardware-source proof, Manager allowlist, Gateway, Server, and browser response validation exists. PS-only loopback must remain untouched.

## Hardware contract: dedicated 4 KiB aperture

Candidate reference physical base: `0x40004000` (final address from Vivado HWH/manifest). This is **Site 1 only**, not eight physical channels. Register access is 32-bit, 4-byte-aligned and little-endian at the native ARMv7 boundary; invalid/unimplemented offsets reject with AXI `SLVERR` (simulation only: never deliberately access illegal physical AXI addresses).

| Offset | Access | Reset | Meaning |
|---|---|---|---|
| `0x000` | RO | `0x4C543032` | Magic: LT02 |
| `0x004` | RO | `0x00010000` | ABI v1.0 |
| `0x008` | RO | `0x00000001` | Capabilities bit 0: 2 KiB scratchpad + physical counters |
| `0x00C` | RO | `2048` | Capacity in bytes |
| `0x010` | WO | — | Command bit 0: clear DATA counters only; no writes to other bits |
| `0x014` | RO | `1` | Status bit 0: ready; no implied firmware/DUT qualification |
| `0x018` | RO | `0` | DATA write count, mod 2^32 |
| `0x01C` | RO | `0` | DATA read count, mod 2^32 |
| `0x100..0x8FC` | RW | unspecified | 512 × 32-bit words; WSTRB lanes merge |

All other offsets are invalid. Data memory is intentionally **not reset/initialized**; the producer must write before it reads. A DATA write/read is counted once per accepted AXI transaction, not once per byte/lane. Command clear resets counters only, not scratchpad. The normal Python driver never clears counters, because clearing loses concurrent evidence. A concurrent unrelated MMIO accessor must be excluded by the production lease and PL ownership check. Counters are **evidence of access**, not cryptographic proof or protection against malicious code.

If AXI AW and W arrive on different cycles, the slave must wait for both. BVALID/RVALID remain asserted until BREADY/RREADY; backpressure and WSTRB partial-write semantics are mandatory Cocotb checks. A simultaneous read and write of the same memory address may yield the old word; the driver serializes all data writes before reads. Wraparound counters are compared modulo 2^32.

## Software contract

- `LoopTestDriver` accepts an injected `read32(addr)`/`write32(addr,value)` Site-owned port and an explicit, aligned base; it **never opens /dev/mem** by itself.
- Exact Magic, ABI, Capability and Depth are verified before any writes.
- Payload is bytes (1..1 MiB per case); split into chunks of up to 2048 bytes.
- Each chunk: snapshot counters, write ceil(length/4) padded little-endian words, read back the same number of words, validate exact bytes after truncation, then require DATA write/read counters to advance by exactly that number.
- Partial final words are padded with zero bytes, and the *original byte count* is authoritative; no implicit extra bytes in the echoed payload.
- A mismatch or counter error fails immediately. Never retry a possibly completed write.
- Emit bytes, chunk count, word counts, elapsed PS-side nanoseconds, TX/RX CRC32 and payload bytes to the higher-level diagnostic transport. **Browser/Manager RTT is a separate metric**.
- Pattern generation, test-ID, sequence, CRC verification, request admission and inter-packet delay belong to the existing diagnostics stack, not FPGA/driver.
- The LinuxMMIO caller creates a precise `MMIOAperture` allowlist (only the above registers/window), holds exclusive ownership, and closes before FPGA reload. No fallback to a mock or synthetic PASS in the PL real path.

## Acceptance gates

| Gate | Required tests | Evidence boundary |
|---|---|---|
| LT02-01 | ABI text, documented allowed offsets and proof boundary | Source review |
| LT02-02 | Python fake-word-port: exact caps; 1/1023/1024/1025/2048/2049-byte and multi-chunk boundaries; payload mismatch; wrong ABI; short counter; reject empty/oversized | Host unit only |
| LT02-03 | Verilator lint + Icarus/Cocotb **actual RTL**: separated AW/W, backpressure, full/partial WSTRB, data window, counters, read-only/invalid SLVERR, reset | Host RTL only |
| LT02-04 | SWPC Vivado 2026.1: five-aperture GP0 HWH, synthesis, implementation, timing, no external PL I/O, BIT/HWH/manifest hashes | SWPC build only |
| LT02-05 | PYNQ-Z2 development HIL: independent fixture identity, correct FCLK, exact `LinuxMMIO` + `LoopTestDriver`, boundary bytes, repeat/long-running counts, supervised original image recovery | Real hardware |
| LT02-06 | PPU local PL diagnostic Gateway/Server, Manager bounded relay, UI PL selector, browser real-path CRC and endpoint/source proof, no fallback to PS or mock | Real stack/HIL |

**LT02-05 and LT02-06 are NOT RUN until built and actually tested.** Existing 2026-10-16 SWD-03 MMIO-13–15 Development Hardware Acceptance remains valid for its *own* four-aperture image but does not qualify LT02.

## LT02-05 host-only preflight candidate

A separate, inert [LT02 HIL P0 runbook](../../pl/hil/lt02/README.md)
and `pl.hil.lt02.preflight` check exact approved BIT/HWH/manifest/BIN and
known-good PYNQ recovery hashes, validate the five real HWH address segments
and ABI, and fail closed on missing read-only inventory/operator prerequisites.
The `pl.hil.lt02.cases` helper reuses the production Python
`LoopTestDriver` through an injected Site-owned word port; no test harness
opens real `/dev/mem` or loads the FPGA. P0 only verifies the *supplied*
evidence: it is not physical operator/UART/power attestation, and cannot
authorize Z2 loading, live MMIO or UI enablement.

LT02-HIL01, LT02-HIL02 and LT02-R0 remain NOT RUN until separately executed
and evidenced on the physical PYNQ-Z2 with supervised original restoration.

## Performance policy

Report `bytes / elapsed seconds` and operations/s as observed, not as AXI theoretical bandwidth. Establish a measurement baseline first; there is no arbitrary mandatory throughput threshold. Test a fixed seed and duration to compare revisions. A Python stopwatch does not isolate FPGA service time from Linux scheduling or AXI bridge overhead. No claim about signal-integrity, external SWD, DMA, multi-Site concurrency, or factory stress qualification.

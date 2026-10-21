# Fixed Image ABI v1 — SWD Semantic Convergence Gate 1

**Status: REVIEW CANDIDATE / Host-only simulation. M1 = NO-GO.**
Legacy SWD-03 remains unchanged. No real UIO/MMIO, bitstream, hardware,
FPGA reload, DUT operation, merge or deployment authorized.

## Candidate semantic decisions

1. **Line Reset:** COMMAND=2, BIT_COUNT=64, exactly 64 SWDIO-high SWCLK
   clocks. The existing master also performs 64 Hi-Z recovery clocks BEFORE
   this sequence and eight low-idle clocks AFTER; neither is counted.
   Values 50/63/65/128 are rejected. Variable length requires a future
   capability/revision rather than a pretend 50..128 implementation.
2. **CLOCK_DIV (offset 0x05C):** retained name; semantic meaning
   SWD half-period input FCLK cycles, integer 2..65535, ideal
   active fSWCLK = FCLK/(2*N). Device clock must come from a verified
   Board/Image descriptor; simulation does not prove actual hardware timing.
3. **Stable result codes:** OK=0, SWD_WAIT=1, SWD_FAULT=2,
   SWD_NO_ACK=3, PARITY=4, TIMEOUT=5, ABORTED=6,
   BAD_ARGUMENT=7, ENGINE_UNAVAILABLE=8, INTERNAL_FAULT=9,
   NEED_RESET=10, PHY_ERROR=11. Old SWD Master NEED_RESET=2 must
   map to v1 NEED_RESET=10, not BAD_ARGUMENT. SWD legacy Master
   BAD_CONFIG=1 maps to BAD_ARGUMENT; its PHY_ERROR=9 maps to v1 11.
4. **SWD_RESPONSE_META, Site +0x06C (RO):** bits2:0 raw wire ACK
   (0 NONE,1 OK,2 WAIT,4 FAULT; preserve any invalid pattern),
   bit3 DATA_VALID, bits12:4 ATTEMPTS (u9), bits14:13 LINK_STATE
   (0 reset required,1 DPIDR required,2 connected), bits31:15 zero.
   **SWD_RAW_STATUS +0x070 (RO):** original SWD Master status
   0..9, diagnostic only; DONE_STATUS is the stable ABI enum.
5. **CAPACITY_WORDS:** zero when SPI FIFO is absent. SWD-only RTL
   advertises SWD capability only; no fake FIFO capacity or SPI.
6. **Sequence:** exactly one in-flight command per Site. COMMAND is
   written last after setup with a platform-qualified MMIO memory barrier
   (Host simulation has no actual ARM barrier). Never reuse sequence in
   the same owner epoch. RTL Site 1 rejects immediate replay; Host
   driver tracks all issued sequences and serializes coroutines.
7. **Completion:** hardware captures DONE_SEQ, DONE_STATUS, DONE_DATA,
   SWD_RESPONSE_META and SWD_RAW_STATUS at completion. Read immutable
   diagnostics, verify matching DONE_SEQ twice, then write matching
   ACK_SEQ. Invalid metadata or AXI failures poison the owner; no replay.
8. **Fault:** TIMEOUT/ABORT/PHY_ERROR latch Site FAULT. The matching
   ACK_SEQ consumes DONE-valid but **does not clear FAULT** or
   SITE_ERROR. No in-band recovery is implemented, and subsequent
   programming is refused until independent authorized recovery.
9. **Abort race:** write ABORT=1 accepted only when the actual SWD
   Master reports BUSY, not necessarily during wrapper launch_pending.
   SLVERR during the transition is ambiguous; never claim rollback.
   Accepted Abort likewise does not prove all target effects are undone.
10. **Timeout:** software poll expiration does not prove hardware
    stopped, an AXI read completed, or DUT power is safe. Poison the
    owner and require independent recovery before retry.

## Architecture boundary

This is an additive ABI candidate applied to all eight *logical*
Site windows; only standalone simulation Site 1 has RTL. No PPU
Global Identity implementation, SPI, multi-Site hardware, Device MMIO
qualification, Kernel/DT owner proof, external OE/Power/NRST circuitry
or FPGA image is included in this Gate.

Host CI requirements: machine-readable ABI validation, Cocotb virtual
DPIDR and timeout FAULT snapshot/ACK tests, negative register/timing
tests, concurrent Python Site command serialization, legacy SWD-03
regression and an independent Draft PR. All new evidence is Host-only;
M1 Architecture Freeze remains NO-GO.

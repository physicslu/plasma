# ADR-0005 — Direct-addressed independent SWD IP, optional guarded OpenOCD Bitbang debug

> **Status: Superseded by [ADR-0006](0006-independent-swd-engine-and-future-gpio-bus.md) (owner decision, 2026-10-27).**
> Historical decision retained for audit. Optional SWD Debug Bitbang is **NOT** the current implementation direction.
> This ADR is recorded on draft PR #1189; until merged, it is not an active main/deployed contract. The old MPE wrapper, RTL, AXI candidate and standalone MPE Vivado Tcl in that PR are **experimental migration source**, not approved final architecture or a qualified bitstream.
>
> **Design objective:** eliminate an unnecessary FPGA multi-Site management layer. Make each Site a separately addressable independent SWD AXI IP, while retaining an explicitly gated OpenOCD diagnostic Bitbang capability inside each IP.

## Decision and first-principles architecture

```text
Zynq PS Embedded Linux / OpenOCD
                 |
        PS7 M_AXI_GP0
                 |
       AXI Interconnect (routing ONLY)
          /               \
   SWD IP Site 1        SWD IP Site 2          -> scale to N Sites
   independent AXI      independent AXI
   CMD/RESP/FIFO        CMD/RESP/FIFO
   HW SWD FSM           HW SWD FSM
   guarded Debug BB     guarded Debug BB
          |                   |
  JA Y18/Y19 SWD       JB W14/Y14 SWD
```

- **No MPE central Site Manager, cross-Site SWD scheduler, shared SWCLK FSM or opaque wrapper ABI.** Each instanced SWD IP owns its register decode and command/response state, FIFO, SWCLK divider, SWDIO OE, transaction FSM, deadline, abort and mode; PS Driver selects Site via its AXI address. A standard AXI Interconnect routes bus accesses only. Do not duplicate PS/Linux Job scheduling in PL.
- **Site identity is one-based in software.** Candidate per-Site AXI windows: Site 1 `0x43C01000` (PMODA JA Y18/Y19) and Site 2 `0x43C02000` (PMODB JB W14/Y14), each 4 KiB; these addresses remain **proposed until actual Vivado HWH and PS7 address assignment**. Site 1, Site 2 can execute SWD concurrently without cross-Site global operational locks. N=8 is a future scalability target, not a physical feature of this board build.
- **Normal Mode: transaction-level hardware SWD.** PS-local OpenOCD/native adapter submits DP/AP/line reset/SWJ commands using per-Site registers and tagged FIFO. Each SWD IP handles SWCLK and bidirectional SWDIO hardware timing. The normal programming data path has no PS MMIO-per-edge bit toggling.
- **Debug Mode: guarded Controlled Bitbang per Site.** For electrical/protocol bring-up only, a separate PS-local, version-qualified UNIX-socket Bridge translates the supported OpenOCD `remote_bitbang` SWD operations into this **new** Site's dedicated diagnostic registers (SWCLK, SWDIO_OUT, SWDIO_OE, SWDIO_IN). This is not a second old GPIO/WordPort IP or a legacy driver import. Bitbang is slower and not qualified for product flash throughput.
- **Single physical-output owner per Site.** `NORMAL` and `DEBUG` are mutually exclusive and default to safe disabled. Mode acquisition needs Site idle, no inflight command or unconsumed completion, verified PS hardware lease, outputs quiesced and SWDIO Hi-Z, then explicit mode transition. Never allow the FSM and Bitbang register path to simultaneously drive SWCLK/SWDIO. On reset/disable/abort/session loss: SWCLK low when driven, SWDIO Hi-Z. No automatic fallback from failed Normal operation into Debug. No power/NRST/VPP permissions or voltage switching. JA signals are shared electrically with the Raspberry Pi header; no conflicting HAT/driver.
- **Ownership and safety remain in PS.** A Broker/owner lease may protect cross-process MMIO Image admission, Root Guard and Golden Recovery, but there is **no extra PL 'MPE manager'**. Real Target voltage, PS/Linux ARMv7 MMIO bus width/barriers, BIT/HWH/Manifest/provenance and hardware access require separate admission.
- **Build standard unchanged:** follow ADR-0004. New independent dual SWD IP Vivado Project, verifiable Tcl/XDC/BD/HWH, and only SHA-pinned Path 2 `operator-cli` for qualified SWPC Build. Build is NOT Deploy.

## OpenOCD version barrier — DO NOT silently claim SWD remote_bitbang on 0.12.0

**Verified source fact:** OpenOCD **v0.12.0** `src/jtag/drivers/remote_bitbang.c` registers `.transports = jtag_only` and lacks `swd_ops` and `swdio_drive/swd_write/swdio_read`. Therefore PLASMA's existing OpenOCD 0.12.0 `remote_bitbang` **cannot be treated as a SWD-capable Debug Bridge**. See upstream at:
- `https://github.com/openocd-org/openocd/blob/v0.12.0/src/jtag/drivers/remote_bitbang.c`
- `https://github.com/openocd-org/openocd/blob/v0.12.0/doc/manual/jtag/drivers/remote_bitbang.txt`

Upstream newer revisions implement SWD `remote_bitbang`, with ASCII commands `O/o` (output enable), `c` (read), `d/e/f/g` (SWCLK/SWDIO), and version-dependent sleep commands. See `https://github.com/openocd-org/openocd/blob/master/doc/manual/jtag/drivers/remote_bitbang.txt`. **Do not assume a local or pinned executable supports these commands from its name.**

**Release gate:** before enabling the new Debug Bridge, pin a specific OpenOCD source/build version (or explicitly reviewed backport), prove `remote_bitbang` SWD support by source inspection and actual host-side protocol tests, lock its CLI/transport behavior, test SWDIO direction/turnaround/no-contention, errors, disconnect and Mode lease safety, then run separately approved physical HIL. Do not silently upgrade the existing qualified OpenOCD 0.12.0 production Provider stack merely to enable diagnostics. Until verified, `DEBUG_REMOTE_BITBANG_SWD=BLOCKED_VERSION_UNQUALIFIED`.

### Gate 1 Host-only protocol reference (not release admission)

- Read-only source comparison pinned upstream OpenOCD `v0.12.0` tag `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c` (`remote_bitbang.c` blob `36bcbe19cac2c3d0c4c7c1f906a5db695a091478`): driver is `jtag_only`, no `.swd_ops`.
- Read-only newer upstream **commit reference**, not an installed release: `cb0c224e936091156ecf3025ba05657408ed64c8` (`remote_bitbang.c` blob `f3a107312531ddfd14d3f0906ad745d4cb5f4eca`) advertises `TRANSPORT_JTAG | TRANSPORT_SWD` and `.swd_ops = &bitbang_swd`. Protocol document blob `8316cb0dd53a8fcb5ca0d036d4821b751b1b1e87` defines `O/o` drive, `c` sample, `d/e/f/g` write, `Q` close and optional `Z/z` sleeps.
- The new `software/python/plasma_interfaces/swd_debug_bitbang.py` exercises only a **byte-level, injected-MMIO protocol core** against Host-only tests; it rejects JTAG/reset commands and unsupported sleeps, guards clock/data turnaround and has no socket listener, authenticated lease implementation or OpenOCD process. It **does not** qualify the newer binary, its build options, a real UNIX Bridge, or physical SWD. The existing OpenOCD 0.12.0 production Providers remain unchanged. `DEBUG_REMOTE_BITBANG_SWD=BLOCKED_VERSION_UNQUALIFIED` remains binding.

## Retire unnecessary MPE/legacy while retaining useful tests

- Draft PR #1189's `plasma_mpe_*` RTL and `pl/projects/z2-mpe-dual-site/` Tcl are **not** the final IP integration. Refactor into a **reusable single-Site AXI SWD IP** instantiated twice through a standard AXI Interconnect, with each Site independently qualified. Migrate XDC, ABI, PS Driver, OpenOCD adapter, Cocotb and build contracts. Prior MPE simulations remain regression evidence for the old candidate only; **rerun against the new RTL** and do not reuse PASS results as new-IP sign-off.
- Retire prior `z2-swd-gpio` / `z2-swd03-axi` / `z2-bluepill-rbb` product paths, obsolete single-Site WordPort/RemoteBitbang Bridge/API and F1-B build-only dependencies **after replacement qualification**. Do **not** retire the OpenOCD `remote_bitbang` protocol itself; provide a new, isolated diagnostic bridge. No legacy fallback/import from new production applications.
- Preserve existing Root Guard, Owner Locks, Golden Restore, historical evidence and functioning installed Image until separate retirement acceptance. Changes to normal runtime, physical I/O or DUT activity remain gated.

## Blocking implementation and verification requirements

1. Explicit per-Site AXI-Lite register specification for `MODE`, `BB_SWCLK`, `BB_SWDIO_OUT`, `BB_SWDIO_OE`, `BB_SWDIO_IN`, `NORMAL_CMD`, Status/FIFO and safe reset. Deny Debug registers in Normal, and deny Normal command launch in Debug.
2. Reusable single-Site synthesizable SWD IP with two independent instances, no central MPE decoder/scheduler; AXI interconnect explicitly resolves two independently addressable slaves.
3. Cocotb/pytest negative tests for mode change under Busy, pending responses, bad lease/error, Bitbang output contention, per-Site isolation, reset/disconnect, and no silent fallback. Tests must exercise same production PS control semantics where applicable.
4. Independently version-locked OpenOCD Debug SWD bridge + source/protocol conformance; no assumption that 0.12.0 supports SWD `remote_bitbang`.
5. SWPC Path 2 `operator-cli` clean Vivado Build, actual timing/DRC, HWH two-instance address, physical JA/JB pad mapping, BIT/HWH hashes and matched Image Manifest; no Build/Deploy conflation.
6. Under Owner-approved scope, PS/Linux ARMv7 MMIO qualification and 2-real-DUT independent SWD behavior. No HIL nor product authorization is asserted by this ADR.

**Current status: `ARCHITECTURE_APPROVED_PENDING_IMPLEMENTATION`, `OPENOCD_012_SWDBB_UNSUPPORTED`, `VIVADO_BUILD_NOT_RUN`, `PHYSICAL_HIL_NOT_RUN`.**

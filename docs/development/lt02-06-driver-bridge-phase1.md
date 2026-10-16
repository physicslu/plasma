# LT02-06 Phase 1 — PS/PL diagnostic bridge (host-only, inactive by default)

## Purpose

Connect the **existing production `LoopTestDriver`** to Plasma Protocol v3.3
as an explicitly injected, Site 1-only PL loopback diagnostic. This does
**not** turn `FPGAInterface` into a flash programmer, does not load a
bitstream and does not change production services or FPGA images.

The LT02-05 real PYNQ-Z2 development HIL was **reported PASS** by the lab
operator on 2026-10-16 at commit
`473e93eb71f6861d0dafd603dde9c398d842cf8f`,
with ten byte boundaries, physical FPGA counter readback and original
`base.bin` restoration. That report qualifies the tested real-PS driver
experiment, **not** this new northbound data path, real user-interface
activation, protocol access control or any external target.

## Phase 1 implemented topology

```text
PlasmaClient diagnostic_loopback(endpoint="pl")
    -> Plasma Protocol v3.3 TCP (binary payload + declared CRC)
    -> PlasmaServer, ONLY if explicitly created with lt02_driver=<LoopTestDriver>
       -> injected production LoopTestDriver.echo()
       -> caller-owned Site 1 WordPort (in host tests: fake word register port)
       -> result payload + per-case hardware counters, chunks, elapsed_ns
    -> response source="pl" and LT02 metadata
    -> Gateway execute_ps_loopback(..., pl_endpoint_enabled=True) for testing
       -> strict physical counters + CRC + exact byte comparison
```

### Fail-closed defaults

- No implicit LinuxMMIO creation, `/dev/mem`, UART, device-tree, FPGA load,
  power, external SWD or DUT access.
- `PlasmaServer(..., lt02_driver=None)` (the actual default) continues PS
  loopback normally; `endpoint="pl"` yields `OPERATION_UNSUPPORTED`.
- Only a production `LoopTestDriver` object is accepted for explicit injection.
  It must be composed by a separate supervised platform owner *after*
  verifying loaded image/clock/driver ownership and must be quiesced before
  reconfiguration. Merely creating a Python object is **not** physical
  hardware attestation.
- Hardware payload per case is capped at **1 MiB** before driver access;
  `LoopTestDriver` chunks each request into 2 KiB scratchpad transfers.
  Each case checks raw bytes, CRC, word counts and exact count of chunks.
  No operation retries an uncertain write.
- Any driver exception / inconsistent result permanently quarantines the
  server instance's PL endpoint until explicit external recovery and
  reinitialization; the PS-only route remains independent.
- The public Engineering REST Gateway remains **default disabled for PL**
  even when a Protocol-server driver has been injected. The internal
  `pl_endpoint_enabled=True` parameter permits only developer/unit tests
  of the validation function; the deployed Gateway does not pass it.
  Existing Secure Gateway STATUS_READ permission is **not** automatically
  treated as authorization to perform physical PL writes.
- `FPGAInterface` remains fail-closed for Erase/Program/Verify/Read.

## Phase 1 verification and known limits

New host-only test `software/python/tests/test_lt02_diagnostic_bridge.py` uses
the **real TCP server and the real production driver** with an injected fake
32-bit port. Cases include: default deny, 10 byte boundaries
(1, 4, 5, 1023, 1024, 1025, 2048, 2049, 4097, 8193), source/CRC/counter/chunk
proof, independent PS operation, 1 MiB cap, failed physical write quarantine,
missing/invalid injected driver, and Gateway default deny.

These tests do **not** claim that the Gateway has an actual live PYNQ-Z2
`LinuxMMIO` backend, that it can securely bind per-request image receipts,
or that Manager/Browser allows PL selection.

## Phase 2 required before public PL enablement

1. Add an explicit, verified PPU-local hardware session owner with site lease,
   image Manifest/BIT/HWH/BIN digest + actual loaded receipt, FCLK/UIO/process
   ownership, and lifecycle hooks to close maps before reconfiguration.
2. Add secured Manager/Gateway admission policy for PL writes, consistent with
   the existing role model and Site state/ownership; do not silently treat
   STATUS_READ authorization as sufficient.
3. Validate real PPU Gateway → Plasma Server → ARMv7 native LinuxMMIO →
   LoopTestDriver → FPGA on the supervised Z2, including recovery of base image.
4. Only after real-path PASS, wire the existing Web Engineering Loop Test
   PL option, with explicit source/provenance and no PS/Mock fallback.
5. Do not interpret internal AXI loopback as SWD wire timing or target Flash
   programming validation.

**Gate 2**: PR merge requires explicit owner approval, per root `AGENTS.md`.

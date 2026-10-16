# LT02-05 — PYNQ-Z2 real PS↔PL MMIO loopback HIL gates

**Status of this change: HOST P0 SOURCE ONLY.** This folder contains a
fail-closed *offline* artifact/preload-inventory gate and deterministic
vectors using the production Python LoopTestDriver via an injected word port.
There is **NO CLI that opens /dev/mem, loads a BIT/BIN, changes services,
or accesses Z2**. A P0 PASS never grants live hardware access.

Historical SWD-03 PYNQ-Z2 HIL and PR #954 five-aperture Vivado build do not
qualify the new LT02 scratchpad on physical silicon.

## Evidence chain

| Gate | Required observation | Meaning |
| --- | --- | --- |
| HOST-RTL | Existing Cocotb/Verilator production driver RTL tests | Host only |
| HOST-VIVADO | PR #954 retained actual BIT/HWH/manifest/Vivado logs | Owner reported PASS; independently inspect SHA-256 |
| LT02-P0 | This PR: independently pinned artifacts + actual HWH + original Z2 inventory + operator attestations | OFFLINE, no live authorization |
| LT02-HIL01 | Supervised candidate load, live Identity/ABI readback | Real Z2, NOT RUN |
| LT02-HIL02 | Production ARMv7 LinuxMMIO + LoopTestDriver 1/1023/1024/1025/2048/2049-byte CRC/counters and repeats | Real Z2, NOT RUN |
| LT02-R0 | Restore original PYNQ base.bin, metadata, UIO, FCLK, services and Gateway | Real Z2, NOT RUN |
| LT02-06 | Managed PPU Gateway/Server → Manager → Control Station PL Endpoint | NOT IMPLEMENTED |

## SWPC preflight without Z2 access

Identify the actual retained LT02 Vivado run directory:
pl/build/z2-lt02-axi/run.XXXXXXXX/artifacts. Independently review its
manifest.json and .sha256 receipts, raw Vivado logs, setup/hold, DRC and
methodology reports. Do not copy a historical SWD-03 manifest.

The candidate BIN must be independently converted from the new LT02 BIT
using the reviewed Zynq-7000/Bootgen procedure. BIT and BIN digests differ;
the FPGA Manager cannot load arbitrary BIT containers.

Prepare a separately reviewed PRIVATE approval JSON. Never auto-populate
this from unreviewed candidate-provided digests:

    {
      "schema_version": 1,
      "source_git_sha": "<actual 40-hex source commit from manifest>",
      "candidate_bit_sha256": "<reviewed BIT SHA256>",
      "candidate_hwh_sha256": "<reviewed HWH SHA256>",
      "candidate_manifest_sha256": "<reviewed manifest SHA256>",
      "candidate_bin_sha256": "<reviewed converted BIN SHA256>",
      "recovery_bin_sha256": "<verified original PYNQ base.bin SHA256>",
      "recovery_hwh_sha256": "<verified original PYNQ base.hwh SHA256>"
    }

The exact original PYNQ recovery digests are independently pinned in
pl.hil.swd04.contract, not inherited from the new LT02 manifest.
The source SHA is the reviewed **build source commit** (may differ from
the PR #954 merge commit). Never invent a Build ID.

Obtain a current read-only Z2 inventory via existing
pl.hil.swd04.collect (see docs/development/swd04-z2-hil-runbook.md).
The operator must manually check and mark these PRIVATE schema-v1 booleans:

- exclusive_pl_ownership_confirmed
- uart_console_verified
- independent_power_recovery_verified
- maintenance_window_confirmed
- restoration_operator_ready
- no_external_dut_connected
- original_metadata_backed_up
- uio_driver_reconciliation_planned
- bitstream_to_bin_conversion_verified

These are human assertions, not independently proven by JSON.
Do not synthesize true values to pass automated checks.

From repository root, after actual files and JSON exist:

    PYTHONPATH="$PWD:$PWD/software/python" python3 -m pl.hil.lt02.preflight \
      --bit /retained/lt02/artifacts/plasma-z2-lt02-five-aperture-0.1.0.bit \
      --hwh /retained/lt02/artifacts/plasma-z2-lt02-five-aperture-0.1.0.hwh \
      --manifest /retained/lt02/artifacts/manifest.json \
      --candidate-bin /private/approved-lt02.bin \
      --recovery-bin /private/known-good/base.bin \
      --recovery-hwh /private/known-good/base.hwh \
      --approved-hashes /private/approved-lt02-hashes.json \
      --inventory /private/z2-before.json \
      --operator /private/operator-attestation.json \
      --output /private/lt02-p0-result.json

Output is exclusively created, never overwritten, and explicitly records
go_live_authorization=NOT_GRANTED, native_mmio_hil=NOT_RUN,
fpga_loading=NOT_RUN and recovery_execution=NOT_RUN.

P0 is a record-consistency check and cannot establish physical UART/power
recovery or all current PL users' state. Recheck these independently
immediately before any separately approved live operation.

## Real HIL sequence (NOT IMPLEMENTED by this PR)

1. Physically verify UART, independent power recovery, known-good original
   BIN/HWH, PYNQ metadata and the exclusive PS GP0 ownership, including
   kernel/UIO/DMA/mmap consumers. A flock alone is not proof.
2. Separately authorize a supervised FPGA Manager load. Bind exact candidate
   firmware digest, current boot ID, most recent dmesg load line, observed
   Z2 Identity/Build ID, and five-aperture MMIO ownership evidence.
   Never reuse old SWD-03 receipts or execute ps7_init.
3. HIL01: perform bounded, known-address read-only Identity/ABI checks.
   Never deliberately probe an invalid hardware AXI address.
4. HIL02: run exact Z2 ARMv7 CPython 3.12.13, production LinuxMMIO with
   loopback_aperture(0x40004000), and one exclusive Site 1 lease. Inject it
   into pl.hil.lt02.cases.run_suite; the function exercises the REAL
   LoopTestDriver with CRC, counters and deterministic lengths. A fake-port
   PASS is HOST ONLY. Stop without retry on any mismatch/uncertain write.
5. Close all leases and MMIO mappings. Restore original PYNQ base.bin and
   metadata/UIO/services even after a partial failure if Linux remains
   responsive. Recollect before/after inventory; reuse
   pl.hil.swd04.restore acceptance; check SSH, UART, Jupyter, Gateway,
   FCLK0, boot ID and no new AXI/kernel errors.
6. If Linux hangs or SIGBUSes on physical AXI, STOP probing. Python timeouts
   cannot unhang the bus. Use separately verified UART/power recovery.

This initial P0 change provides NO live runner, no --execute-live override
and no FPGA-load/restore script. A separately reviewed maintenance plan and
hardware operation authorization are mandatory before live testing.

Do not publish raw inventories/credentials or FPGA artifacts in the PR.
The Control Station PL selector remains disabled until LT02-06 real-path
integration and separate qualification.

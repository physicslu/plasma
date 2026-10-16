# LT02-05 — Real PYNQ-Z2 native LinuxMMIO loopback development HIL

**Status:** execution kit/source and host-only tests. **No new Z2 load or
actual LT02-05 MMIO operation is claimed until observed on the board.**

Previously qualified SWD-03/Identity evidence belongs to **its own**
four-aperture image, not the current five-aperture LT02 candidate. Use the
SWPC Vivado build retained for merged PR #954, with matching
`.bit`, `.hwh`, `manifest.json` and a reviewed Zynq7000 BIT→BIN conversion.
Never substitute a different known-good image or bypass a failed HWH check.

## What is exercised

The HIL entrypoint is `pl.hil.lt02.native`. It uses exactly the production
`plasma_interfaces.linux_mmio.LinuxMMIO` native ARMv7 word-access backend
and the production `plasma_interfaces.mmio_loop_test.LoopTestDriver`:

1. Validate SHA256 of a **review-pinned** Manifest and actual BIT/HWH files;
   verify exactly five 4 KiB GP0 apertures, source Build ID, ABI, 2 KiB capacity
   and no external PL IO/programming capabilities.
2. Check original PYNQ `base.bin`/`base.hwh` against retained, known-good
   SHA256 before any experimental image is loaded.
3. With a supervised external load in progress only after current PL ownership
   and recovery checks, record the current-boot FPGA Manager last-load line in a
   **root-protected unique receipt**. The recorder never loads an FPGA image.
4. After the candidate is loaded, require the qualified ARMv7 CPython
   3.12.13 `/opt/plasma/python/3.12.13`, operating FPGA Manager, 100 MHz
   enabled FCLK0, current boot/load receipt, root-owned files and no
   overlapping kernel UIO/platform driver or retained /dev/mem mappings.
5. Check real Identity v1 Build ID from the image **before writing**. Use
   `LinuxMMIO` exact allowlist: Identity RO, LT02's approved data words RW,
   read-only metadata/counters and write-only command (never issued).
6. Run deterministic payloads of 1, 4, 5, 1023, 1024, 1025, 2048, 2049,
   4097 and 8193 bytes. Verify **every byte**, returned CRC32, read/write
   counter delta and chunk count with the production driver; no retry after
   a possibly completed MMIO transaction.
7. Close the MMIO owner and save unique `started.json` and `result.json`
   without overwriting previous evidence. A SIGBUS/kernel stall may leave
   **STARTED only**, which is NOT PASS.
8. A supervised *external* orchestrator must restore the exact original
   FPGA image (including metadata/UIO/clock/services/HTTP reconciliation) in
   success and failure paths and independently observe the restoration.
   This module **does not perform FPGA loading, service changes or recovery**.


## LinuxMMIO v1.1 / LT02 repeat-and-performance regression (candidate)

This is an **opt-in addition** to the above supervised LT02-05 procedure.
The default is unchanged: **one** ten-case matrix; no automatic FPGA load.
Only after the exact candidate has passed the current live preflight, an
operator-authorized supervisor may supply `--repeats 2` through
`--repeats 8` to the same `--execute-live` invocation. The manifest,
current-boot load receipt, original image backup and independent recovery
requirements do not change. Every attempt uses a fresh unique `--output`
directory; do not overwrite old evidence. Do not run repeat stress tests if
other SWPC agents currently own the FPGA image or MMIO aperture.

`result.json` contains `cases` with repeat/case indices, byte-exact CRC,
counter deltas and elapsed time; `performance` includes aggregate
bytes, word counts, observed wall-time effective B/s and word ops/s,
per-case latency p50/p95/max, and `mmio_word_accesses` with observed
successful Python native word read/write counts. Word-operation statistics
include metadata/identity/counter accesses, whereas `data_*_words` only
count LT02 scratchpad payload accesses. These are **different denominators**.
The wall-time rate includes interpreter overhead, thread scheduling and
mapping effects; it is **not** an FPGA bus or electrical throughput
specification. Zero elapsed wall time produces `null` rather than a
fabricated infinite rate. No arbitrary throughput PASS threshold is enforced.

After an uncertain MMIO error, counter discrepancy or CRC mismatch, the
production `LoopTestDriver` instance is poisoned and no second case is
attempted. A Python exception or timeout cannot guarantee recovery from
kernel AXI SIGBUS/hang. The independent supervisor must still restore the
original `base.bin` and verify UIO, clocks, services and network status
before overall HIL PASS is claimed.

**As of this change: host regression and CI are distinct from a new Z2
execution. The original PR #957 real-HIL PASS remains historical evidence;
a v1.1 repeated real-board performance result must be separately observed.**

## Approved development orchestration on SWPC

Use `docs/development/codex-z2-hil-development-command.md` and
`AGENTS.md`, not a new review/permission round within previously approved
prototype development scope. Perform a bounded current-state preflight on
the enrolled PYNQ-Z2, resolve its authorized local SSH credentials without
printing them, check actual PL ownership/clock and physically usable
out-of-band recovery, and use only the existing managed FPGA Manager path.

The actual candidate .bin is a **separate hashed output** of a verified
Zynq-7000 conversion from the LT02 `.bit`; do not write a raw .bit to
FPGA Manager. Retain exact conversion log, candidate hash and current
service/driver/metadata evidence outside Git.

### On Z2 after the supervised candidate load (not on SWPC)

Stage the HIL Python modules and the matching candidate files in a private
directory, under the exact approved installed Python interpreter. Ensure
`plasma_interfaces` uses the matching reviewed production code, and
`pl.hil` is importable via the checked-out source root on `PYTHONPATH`.

Example **argument contract** (the orchestrator supplies real reviewed paths):

```bash
# Variables must refer to the actually reviewed LT02 build and known-good
# recovery bytes. This is not an instruction to load an FPGA.
LT02_PY=/opt/plasma/python/3.12.13/bin/python3
LT02_CODE=/root/lt02-reviewed-source
LT02_MANIFEST=/root/lt02-hil/candidate/manifest.json
LT02_BIT=/root/lt02-hil/candidate/lt02.bit
LT02_HWH=/root/lt02-hil/candidate/lt02.hwh
LT02_BIN=/root/lt02-hil/candidate/lt02.bin
LT02_BASE_BIN=/root/lt02-hil/recovery/base.bin
LT02_BASE_HWH=/root/lt02-hil/recovery/base.hwh
LT02_RECEIPT=/root/lt02-hil/evidence/loaded.json
LT02_RESULT=/root/lt02-hil/evidence/mmio-case-results
LT02_REVIEWED_MANIFEST_SHA256=<64-digit-review-pinned-manifest-digest>

# To avoid hand-copying arguments, the orchestrator owns the common bundle.
# First record only the observed current-boot load; *no MMIO access*:
PYTHONPATH="$LT02_CODE:$LT02_CODE/software/python" "$LT02_PY" -m pl.hil.lt02.native \
  --manifest "$LT02_MANIFEST" --bit "$LT02_BIT" --hwh "$LT02_HWH" \
  --candidate-bin "$LT02_BIN" --recovery-bin "$LT02_BASE_BIN" \
  --recovery-hwh "$LT02_BASE_HWH" --receipt "$LT02_RECEIPT" \
  --output "$LT02_RESULT" \
  --expected-manifest-sha256 "$LT02_REVIEWED_MANIFEST_SHA256" \
  --record-loaded-image

# Only after that receipt and actual hardware preflight, one bounded run:
PYTHONPATH="$LT02_CODE:$LT02_CODE/software/python" "$LT02_PY" -m pl.hil.lt02.native \
  --manifest "$LT02_MANIFEST" --bit "$LT02_BIT" --hwh "$LT02_HWH" \
  --candidate-bin "$LT02_BIN" --recovery-bin "$LT02_BASE_BIN" \
  --recovery-hwh "$LT02_BASE_HWH" --receipt "$LT02_RECEIPT" \
  --output "$LT02_RESULT" \
  --expected-manifest-sha256 "$LT02_REVIEWED_MANIFEST_SHA256" \
  --execute-live --ack-unrecoverable-axi-stall-risk
```

Those commands MUST run in the authorized, isolated, supervised
PYNQ-Z2 execution context. Do not substitute example paths or digests
for actual retained artifacts. The `--output` directory must not already
exist. The receipt filename and its parent must be root-owned/private.

A Linux/Python timeout cannot interrupt a physically stalled AXI read;
after an actual fault do not run a second MMIO attempt. Use independent
UART/power recovery only if technically safe.

**Acceptance boundary:** `LT02_REAL_MMIO_CASES_PASS_FPGA_RECOVERY_NOT_RUN`
proves only the bounded real data operations were observed. Overall
**LT02-05 HIL PASS** additionally requires observed, independently
verified restoration of original BIT/BIN/HWH/metadata, UIO, clocks,
service states, SSH and HTTP. Physical SWD, DUT and real IC programming
remain **NOT RUN**.

Host CI exercises a fake word-port and Cocotb real RTL independently; it
cannot prove Z2 FPGA configuration or real MMIO.

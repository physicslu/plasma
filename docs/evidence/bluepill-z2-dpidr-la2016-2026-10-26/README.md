# Z2 PS OpenOCD → PL SWD → Blue Pill DPIDR with LA2016

**Observed 2026-10-26; DPIDR FAIL.** This is the direct Codex experiment on
SWPC at repository HEAD `0c11e3420272bed09e778182e9d6422c115f75d0`.
No Path 2 or Path 3 Dispatcher ran. The owner authorized the physical scope
and attested the 3.3 V Blue Pill connection, common ground and isolated
ST-LINK. This archive does not establish analog voltage quality or physical
pin continuity.

The actual execution path was:

```text
SWPC Codex ── SSH/sudo ── Z2 PS OpenOCD 0.12.0+dev-02767-g5088db4c9
   │                             │
   │                             └─ PS-local UNIX Remote Bitbang socket
   │                                → WordPort Bridge → /dev/mem → Z2 PL
   │                                                       → Blue Pill SWD
   └─ passive sigrok capture ── KINGST LA2016 CH0/CH1/CH2
```

## Image and tooling before the SWD attempt

The Z2 returned ARMv7, Boot ID
`4cefdc0c-f586-4d19-b126-1d8e1108c8f1`, and FPGA Manager `operating`.
The protected checkpoint already held
`plasma-bluepill-swd-65dca783.bin` in `IMAGE` state for that Boot ID.
Its actual BIN SHA256 was
`bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1`,
matching the companion Manifest; the Manager's last current-boot load record
named that BIN. The Manifest SHA256 was
`5f5fa580e9b437ce3a9377313bdfb4fc6012031270e1544c12034ccf3ca0fb98`.
The retained Golden `base.bin` SHA256 was
`c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`.
The existing protected Root source pin was
`55f6db3bc5fa866135e5a9070175928d044e53ce`.

The image was **already loaded**, so this session did not issue a new FPGA
Manager download. Reconfiguration would have added risk without changing
the candidate identity. The Root `test` operation first refused three
pre-existing Python 3.10 `.pyc` files with
`PATH2_UNPINNED_BYTECODE_DENIED`. They were moved intact into a private
root-owned quarantine with individual hashes recorded in
[bytecode-quarantine-receipt.json](bytecode-quarantine-receipt.json). The second Root `test`
returned `IDENTITY_PASS`, `read32_count=3`, `write32_count=0`,
`test_count=3`, same Boot ID, `auto_restore=false`.
The Root receipt's `project` string is a compatibility field; the actual
loaded BIN and companion Manifest are identified above.

The PS-local Bridge source was staged from the exact
[deployment bundle](bridge-bundle.tar) whose SHA256 is
`87ff32c79360d57bc9abd7c9ecaf67a68be3cc6b7464cadfb43db589b8c9a8ff`.
The bundle contains the Bridge, narrow WordPort, Linux MMIO, Remote Bitbang
and ARMv7 barrier source; per-file hashes are in
[source-integrity.json](source-integrity.json). The native ARMv7 library
compiled on Z2, exposed one `dmb sy` instruction in disassembly, imported
successfully, and had SHA256
`260d17d87e2edc5a6c97757b47a6ede78fa024d9ac19fbb9020ac257600a6555`.
This is a barrier/source check, not independent proof that every PS/PL write
reached an external pin.

The LA2016 was unique and idle before capture. The pinned sigrok AppImage
SHA256 was
`b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`;
its driver initialization returned exit 0 with the existing firmware
resource. `CH0=SWCLK`, `CH1=SWDIO`, `CH2=Blue Pill 3.3 V digital logic`
was the owner-attested probe map. The LA was used as an input-only observer;
no PWM output was enabled. ST-LINK was not enumerated on SWPC during the
preflight, and the owner attested that it was isolated from the DUT.

## Exact sequence and results

| Step | Observation |
| --- | --- |
| Z2 preflight | Candidate BIN/Manifest/Golden hashes matched; same-boot `IMAGE` checkpoint; Manager `operating`; `/dev/mem` and `/dev/uio1` had no `fuser` owner. |
| PS tooling | OpenOCD `remote_bitbang` + SWD configuration parsed with exit 0 before `init`; Bridge bundle and barrier staged and checked. |
| Protected Identity | Initial exit 2 on unpinned bytecode; after reversible quarantine, `IDENTITY_PASS` with 3 reads and 0 writes. |
| 12:07:47 UTC capture 01 | LA capture started first and completed. A mistyped expected BIN digest in the local run script triggered `AssertionError: IMAGE_CHANGED` before Bridge startup. **Z2 SWD NOT_RUN** for this capture. |
| 12:08:43 UTC capture 02 | LA capture started first; Z2 PS OpenOCD connected to the PS-local UNIX socket. Bridge processed 3,415 wire bytes, 231 MMIO reads and 3,141 MMIO writes, then exited 0 and removed the socket. OpenOCD exited 1: `Error connecting DP: cannot read IDR`. **DPIDR FAIL**, no DPIDR value. |
| Post-run | Same Boot ID and `IMAGE` checkpoint, FPGA Manager `operating`, BIN/Golden hashes unchanged; `/dev/mem`, `/dev/uio1` and LA USB free. The image remained loaded; no Golden Restore was selected. |

Both captures used the existing pinned sigrok AppImage in passive mode,
`samplerate=5m`, `CH0,CH1,CH2`, `--samples 50000000`. Each archive contains
50,002,496 actual samples at 5 MHz and 24 two-byte logic chunks. Capture
was observed to start before the corresponding Z2 command. The first command
stopped in preflight; the second reached OpenOCD and the Bridge. Their UTC
timestamps, exact exit codes and trimmed process output are in the
[capture 01](capture-01-sanitized.json) and
[capture 02](capture-02-sanitized.json) receipts.

The Z2 PS OpenOCD configuration disabled its GDB/Tcl/telnet ports, selected
`remote_bitbang`, pointed `remote_bitbang host` to the **Z2-local** UNIX
socket with `port 0`, selected SWD, declared one Blue Pill DAP with expected
ID `0x1ba01477`, then ran `init; shutdown`. There was no target Flash erase,
program, readback, reset or SWPC per-bit forwarding. The OpenOCD log in the
second receipt shows socket connection followed by `cannot read IDR`.

## First measured difference and interpretation

An offline decode of capture 02 produced no SWD annotations. Direct parsing
of the raw `.sr` found **one logic state across all 50,002,496 samples**:
`CH2:CH1:CH0 = 0b110`, so CH0/SWCLK was low with **zero transitions**.
Capture 01 had the same constant state, as expected from its aborted Z2
preflight. For comparison, the archived
[successful ST-LINK reference](../stlink-stm32f103-swd-reference/2026-10-23/README.md)
contains four logic states in `round-01-verify.sr`. This comparison establishes
that the current LA recording lacks an observable SWCLK edge; it does not
calibrate analog level or identify which segment of the path failed.

`Error connecting DP: cannot read IDR` is the OpenOCD failure. The first
measurable signal difference is the absent CH0 edge despite 3,141 Bridge
write32 calls. The write counter records Python MMIO operations, not proof
that an AXI transaction produced an edge at PMODB or reached the LA probe.
Output routing, pin continuity, PL register behavior, bus write semantics
and measurement placement remain hypotheses. The Blue Pill's DPIDR, ACK and
turnaround cannot be assessed from a trace with no SWCLK. No further SWD
attempt was made after this physical failure.

## Evidence and offline verification

| File | Contents |
| --- | --- |
| [capture-01.sr](capture-01.sr), [capture-02.sr](capture-02.sr) | Byte-for-byte LA2016 sigrok archives from the two captures. |
| [capture-01-sanitized.json](capture-01-sanitized.json), [capture-02-sanitized.json](capture-02-sanitized.json) | Original process receipts with only the dynamic LA USB bus/device address redacted. Source and published hashes are in `source-integrity.json`. |
| [postrun-preflight.json](postrun-preflight.json) | Saved read-only Z2 state after the physical attempt. |
| [execution-receipts.json](execution-receipts.json) | Exact terminal-observed Root/Bridge summaries and limits; the Identity Root output had no separately saved raw file at execution time. |
| [bytecode-quarantine-receipt.json](bytecode-quarantine-receipt.json) | Original bytecode path, timestamp, size and hash, plus reversible quarantine result. |
| [measurements.json](measurements.json) | Recomputed logic states and sample counts. |
| [bridge-bundle.tar](bridge-bundle.tar), [source-integrity.json](source-integrity.json) | Exact PS source package and per-file checksums. |
| [execution-scripts-redacted.tar](execution-scripts-redacted.tar) | The 14 local command helpers retained for audit, with only the operator home path replaced by `<SWPC_HOME>`. These are archival source, not a hardware runbook. The capture and Z2 run scripts reflect the corrected second attempt; the first attempt's digest typo is preserved by its error receipt and described above. |
| [SHA256SUMS](SHA256SUMS), [verify.py](verify.py) | Offline integrity and `.sr` logic-state verification. |

Run `python3 docs/evidence/bluepill-z2-dpidr-la2016-2026-10-26/verify.py`
from the repository. It reads archived files only. The archive does not
include credentials, host address, private USB serial, raw privileged dmesg,
an analog voltage trace or a hardware-repair claim. The source session's
unredacted reports remain in the owner-controlled `.work` area and are not
committed.

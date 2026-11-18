# Native C WordPort Z2 prototype execution record

This directory indexes the reviewed scripts used for the owner-approved PR #1199
Path 3 experiments. The [scripts](scripts/) are source snapshots for review;
they are **not** an automatic hardware workflow. Run them only with current
Boot ID, Root source pin, FPGA Image/Manifest, ownership, wiring and recovery
checks. `remote_long.py` reads the existing owner-controlled credential source;
no credentials are stored here.

## Script map

| Step | Script | Purpose |
|---|---|---|
| Z2 staging | [z2_stage.py](scripts/z2_stage.py), [transfer.py](scripts/transfer.py) | Copy the existing PS bundle to an isolated directory; transfer the PR source and SHA-pinned ARMv7 library. |
| Native DPIDR + LA | [z2_native_dpidr.py](scripts/z2_native_dpidr.py), [capture_native_dpidr.py](scripts/capture_native_dpidr.py) | PS-local OpenOCD through Native C bridge, with passive LA2016 capture. |
| v0.1 erase/program + LA | [z2_native_flash.py](scripts/z2_native_flash.py), [capture_native_flash.py](scripts/capture_native_flash.py) | One 19-page erase/program, independent readback and optional guarded reset modes. |
| Readback diagnosis | [z2_inspect_readback.py](scripts/z2_inspect_readback.py) | Inspect the partial file after the old 60-second session alarm. |
| CDC | [cdc_heartbeat.py](scripts/cdc_heartbeat.py) | Six-second passive heartbeat observation; no UART TX. |
| Transport | [remote_long.py](scripts/remote_long.py) | Existing pinned SSH/sudo route, with credential redaction. |

The `z2_native_flash.py` snapshot is the **final 600/60-second acceptance
version**. Earlier erase/program and segmented-read modes used the same guarded
bridge path, but this file evolved as the experiment progressed; it is not a
byte-for-byte snapshot of every earlier invocation. The native library itself
was not rebuilt for the timeout change: CI ARMv7 SHA256
`66261cef851c9777469b393b7539c5b0f8c2b039a032f1a5b4cbf9e93460e447`.

## Results and local artifacts

- DPIDR: `0x1ba01477` from Z2 PS OpenOCD; simultaneous LA and Sigrok decode.
- One v0.1 erase/program: 18,768 bytes, simultaneous LA; independent segmented
  readback matched SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`.
  A single `reset run` then produced consecutive CDC v0.1 heartbeats.
- Timeout revision: total Bridge alarm 600 seconds, socket idle 60 seconds.
  A single 18,768-byte readback completed with 0 mismatches, OpenOCD and bridge
  exit 0, and safe owner/MMIO release. No erase/program/reset was repeated.

Raw `.sr` waveforms, Flash readbacks, full OpenOCD receipts and the SHA256
inventory remain in the operator's ignored
`.work/native-c-wordport-1199/` directory; they are not published in Git.
The old monolithic readback's large repeated broken-pipe stderr was not saved
as a separate complete file. Its partial 12,288-byte output and failure cause
are retained in the local result record.

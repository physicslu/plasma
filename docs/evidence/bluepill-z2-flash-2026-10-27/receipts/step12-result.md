# Blue Pill Step 1–2, 2026-10-27

Execution: SWPC Codex Path 3 direct SSH/sudo to Z2 PS, local repository
`main` HEAD `c37fbb6011c1073c5ec0146633f538a14f4135b9`. No Dispatcher run ID.
No FPGA download, LA capture, OpenOCD, DPIDR or Flash operation.

## Step 1

- Z2 Boot ID `4cefdc0c-f586-4d19-b126-1d8e1108c8f1`; FPGA Manager
  `operating`; protected checkpoint `IMAGE` for
  `plasma-bluepill-swd-65dca783.bin` in the same boot.
- Actual BIN SHA256 `bfbd3d872caeff05a8f9daa0829b6292e5b5036c6b927d6c779e13fe9ec1a1`,
  companion Manifest SHA256 `5f5fa580e9b437ce3a9377313bdfb4fc6012031270e1544c12034ccf3ca0fb98`,
  Golden `base.bin` SHA256 `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`.
- Installed Root source pin `55f6db3bc5fa866135e5a9070175928d044e53ce`.
  First protected Identity attempt exited 2 with
  `PATH2_UNPINNED_BYTECODE_DENIED`. Three exact Python 3.12 `.pyc` files
  generated in the protected source tree were reversibly moved, with
  SHA256 verification, to
  `/root/plasma-path2-bytecode-quarantine-20261027-step12`.
  The second protected Root `test` exited 0: `IDENTITY_PASS`, 3 reads,
  0 writes, `test_count=4`, same Boot ID.
- `/dev/mem` and `/dev/uio1` had `fuser` exit 1 before and after the test.
  The LA2016 was enumerated as unique VID:PID `77a1:01a2` at the current
  USB node. The pinned AppImage SHA256 matched
  `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`;
  actual USB device read and write access checks both exited 0. LA was
  not opened or used.

## Step 2

The one Z2 PS MMIO diagnostic exited 0 with `STEP2_INTERNAL_SWCLK_PASS`.
It verified source SHA, Manifest/Image and Golden through the existing
Root code, acquired `RootZ2TargetPort.exclusive()` and Site 1 MMIO lease,
and used the pinned ARMv7 DMB barrier.

| DRIVE | SAMPLE | SWCLK bit 1 | SWDIO OE bit 2 |
| --- | --- | --- | --- |
| `0x02` | `0x09` | 0 | 0 |
| `0x03` | `0x0B` | 1 | 0 |
| `0x02` | `0x09` | 0 | 0 |

There were 7 MMIO reads and 3 writes. The baseline and final SAMPLE were
both `0x09`; CLK was Low and DIO Hi-Z at exit. The High state was held for
approximately 1 second. Afterward the Manager was still `operating`, the
checkpoint still `IMAGE`, the BIN/Manifest/Golden hashes were unchanged,
and both MMIO devices were free. This verifies **internal register behavior
only**; physical PMOD SWCLK edges remain NOT_RUN/unknown.

Execution sources: `remote_step2.py`, `quarantine_bytecode.py` here,
and the existing `.work/bluepill-dpidr-direct-20261027/remote.py` transport.

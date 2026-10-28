# Image-agnostic Native C WordPort — Path 2 prototype

Status: Gate 1 Draft PR #1200, **Host-only software candidate**. No hardware
deployment, production Job authorization, FPGA reload or DUT operation in this
change. Do not construe source-level success as a physical HIL result.

## Design decision

**Do not bake a firmware name, revision, size, SHA or erase length into the
programmer engine.** A reviewed Programming Asset is selected per Job/Work
Order. The exact ICPN's reviewed Programming Profile and Memory Geometry
determine the *admitted* target/erase/program behaviour.

Production-intent boundaries (existing, unchanged):

```text
SWPC / Controller / Path 2 owner-approved Work Order
  -> Programming Asset (chosen per job; URI/path, expected SHA256, format)
  -> normalized Image / frozen ExecutionImageRef
  -> Exact ICPN + version-locked ProgrammingQualification
  -> provider-specific Programming Plan + exact Geometry
  -> Z2 PS OpenOCD (native execution) -> local Native C WordPort bridge
  -> FPGA PL -> selected Site -> DUT
  -> receipts / readback hash / per-Site result
```

The existing canonical `OpenOCDPlanCompiler`/`OpenOCDPlanExecutor` is
**software-only** and must not be silently promoted to production hardware
runtime by this development tool. This first prototype uses the already
HIL-proven single-Site physical WordPort transport with exact hardware
admission. The cross-manufacturer, multi-Site production integration remains
separate and is **NOT_IMPLEMENTED** here.

## New generic prototype entry

`scripts/plasma_wordport_program.py` replaces revision-specific *selection*
for subsequent experimental Jobs. The older
`scripts/plasma_native_wordport_v02.py` is retained as historical v0.2
evidence/rollback baseline; do not use that version-pinned entry for new
general programming work.

Supported input is currently **raw BIN only**, starting at Main Flash base.
`--firmware` is a Z2 absolute local file path, selected by each Work Order.
`--image-sha256` is mandatory for any operation accepting an image and
must originate from the owner-approved Programming Asset, **not** be obtained
by trusting the same file on Z2 at execution time. The checked file is staged
in a 0700 per-run evidence folder as a 0400 read-only snapshot and checked
again before OpenOCD uses it. No image is required for `reset-run` or
`diagnose-after`.

Current physical Provider admission is strictly:

- `--icpn STM32F103C8T6`, `--site-id 1`.
- Z2 PS OpenOCD 0.12.0 `target/stm32f1x.cfg`; Main Flash 0x08000000,
  64 KiB, 1 KiB erase pages, 2-byte program granularity. Under the
  currently reviewed physical range policy, erase may cover **at most
  the first 62 pages** (0xF800 bytes); the last two pages stay untouched.
- Already verified Z2 Boot ID/Root Guard, held tested FPGA image/Golden,
  exact Native C bridge SHA, owner MMIO exclusivity, real operator
  attestation of 3.3V/common ground/pins.
- **No** alternative IC, bank, arbitrary CFG, higher Site ID, mass erase,
  raw Tcl injection or automatic image-format conversion is admitted.
  A new target requires a separately reviewed qualified Provider/profile.

The engine derives `image_bytes` from the selected staged file,
verifies its independent SHA-256 and checks 2-byte alignment and range.
Erase length = `ceil(image_bytes / erase_page_size) * erase_page_size`
and must remain within the target's qualified Main Flash range.
The engine performs one Erase, one Program, one Verify and a separate
**exact image-byte-count** Readback/SHA comparison. A successfully
programmed image is left halted: no implicit reset or retry.

Examples of dynamic erase planning (not baked into runtime):

| Image example | Size | Pages | Erase length |
| --- | ---: | ---: | ---: |
| Earlier v0.1 CDC BIN | 18,768 | 19 | 0x4C00 |
| Earlier v0.2 CDC BIN | 62,800 | 62 | 0xF800 |
| Another valid 8,194-byte BIN | 8,194 | 9 | 0x2400 |

A full 64-KiB image is **rejected** by the current Site 1 profile:
the previous independent backup showed non-erased content in page 63.
Neither caller-supplied length nor user-attested electrical safety can
silently expand the approved erase boundary. A separately reviewed
profile/operation may later extend this range with explicit backup and
recovery evidence. No assumption of preserved bytes *inside* the
computed erase range is made.

## Example — owner-approved SWPC Path 2 CLI

First install **identical reviewed entrypoint bytes** on SWPC and Z2,
according to the current approved Gate/privileged change process. The
source SHA identifies this exact reviewed execution code, not the firmware.

```bash
S=scripts/plasma_wordport_program.py
SCRIPTSHA="<reviewed exact SHA256 of this script>"
Z2_IMAGE="/absolute/path/on/Z2/chosen-firmware.bin"
IMAGE_SHA="<independent SHA256 from approved Programming Asset>"

python3 "$S" --role swpc --operation preflight \
  --icpn STM32F103C8T6 --site-id 1 \
  --firmware "$Z2_IMAGE" --image-sha256 "$IMAGE_SHA" \
  --source-sha256 "$SCRIPTSHA"

python3 "$S" --role swpc --operation program \
  --icpn STM32F103C8T6 --site-id 1 \
  --firmware "$Z2_IMAGE" --image-sha256 "$IMAGE_SHA" \
  --source-sha256 "$SCRIPTSHA" --owner-attested
```

For the existing `path2-cli` Work Order:

- `capability: operator-cli`, `scope: guarded-hardware`, a pinned
  exact PR HEAD, `script: scripts/plasma_wordport_program.py`, exact
  `argv` and bounded `timeout_seconds: 900`.
- Reuse the existing **non-root SWPC Runner**, enrolled SSH/sudo to Z2,
  protected Root source and validated installed runtime; no new fixed
  Stage/Runner/Adapter or generic sudo permission.
- `--role swpc` is the high-level coordinator only. OpenOCD always runs
  **on Z2 PS**; live per-bit SWD never transits the SWPC network.
- A source hash, file path and image hash alone do **not** authorize
  hardware use. The reviewed operation scope and qualified hardware
  conditions remain independently mandatory.

For a second image, submit a **new Work Order** with the alternate
`--firmware` and independently approved `--image-sha256`. The code,
target configuration and FPGA Image do not change. Each command is
one explicit attempt; there is no implicit alternating/retry loop.

## Evidence, failure and limits

New per-run records are isolated from the historical v0.2 results:

```
<Z2_NATIVE_BUNDLE>/.work/native-wordport-path2/run-*/
    program-image.bin         # immutable checked snapshot, program only
    openocd.tcl
    openocd.log
    bridge.log
    readback-image.bin        # if dump completed
    receipt.json
```

The receipt records the exact ICPN/Site, Image SHA and length, computed
erase bytes, OpenOCD/Bridge exits and readback SHA. PASS requires both
OpenOCD and Bridge normal exit plus the full independent readback hash.
Flash Loader timeout captures the already-reviewed post-error snapshot
without automatic retry or reset.

CI covers two historical image lengths and a third unrelated length,
hash/size/geometry/alignment negatives, a private staged-image mock
session and no implicit flash for reset/diagnosis. It does not prove
generic STM32 silicon, USB CDC behaviour, other vendor support, or 8-Site
parallelism. Those need their own explicit hardware gates.

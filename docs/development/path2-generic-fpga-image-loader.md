# Historical Path 2 Root Work Order — retained Protected Root Entry (PR #1167 / Issue #1168)

> **2026-10-26 retirement note:** The former `z2-root-operation` Work Order
> with `download|test|restore` is no longer admitted by the current Path 2
> Dispatcher. The independent protected FPGA image Root Entry and tested Golden
> recovery code remain in the repository; any actual Z2 installation, source
> pin and OS authority must be verified on that device before use.
> Current general Path 2 Work Orders use `capability: operator-cli` without a
> fixed operation list or F1-B Project binding. All F1-B PASS data below are
> *historical*, not evidence of Blue Pill SWD or current hardware readiness.
> **HISTORICAL WORK ORDER ONLY — NOT A CURRENT DISPATCHER CONTRACT.**
> The Dispatcher rejects `z2-root-operation` with
> `RETIRED_PATH2_ROOT_OPERATION`. The two-argument Protected Root
> Entry is a separate, guarded FPGA image lifecycle/recovery tool. A
> `operator-cli` script may explicitly invoke a reviewed protected tool only
> when independently authorized and permitted by actual OS, source-pin,
> ownership and recovery checks; a Work Order grants no implicit Root access.


**Historical verified status (2026-10-25):** PR #1167 was merged into `main`.
Operator SSH deployment and its F1-B Download → 3-read MMIO Test →
Golden Restore all passed on the real PYNQ-Z2. The *independent*, trusted
Path 2 Dispatcher → SWPC Runner → Z2 Root sequence then passed in
[Issue #1168](https://github.com/physicslu/plasma/issues/1168):
[Download Run 40206257358](https://github.com/physicslu/plasma/actions/runs/40206257358),
[Test Run 40206377161](https://github.com/physicslu/plasma/actions/runs/40206377161),
[Restore Run 40206484938](https://github.com/physicslu/plasma/actions/runs/40206484938).
All three actual Root receipts shared Boot ID
`4cefdc0c-f586-4d19-b126-1d8e1108c8f1` and exact trusted source SHA
`b807f1ac727209cfe1d09e9d2d31a302039e523a`. These are **F1-B
physical results only**. They do not qualify OpenOCD, Blue Pill flash,
new FPGA Programmer IPs, or a general eight-Site product image.

## Retired Work Order execution boundary (historical, not current)

In the 2026-10-25 historical implementation, the owner-authenticated
Dispatcher admitted Path 2 requests with `capability: z2-root-operation`,
`scope: guarded-hardware` and one `operation: download|test|restore`.
That **Dispatcher admission is retired**. The live Work Order parser rejects
the obsolete capability and operation field; it does not delegate a fixed
Download/Test/Restore Stage or a privileged Root call.

```text
HISTORICAL ONLY: owner-pinned Path 2 z2-root-operation Work Order
 -> trusted-main Development Dispatcher (B1)
 -> existing SWPC Runner and enrolled, pinned SSH/sudo transport
 -> existing /usr/local/libexec/plasma/z2-path2-root-entry
 -> code-selected reviewed hardware implementation (B2)
 -> exact Z2 boot/image/result receipt (B3)
```

**Current Path 2:** Owner/SHA-pinned `operator-cli` Work Orders select a
reviewed repository Python `script`, `argv` and bounded
`timeout_seconds` with `scope: guarded-hardware`; the trusted Dispatcher
runs that script on the non-root SWPC Runner. It does **not** call the Root
Entry automatically, select a fixed Stage/Profile or provide sudo authority.
The independent protected Root executable retains its own two positional
arguments, `<download|test|restore> <reviewed-40-hex-git-sha>`, and all
effective OS, source-pin, image/Manifest, lock and recovery protections.

### Provenance without a runtime Profile

The Root Entry no longer reads `.plasma-path2-profile`. The installed tree
remains `/root/plasma-path2-approved`, root-owned and not writable by other
accounts. It contains `.plasma-path2-source-sha256`, which must hash-pin all
installed Python files **and** one root-owned
`.plasma-path2-source-commit` containing exactly one reviewed 40-hex Git
commit SHA plus newline. This file is a scalar source pin, not a Project,
Stage or driver-selection Profile. The Root Entry requires that the Work
Order source SHA exactly equals this installed pin. It rejects unpinned
files, symlinks, `.pyc`, unsafe ownership/permissions and any manifest
mismatch before executing the code-selected handler.

The current two-argument Root Entry directly selects
`pl.hil.fpga_image_root` (with `fpga_image_guard` and
`fpga_image_admission`), not the historical
`pl.hil.path2_f1b_minimal_stage` module. This implementation verifies the
companion FPGA Image Manifest, source provenance, exclusive ownership,
current-boot state, Identity/MMIO checks and guarded recovery. Existing
physical acceptance evidence remains limited to Site 1 F1-B; it is not
Blue Pill Flash qualification or a general Programmer-IP execution grant.
Neither Stage nor Project/Profile selection is part of the live Root interface.

## Operator SSH one-command Deploy + Smoke Test (PR #1167)

This is **not GitHub Actions**, and it does **not** introduce a Stage/Profile
or Root framework. It runs only when an operator explicitly invokes it on
SWPC from a trusted interactive SSH terminal. The historical operator
run passed on real Z2 on 2026-10-25, **before the separate Path 2 HIL**.

The original operator one-command SSH script was exercised with the
**exact reviewed PR HEAD** `b1aa93f8487952188613d349211c0e2a4dfaa621`
and returned `DEPLOY_PASS`, Download PASS, Test PASS (3 MMIO reads,
0 writes) and Restore PASS. After the merge, the source-pinned installed
Root tree was separately aligned and read-only verified against the
**merge SHA** `b807f1ac727209cfe1d09e9d2d31a302039e523a`
(`PIN_VERIFY_PASS`). The original PR-head checkout command is **historical
evidence, not a repeatable current-main deployment procedure**. Do **not**
rerun it to overwrite the installed trusted-main Root or silently roll its
pin backward.

For any subsequent deployment, independently verify the then-current
trusted-main Git Tree, exact root source pin and complete SHA256 manifest,
root ownership, active FPGA Manager image/recovery, exclusive device
ownership and the current Boot ID. A new `main` commit (even docs-only)
advances Git HEAD but **does not automatically update the installed Root
source pin**. Any later explicit protected Root call must supply a separately
authorized exact SHA matching the installed reviewed source; perform a
safely checked source-pin migration only when actually required. Never
bypass the Root Entry SHA match.

The Z2 installer requires root, ARMv7 Python 3.12.13, FPGA Manager
`operating`, the **observed last Manager firmware load of `base.bin`**,
prior checkpoint status `BASE` (if present), and exact base/candidate firmware
SHA256. Unknown or unverifiable Golden-image status is a **hard stop**;
there is no assumption based solely on the FPGA Manager `operating` flag.
It installs the reviewed source with a complete SHA256 manifest and an exact
Git commit scalar pin, retains a backup of the old protected source tree,
and installs the existing two-argument Protected Root Entry. It does not add
a service, Work Order, Runner, Stage Orchestrator, or runtime Project Profile.

The single SSH invocation then runs these existing Root operations:
`download` -> `test` (three MMIO reads, zero writes) -> `restore`
(Golden `base.bin`). Each operation must have an exact on-Z2 receipt and
the same Boot ID. A failed Download/Restore does not blindly retry. If Test
fails, guarded Restore may be attempted **only** if the persistent root-owned
checkpoint still reports the same verified Boot ID and `F1B` held state;
otherwise manual review is required. Console output is also written under
`~/.local/state/plasma/` on SWPC with directory permission `0700`.
Never interpret the installer returning as a physical PASS unless the final
line explicitly states `RESULT=PASS`.

This historical smoke was **F1-B Site 1** programming-image verification, not SWD flashing:
no OpenOCD, Blue Pill erase/program/readback, or DUT power commands.
The active Root implementation is `pl.hil.fpga_image_root`; the historical
`path2_f1b_minimal_stage.py` remains in the repository but is not selected by
the two-argument Root Entry. The receipt key `stage` is retained for
compatibility with existing receipt validation; it is **not** Stage/Profile
admission. Renaming the compatibility key requires a separate caller/test audit.

### Explicit limitations

- The operator must have effective SSH and interactive sudo access. No
  credential is stored or copied by the script.
- A missing dmesg Golden-image observation causes `DENIED`, even if the
  system appears functional. Do not bypass it merely to obtain a PASS.
- Updating a protected Root program is a real deployment; it must be run
  only by an operator who has authorized the exact code version and accepts
  the current FPGA recovery conditions.
- GitHub-hosted CI only checks syntax and fail-closed source contracts.
  Running the above commands is necessary for real SWPC/Z2 evidence.
- The historical SSH command did not itself merge #1167 or activate the
  GitHub Runner. #1167 was subsequently merged at Gate 2 and separate
  authentic Path 2 Runner HIL passed as recorded in #1168.

### Migration / deployment boundary

Migrating an already installed Z2 Root Entry requires an explicit separate
deployment operation: atomically install matching protected Root code and the
new source-commit pin, regenerate and independently verify the complete
SHA256 manifest, and verify source/tree ownership and the existing recoverable
FPGA image before use. The old three-argument Root Entry is **not**
supported by the revised source. If installed host code and Z2 code differ,
fail closed; never retry a partially completed FPGA write blindly.

For current Work Orders, use the generic `operator-cli` boundary above.
The old four `z2-path2-download/testing/restore/full-hil` fixed IDs,
`path2-stage-contract`, Stage Orchestrator, runtime Project Profile and
Stage CI admission remain retired. Other PLASMA programming and socket
profiles are unrelated and retained.

### Evidence and limits

GitHub-hosted tests check Work Order fail-closed parsing, exact SHA and owner
authorization, Root syntax, SSH/sudo failure categories, safety receipts and
host-only build qualification. **Actual F1-B** Z2 Download/MMIO/Restore was
separately proved by the three Issue #1168 real self-hosted Runner receipts,
not those host-only checks. The test Root code checks `read32_count == 3`
and `write32_count == 0` before returning `IDENTITY_PASS`; the *sanitized
GitHub receipt* contains `IDENTITY_PASS` but does **not** directly include
the read/write counters. No physical Blue Pill DPIDR, Erase, Program,
Verify, Readback, eight-Site HIL or additional IP admission is claimed.
No new Root executor, Runner, Workflow or privilege grant.

## Generic FPGA Image Deployment — AP / PS / PL boundary

**First principle:** the protected PS deployer is an image verifier and
loader, **not** a repository of per-IC or per-Programmer-IP handlers.
The currently verified F1-B handler is a migration baseline, not the
intended universal handler architecture.

| Layer | Responsibility | Does *not* establish |
| --- | --- | --- |
| AP / release pipeline | Qualify build, supported board/FPGA part, image/ABI/IP capability matrix and release authorization. Provide a reviewable, immutable authorized manifest | Its assertion alone is not trustworthy unless authenticated |
| PS / existing Protected Root | Authenticate an explicitly trusted, approved manifest (e.g. protected root-owned allowlist or cryptographically verified publisher); check exact BIN SHA256, Board/FPGA part, ABI/identity expectation, current exclusive ownership and recoverable Golden; use the **existing Linux FPGA Manager** | SHA256 alone is not authorization; PS does not implement every IP's programming algorithm |
| PL / loaded Image | Expose deterministic Identity, ABI, Build/Image ID, Site Bitmap and capability words; PS compares values to the **pre-authorized expectation** after load | Self-reported registers are not cryptographic image authentication |
| Programming Engine | Use the selected, already-admitted Site and protocol controller to execute SWD/SPI/JTAG target operations with independently qualified target algorithm and electrical conditions | Target DPIDR/Erase/Program/Verify/Readback is not an FPGA Manager download stage |

**Normal operation:** when one approved integrated/Universal Image is loaded,
individual IC programming Jobs must **not** reload the FPGA. Reconfiguration
is an explicit boot/update/maintenance lifecycle operation, not a per-Site
job. Image metadata is a small fixed record per approved release, not an
enumeration of every device, manufacturer or programming operation.

### Evidence-based current compatibility

| Source / Image | Qualification | Runtime status |
| --- | --- | --- |
| F1-B Site 1 fixed Image | Real Z2 Download, 3 read32 / 0 write32 Identity, verified Golden Restore in [#1168](https://github.com/physicslu/plasma/issues/1168) | **Qualified for its existing protected F1-B path only** |
| `FixedABIHardwareDriver` / `FixedABISWDController` Site 1 | Reviewed source plus host/RTL tests; native Z2 ARMv7, exact compatible configured Image, DUT electric and physical Flash tests **NOT_RUN** | **Not admitted**; existing controllers are reusable *outside* FPGA deployment |
| Fixed ABI dual-Site RTL | Host Cocotb and virtual-SWD coverage; no qualified physical Site 2 image | **Not admitted** |
| `pl.hil.swd04` and [PR #1142](https://github.com/physicslu/plasma/pull/1142) Blue Pill remote bitbang | Offline/HIL-read-only evidence; physical Blue Pill Flash **NOT_RUN**; #1142 old 3-arg Root/Profile conflicts with merged 2-arg Root | **Not admitted** |

### Smallest implementation, without a second framework

1. Retain the existing **two-argument** Root Entry:
   `download|test|restore + reviewed Git SHA`, all root-owned source
   pin/manifest, Lock, current-boot and Golden recovery checks.
2. The active `pl.hil.fpga_image_root` consumes a companion FPGA Image
   Manifest, verifies the BIN SHA256 and applicable Board/FPGA requirements
   before the protected load, and keeps Root executable source pinning
   separate from Image data. Do not revive a per-Image approval token,
   fixed release allowlist or new Root code pin for each Image.
3. After Manager download, compare observed PL Identity/ABI against the
   companion Manifest and enforce current-boot ownership/recovery checks.
   Preserve F1-B identity acceptance without claiming untested capability
   words, Blue Pill Flash or other Image HIL qualification. A valid SHA256
   demonstrates consistency, not publisher authorization; a safe functional
   test failure alone does not mandate Golden Restore.
4. **Do not** add an IP-specific Python Root handler or runtime
   `module/project/image` selector. A new Programmer IP needs its
   own admitted protocol controller and physical evidence, but does not
   require a second FPGA loader.
5. Do not label a new image or Site as real **HIL PASS** before a separate
   approved physical image/ABI/electrical/target qualification. Host-only
   contracts and #1168's F1-B receipts cannot grant new privileges.

**Source-lock warning:** merging even a documentation-only PR advances
the exact trusted-main Git SHA; any later *explicit protected Root call*
must use the reviewed SHA expected by the installed Z2 Source Pin/Manifest. A
Git Tree match is evidence of identical contents, but **does not** bypass
the currently enforced exact commit pin. Do not roll the Z2 back to a
historical #1167 PR HEAD.

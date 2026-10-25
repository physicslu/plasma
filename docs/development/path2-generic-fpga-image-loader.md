# Path 2 — Direct CLI to existing Protected Z2 Root Entry (merged PR #1167)

**Verified status as of 2026-10-25:** PR #1167 is merged into `main`.
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

## Execution boundary

The existing owner-authenticated Development Dispatcher and shared Work Order
admission accept Path 2 hardware requests with **capability
`z2-root-operation`**, `scope: guarded-hardware`, and precisely one
`operation: download|test|restore`. No Stage, Project or Profile field is
accepted, and no fixed Stage Task ID is registered. There is no chained
full-HIL automation or arbitrary shell/SSH command.

```text
owner-pinned Path 2 Work Order
 -> trusted-main Development Dispatcher (B1)
 -> existing SWPC Runner and enrolled, pinned SSH/sudo transport
 -> existing /usr/local/libexec/plasma/z2-path2-root-entry
 -> code-selected reviewed hardware implementation (B2)
 -> exact Z2 boot/image/result receipt (B3)
```

Only two fixed positional Root Entry arguments are supported:
`<download|test|restore> <reviewed-40-hex-git-sha>`.

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

The current bounded proof-of-concept Root handler remains
`pl.hil.path2_f1b_minimal_stage` for Site 1 F1-B operations. Its
historical module name does **not** mean a Stage Orchestrator or Profile is
in the execution path. Its existing image identity, FPGA ownership/lock,
B1/B2/B3 scope checks, in-flight state, MMIO child checks and recovery
obligations must remain intact. This refactor does **not** turn that handler
into a generic Blue Pill SWD backend; such functionality requires a separate
reviewed implementation and actual HIL validation, not a freeform module
selector or new runtime Profile.

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
changes the exact SHA requested by a post-merge Path 2 Work Order: perform
a separately authorized, safely checked source-pin migration rather than
bypassing the Root Entry SHA match.

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

This is a current **F1-B Site 1** programming-image smoke, not SWD flashing:
no OpenOCD, Blue Pill erase/program/readback, or DUT power commands.
The existing internal handler file still has historical `minimal_stage`
naming and receipt field `stage`; it directly implements FPGA Manager,
MMIO and recovery. These historical names **do not** authorize an external
Stage Orchestrator or Project Profile. Renaming them is not a prerequisite
for removing the original blocking architecture.

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

For a new Direct Work Order the old four `z2-path2-download/testing/restore/
full-hil` fixed IDs, `path2-stage-contract`, Stage Orchestrator, runtime
Project Profile and Stage CI admission are retired. Other PLASMA programming
and socket profiles are unrelated and retained.

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

## Programmer IP extension boundary (source reviewed ≠ hardware admitted)

The existing F1-B handler `pl.hil.path2_f1b_minimal_stage` is a
**protected FPGA image + identity/Golden recovery fixture**, not a universal
IC programmer. The two-argument Root Entry and its `download|test|restore`
allowlist deliberately govern the **FPGA configuration lifecycle**.
They must not become a freeform `module`, `project`, `script`, `image`
or arbitrary peripheral-IP selector. Programming an MCU is a separate
reviewed **protocol/target operation** requiring actual site admission,
electrical/DUT identity and target-specific qualification.

| Existing reviewed code | Verified level | Permitted Root execution today |
| --- | --- | --- |
| `pl.hil.path2_f1b_minimal_stage` / Site 1 F1-B image | **Real Z2 HIL PASS**: Image Download, 3-read/0-write Identity, Golden Restore (#1168) | **YES**, existing fixed handler only |
| `FixedABIHardwareDriver` + `FixedABISWDController` / Fixed ABI SWD Site 1 | Source and Host/RTL integration; physical PYNQ-Z2 image/ARMv7 MMIO/barrier, DUT electrical and Flash HIL **NOT_RUN** | **NO**: no reviewed, installed, root-authorized hardware provider |
| Dual-Site Fixed ABI SWD RTL (Site 1 / Site 2) | Host-only Cocotb/virtual SWD qualification; no Site 2 physical Z2 image **NOT_RUN** | **NO** |
| `pl.hil.swd04` / earlier SWD transaction pipeline | Source/offline candidate and isolated verification; its image/protocol evidence is **not** the F1-B #1168 physical image | **NO** |
| [PR #1142](https://github.com/physicslu/plasma/pull/1142) Blue Pill Remote Bitbang candidate | Unmerged Draft; old Root 3-argument/Profile contract conflicts with merged #1167; real Blue Pill DPIDR/Flash **NOT_RUN** | **NO** |

**Minimum qualified extension path, without another Framework or Stage/Profile:**

1. Reuse the existing protocol-neutral `FixedABIHardwareDriver` and
   `FixedABISWDController` (or another already-reviewed controller) above
   an explicitly admitted native MMIO port; do **not** duplicate protocol
   engines inside Root.
2. Bind an immutable reviewed FPGA image, actual on-PS image/ABI identity,
   registers and Site ID to the same installed root-owned source SHA +
   manifest/ownership/lock controls, with verified Golden recovery. Confirm
   voltage, isolation, DUT ownership and target-specific operation
   qualification **before allowing any physical command**.
3. Only after a real qualified Programmer IP exists, implement the **smallest
   fixed, reviewed code binding** from protected hardware ownership to that
   existing provider. Its target/verb authorization must be explicit and
   fail-closed; no caller-supplied Python module or runtime Profile. Preserve
   the working F1-B entry, operation ABI and #1168 regression.
4. Prove physical Probe/DPIDR, Erase, Program, Verify, independent Readback
   and Golden recovery for the specific IP/DUT and Source SHA. Only then
   mark that additional IP **HIL PASS**; Host CI/virtual SWD does not qualify it.

**Current outcome:** #1168 proves only the F1-B Root. No additional
Programmer IP is authorized for privileged live execution by this
documentation/qualification inventory alone. Implementing a live non-F1-B
provider without the missing hardware/image/electrical facts would defeat
the reviewed B1/B2/B3 safety and false-label an unqualified IP.

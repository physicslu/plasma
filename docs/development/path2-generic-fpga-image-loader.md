# Path 2 — Direct CLI to existing Protected Z2 Root Entry (PR #1167)

**Gate 1 source refactor; GitHub-hosted offline evidence only.** The source
on a Draft PR is not installed on SWPC or PYNQ-Z2. Z2 install, FPGA Manager,
MMIO, OpenOCD, DUT execution and Golden Restore remain **NOT_RUN**.

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
SWPC from a trusted interactive SSH terminal. **No command has been run on
the actual Z2 by this PR.**

One-time preparation: make the PR #1167 working branch or the reviewed script
available in a dedicated SWPC checkout (do not change the checkout of a
running shared Runner), and verify the existing SWPC-to-Z2 SSH alias,
operator's pinned SSH host key, and working interactive `sudo`.

```bash
# On SWPC, in the reviewed PR #1167 checkout:
cd ~/plasma
bash scripts/plasma-z2-smoke.sh --target xilinx@<verified-z2-ssh-name> --plan

# Deliberate physical deployment and HIL (no Blue Pill operations):
bash scripts/plasma-z2-smoke.sh --target xilinx@<verified-z2-ssh-name>
```

The `--plan` option fetches the current exact GitHub PR #1167 HEAD and
constructs/verifies a minimal source bundle **without SSH or hardware**.
The real command also performs preflight and transfers the verified bundle.
Both commands fetch `refs/pull/1167/head` from the canonical
`physicslu/plasma` origin. A Git SHA is printed; it is **not** taken from
whatever files happen to be locally edited or checked out.

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
- This command deliberately does not change `main`, merge PR #1167, or
  activate the GitHub Runner; keep PR #1167 Draft until Gate 2 approval.

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
host-only build qualification. They do not prove any installed Z2 version,
live hardware state, voltage, bitstream compatibility or physical IC
programming. In particular **no actual F1-B, OpenOCD or Blue Pill PASS**
is claimed. No new Root executor, Runner, Workflow or privilege grant.

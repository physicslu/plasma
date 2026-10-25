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

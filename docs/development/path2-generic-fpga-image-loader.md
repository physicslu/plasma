# Path 2 / Path 3 — existing Z2 trusted Root Entry

**Gate 1 implementation Draft; no root installation or hardware activation.**

The existing Work Order, trusted-main Dispatcher, SWPC Runner and Stage
Transport remain the Path 2 fixed-CLI execution route. Path 3 lets Codex
choose commands under the same Gate 1 and OS permissions, but **generic
privileged Z2 Stage delegation from Path 3 is not yet installed**. Both
paths must use the existing protected Root authority and preserve
B1/B2/B3 for any privileged Z2 operation. No new Path 3 route is added.

The protected Root Entry source is now
`scripts/z2/plasma-path2-root-entry`, installed path
`/usr/local/libexec/plasma/z2-path2-root-entry`. The old
F1-B-named Root Entry is removed from the **candidate source**, not
uninstalled from the live Z2.

The new entry binds exactly three fixed arguments:
`download|test|restore`, authorized project name and pinned Git SHA.
It reads one **root-owned, SHA256-manifest-pinned active project**
from `/root/plasma-path2-approved/.plasma-path2-profile` with
exactly three newline-terminated lines:

```text
pl/projects/z2-fixed-unified-site1
pl.hil.path2_f1b_minimal_stage
<reviewed 40-hex Git source SHA>
```

The example is **not an installed profile**. The authenticated source
manifest must enumerate the profile, selected Python module, **every**
installed Python source, existing FPGA safeguards and Linux MMIO driver.
The entry refuses unpinned Python dependencies, import-tree symlinks or
non-root-owned/writable directories, preserving the old F1-B dependency
pinning without hardcoding F1-B in the execution framework. Caller-provided paths, modules
and shell commands are rejected. This is a single per-Z2 installed
project selection, not another registry, service or Root Executor.

The existing F1-B Python module remains only as project-specific HIL
implementation; it emits the now-shared receipt marker
`PLASMA_PATH2_STAGE=` and the exact Project. The Stage Transport
validates that Project along with the stage, current-boot identifier
and allowlisted stage result. A prospective Blue Pill SWD DPIDR
backend must implement its own independently verified target safety;
it cannot inherit F1-B's Development-only risk exception.

**Non-negotiable:** the installed Root Entry and Project module must
independently enforce hardware ownership, AXI isolation, reliable
current-boot image and recovery evidence, process/FPGA lock and electrical
limits. A root-owned file manifest and CI green check cannot prove
physical safety. Root installation and Z2 hardware operation remain
**NOT_RUN**. This Draft must not be merged until Gate 2.

## Scope reduction

The earlier PR #1143 `generic_image_loader`,
`generic_held_binding`, `generic_root_preflight` wrappers and their
three test modules were removed. They were source-only abstractions not
connected to the existing trusted Root execution path. The retained
change directly edits only existing trusted code and the existing Root
Entry source, with no new Runner, Workflow, SSH path, sudo capability or
alternative image loader.

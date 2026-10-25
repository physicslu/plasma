# Path 2 / Path 3 — existing Z2 trusted Root Entry

**Historical Gate 1 implementation record (originally Draft); no Z2 installation or hardware activation is proven by this document.** Source being on `main` does not attest to which Root files are currently installed on Z2.

The existing Work Order, trusted-main Dispatcher, SWPC Runner and Stage
Transport remain the **Path 2 fixed-CLI Stage execution route**. In Path 3,
Codex selects the engineering method under the owner-approved Gate 1 and
real OS permissions; **Path 2's fixed Stage, Project Profile and this Root
Entry are not universal Path 3 prerequisites**. Codex may use enrolled Z2
SSH/sudo and existing tools within approved scope. If it elects to use this
Root Entry, its installed source/profile/manifest validations apply as
implemented. There is still **no verified generic Path 3 dynamic privileged
Stage delegate** installed by this historical change; preserve B1/B2/B3,
image identity, hardware ownership and recovery for any real operation.

The protected Root Entry source is now
`scripts/z2/plasma-path2-root-entry`, installed path
`/usr/local/libexec/plasma/z2-path2-root-entry`. The old
F1-B-named Root Entry is removed from the **candidate source**, not
uninstalled from the live Z2.

The trusted-main Path 2 *dynamic* Work Order now admits the same
bounded project-name syntax as Stage Transport and Root Entry, instead of
accepting only the historical F1-B name. This does **not** authorize the
project on Z2: the independently root-owned installed project, pinned
SHA, image/recovery and B1/B2/B3 guards must still match. Historical fixed
F1-B Task IDs remain restricted to their original project; Path 3's
privileged dynamic delegation is not added here.

The entry binds exactly three fixed arguments: a bounded stage token,
authorized project name and pinned Git SHA. The root-installed project
module decides which stage tokens it implements. The existing F1-B module
still admits only `download|test|restore`.

The entry reads a **root-owned, SHA256-manifest-pinned project profile**
from `/root/plasma-path2-approved/pl/projects/<project>/.plasma-path2-profile`
when that file is installed. Otherwise it retains the legacy
`/root/plasma-path2-approved/.plasma-path2-profile`. Each profile has
exactly three newline-terminated lines:

```text
pl/projects/z2-fixed-unified-site1
pl.hil.path2_f1b_minimal_stage
<reviewed 40-hex Git source SHA>
```

The example is **not an installed profile**. A project profile is part of
the same installed root-owned source closure; it does not replace the F1-B
profile or create a second executor. The authenticated source
manifest must enumerate the profile, selected Python module, **every**
installed Python source, existing FPGA safeguards and Linux MMIO driver.
The entry refuses unpinned Python dependencies, import-tree symlinks or
non-root-owned/writable directories, preserving the old F1-B dependency
pinning without hardcoding F1-B in the execution framework.
Every installed regular source file must also be root-owned and not writable
by other accounts. Cached Python bytecode (`.pyc`/`.pyo`) is rejected and
bytecode generation is disabled for the stage and its child processes. Caller-provided paths, modules
and shell commands are rejected. The requested project is passed to the
installed module through `PLASMA_ROOT_PROJECT`; it does not select code.

The existing F1-B Python module remains only as project-specific HIL
implementation; it emits the now-shared receipt marker
`PLASMA_PATH2_STAGE=` and the exact Project. The Stage Transport
validates that Project along with the stage, current-boot identifier
and allowlisted stage result. A prospective Blue Pill SWD DPIDR
backend must implement its own independently verified target safety;
it cannot inherit F1-B's Development-only risk exception.

The candidate `pl.hil.fpga_configuration_policy` module supports a
read-only `audit` request for any manifest-pinned project descriptor. Its
receipt is `READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION` and explicitly denies
hardware-write authority. Its `download`, `test` and `restore` live backend
remains unavailable until current ownership, image identity and recovery
admission are independently established. An audit receipt must not be
reported as an FPGA load or programming result.

**Non-negotiable:** the installed Root Entry and Project module must
independently enforce hardware ownership, AXI isolation, reliable
current-boot image and recovery evidence, process/FPGA lock and electrical
limits. A root-owned file manifest and CI green check cannot prove
physical safety. Root installation and Z2 hardware operation remain
**NOT_RUN** in the historical experiment. This sentence records its original
pre-merge status, **not** a current unmerged PR or new Gate 2 requirement.

## Scope reduction

The earlier PR #1143 `generic_image_loader`,
`generic_held_binding`, `generic_root_preflight` wrappers and their
three test modules were removed. They were source-only abstractions not
connected to the existing trusted Root execution path. The retained
change directly edits only existing trusted code and the existing Root
Entry source, with no new Runner, Workflow, SSH path, sudo capability or
alternative image loader.


The shared Stage Transport deliberately does not special-case F1-B's
private error strings as generic safety/identity evidence. A project
stage failure without the exact verified Root receipt is classified
as a generic remote failure; specific diagnostic analysis belongs to
the project module and approved root-side evidence.

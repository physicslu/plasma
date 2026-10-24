# PLASMA Unified FPGA Build & Diagnostic Engine v1.0

Status: **Gate 1 Draft — offline / GitHub-hosted validation only**. This
document is a proposed implementation contract, not a claim of a new SWPC
Vivado build, physical FPGA test, or M1 qualification.

## Scope and existing implementation

This v1 reuses the already qualified F1-B Vivado 2026.1 Project Tcl, pinned
PYNQ-Z2 board helper, HWH verifier and **one** Python host build driver,
`scripts/plasma_vivado_host_build.py`. It does **not** create a second
Vivado execution pipeline, alternate Workflow, runner, hardware access route,
or deploy operation. Path 2 retains the fixed driver and its admission checks.

Path 3 accepts an owner-authenticated goal and acceptance criteria without a
scope enum, fixed builder or owner-authored hardware stage list. Codex chooses
its development tools and build commands. The former mandatory shared-driver
instruction, task-specific admission environment and historical artifact
prefetch are deleted. The reusable Path 2 driver is unchanged; it is not a
prerequisite for Path 3 builds.

The candidate workflow no longer automatically runs a hardware stage list
following Codex success. The sandbox cannot call root, SSH or MMIO. Existing
protected physical execution remains bounded by the trusted executor's actual
allowlist, image verification, ownership/recovery state and receipts. That
executor currently supports the fixed F1-B contract, so arbitrary future-image
Path 3 physical acceptance is **BLOCKED**, not proven by these source changes.
No replacement task framework or physical authorization inference is added.
These candidate changes are **NOT_ACTIVE_IN_MAIN** until reviewed and merged.

## Shared stage contract

1. `PREFLIGHT`: validate source project and reviewed Tcl, worker, exact Git
   SHA, Vivado settings, License-discovery environment presence.
2. `BOARD_PREPARE`: invoke existing SHA-pinned Board Repository helper,
   verify clean board revision and original source commit.
3. `OUTPUT_PREPARE`: create a unique writable directory inside the
   candidate worktree's ignored `pl/build`. No assumed global SWPC cache.
4. `VIVADO_IMPLEMENTATION`: source installed Vivado 2026.1 settings,
   execute the existing `build_bitstream.tcl` with a bounded timeout,
   capture stdout/stderr and SHA256.
5. `ARTIFACT_VERIFY`: existing `verify_hwh.py` qualification and SHA256
   over BIT, HWH, Timing, DRC, Methodology and check_timing evidence.
6. `EVIDENCE_WRITE`: complete the existing Host Build receipt and the
   unified diagnostic receipt.

### Path 2 License Discovery Gate 1 (candidate; no SWPC build)

The single shared driver first validates the owner/runner/source preflight,
then resolves a usable **existing** `Xilinx.lic` from the pinned installed
Vivado tools tree. It accepts a direct `XILINXD_LICENSE_FILE` or
`LM_LICENSE_FILE` only when it is the same, regular, readable license file
inside that allowlisted tree. Otherwise, with neither variable present, it
performs a bounded, non-symlink-following name-only search for exactly one
`Xilinx.lic`. It rejects missing, ambiguous, escaped, unreadable or oversized
sources with a fixed `BUILD_LICENSE_*` code.

Discovery happens in PREFLIGHT before Board checkout, build directory
creation, or Vivado invocation; only the validated `XILINXD_LICENSE_FILE`
is passed to the already existing **host-only** subprocess. No license
contents are read, copied, committed, uploaded, logged or reported. It does
not change SWPC system configuration or create a second Build Engine.

The diagnostic retains only `license_environment_present` (safe boolean).
This says **a trusted readable file was found**, not that a Vivado license
checkout succeeded. Only a separately authorized real host-only run can prove
license entitlement, synthesis/implementation and timing/DRC qualification.
The Gate 1 pull request is verified entirely with Github-hosted synthetic
positive/negative tests, never a live SWPC build.

## Evidence and first-failure semantics

Both paths use `plasma.fpga.build_diagnostics.v1`:

- `plasma-fpga-build-diagnostics.json`: ordered stage states, first failed
  stage, bounded error code, whitelisted Python exception/cause types,
  limited boolean preflight checks, artifact sizes and SHA256.
- `plasma-fpga-build-diagnostics.json.sha256`: digest of that JSON receipt.
- Existing Vivado logs, reports, BIT/HWH and Host Build receipt: only
  preserved if actually produced, never inferred from a PASS message.

`root_cause_status=CONFIRMED` is reserved for directly observed conditions
such as an output-directory permission error, read-only filesystem,
out-of-space error or missing Vivado settings. A generic command failure is
`UNKNOWN`, even if a later run happens to pass.

The diagnostic schema never includes raw exception messages, full paths,
license locations, tokens or host environment. A failure exit code remains
nonzero; it is never silently converted to PASS. Artifact availability has
a limited GitHub Actions retention period.

## Acceptance boundaries

Gate 1 must check successful and rejected stage ordering, exception
redaction, evidence digest, permission denial, license propagation, Host-only
Vivado error attribution, SWPC/Issue/PR admission spoofing, and the
existing dispatcher/Workflow negative contracts **offline**.

Only GitHub-hosted pull_request/push CI may run during this Gate 1. No
Issue #981 comment, SWPC Host Build, physical Z2/FPGA/DUT/LA/USB/MMIO/power
action or deployment is authorized. Gate 2 Merge remains separate.

A successful Host-only Build is **not** an actual hardware programming
qualification: physical load = NOT_RUN, Z2 HIL = NOT_RUN and M1 = NO_GO.

## Future extensibility, not silently claimed in v1

The shared engine currently admits the reviewed fixed F1-B project.
Other project configurations (SWD PL, multi-site PL) require separately
reviewed typed registries, toolchain/part constraints and artifact
verification. Do not call this version arbitrary-project/build-anything.

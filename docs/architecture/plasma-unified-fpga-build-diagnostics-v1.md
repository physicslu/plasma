# PLASMA Unified FPGA Build & Diagnostic Engine v1.0

Status: **Gate 1 Draft — offline / GitHub-hosted validation only**. This
document is a proposed implementation contract, not a claim of a new SWPC
Vivado build, physical FPGA test, or M1 qualification.

## Scope and existing implementation

This v1 reuses the already qualified F1-B Vivado 2026.1 Project Tcl, pinned
PYNQ-Z2 board helper, HWH verifier and **one** Python host build driver,
\`scripts/plasma_vivado_host_build.py\`. It does **not** create a second
Vivado execution pipeline, alternate Workflow, runner, hardware access route,
or deploy operation. Both approved Development Mode routes call the same
\`run()\` implementation:

- **Path 2**: trusted dispatcher validates Issue #981 authorization, exact
  source SHA, reviewed F1-B capability and worker identity; invokes the fixed
  driver through the existing \`development-execute\` job.
- **Path 3**: only the exact authorized
  \`f1b-path3-codex-vivado-build\` task receives the trusted workflow's
  scoped host-build admission variables. Codex must use the shared driver
  CLI for Host-only Vivado work rather than bypassing it with independent
  ad-hoc shell/Tcl execution. The authorized candidate checkout is an
  engineering worktree: its original HEAD remains pinned, while any source
  changes require a diff and independent evidence review.

Canonical Path 3 host-only invocation **during a separately authorized
owner-initiated Path 3 job**, never from GitHub-hosted CI:

\`\`\`bash
python3 scripts/plasma_vivado_host_build.py \
  --path3-engineering-host-only \
  --evidence-dir .plasma-path3-evidence
\`\`\`

This command fails closed without the trusted workflow admission and pinned
SHA/PR identity. A GitHub-hosted pull_request does not pass the admission.
Operator-invented environment variables are **not** an authorization method.

## Shared stage contract

1. \`PREFLIGHT\`: validate source project and reviewed Tcl, worker, exact Git
   SHA, Vivado settings, License-discovery environment presence.
2. \`BOARD_PREPARE\`: invoke existing SHA-pinned Board Repository helper,
   verify clean board revision and original source commit.
3. \`OUTPUT_PREPARE\`: create a unique writable directory inside the
   candidate worktree's ignored \`pl/build\`. No assumed global SWPC cache.
4. \`VIVADO_IMPLEMENTATION\`: source installed Vivado 2026.1 settings,
   execute the existing \`build_bitstream.tcl\` with a bounded timeout,
   capture stdout/stderr and SHA256.
5. \`ARTIFACT_VERIFY\`: existing \`verify_hwh.py\` qualification and SHA256
   over BIT, HWH, Timing, DRC, Methodology and check_timing evidence.
6. \`EVIDENCE_WRITE\`: complete the existing Host Build receipt and the
   unified diagnostic receipt.

License environment variables \`XILINXD_LICENSE_FILE\` and
\`LM_LICENSE_FILE\` are propagated **only if provided**. The diagnostic
contains a boolean \`license_environment_present\`, never their values.
This boolean is **not** a license checkout or entitlement test; actual
Vivado execution remains the authoritative License/Toolchain test.

## Evidence and first-failure semantics

Both paths use \`plasma.fpga.build_diagnostics.v1\`:

- \`plasma-fpga-build-diagnostics.json\`: ordered stage states, first failed
  stage, bounded error code, whitelisted Python exception/cause types,
  limited boolean preflight checks, artifact sizes and SHA256.
- \`plasma-fpga-build-diagnostics.json.sha256\`: digest of that JSON receipt.
- Existing Vivado logs, reports, BIT/HWH and Host Build receipt: only
  preserved if actually produced, never inferred from a PASS message.

\`root_cause_status=CONFIRMED\` is reserved for directly observed conditions
such as an output-directory permission error, read-only filesystem,
out-of-space error or missing Vivado settings. A generic command failure is
\`UNKNOWN\`, even if a later run happens to pass.

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

# Path 2 capability policy — reviewed fixed host builds

Path 2 is a **fixed CLI execution mechanism**. It is not conceptually tied to
`cpu-only` and a Python-only `scripts/experiments/*.py` script.

The original 2026-10 Development Dispatcher hardcoded CPU-only in
`task_by_id`, `authorize`, `execute` and the common Workflow job's
`if` condition. This repository-specific policy was not imposed by GitHub or
Vivado. It is now replaced with a typed capability route:

- `cpu-only`: unchanged bubblewrap, Python -I -S, 40s and output digest.
- `z2-cpu-only`: unchanged exceptional A2 one-shot hardware Claim.
- `vivado-host-build`: fixed **host** CLI via the existing Development
  Task registry. Owner-created Issue #981 commands may name either an exact
  trusted main SHA or an **open, same-repository, owner-created PR HEAD**
  whose immutable SHA exactly matches the command and live GitHub metadata.
  Source and trusted SHA must be different for a PR request. Reruns, wrong
  PR metadata, mismatched SHA, unknown capabilities, and arbitrary executable
  paths fail closed. No Gate 2 merge is needed merely to *qualify* a PR.

No new Workflow, GitHub self-hosted Runner or per-task Workflow exists.
The existing `development-execute` job and `SWPC-plasma-codex` Runner are
reused, with capability-dependent timeout. The trusted host build executor
uses a reviewed `pl/projects/<name>` Vivado entrypoint, pinned 2026.1
settings and board revision, fresh output directory and a finite timeout.
The Vivado project exposes no PL physical I/O. No FPGA Manager/device
programming commands, MMIO, Z2 SSH, DUT, LA, power or deployment are
permitted. Output receipts and timing/report checks are candidate evidence,
not proof of a real FPGA image being loaded or identity provenance.

The manifest entry `fixed-site1-vivado-host-build` is the reusable typed
project definition and *not* a second Work Order system.

**Gate 1:** GitHub CI is not a substitute for the actual SWPC Host Build.
Run the reviewed, fixed PR SHA on the existing Path 2 Runner after explicit
Owner approval; qualify synthesis, timing, DRC, BIT/HWH and evidence before
requesting the merge-only Gate 2. The original trusted main Dispatcher must
also have this policy revision; a PR-only edit cannot change the trusted
code that an Issue #981 event actually executes. No automatic permission to
touch FPGA Manager, Z2, MMIO, LA, DUT, power or deployment is implied.

## F1-B Path 3 diagnosis and evidence reuse — 2026-10-19 (Gate 1, PR #1064)

**Original real failure:** [Path 2 Run 39274388453](https://github.com/physicslu/plasma/actions/runs/39274388453), main `f789629060595ff98695d515eb3225fcc0a370a8`: owner authorization and SWPC checkout succeeded; actual `development-execute` stopped with exit 2 and a real receipt `NOT_RUN_OR_FAIL / EXECUTION_ERROR`. The receipt did **not** preserve the originating exception. No synthesis, implementation, BIT or HWH PASS evidence exists from this run.

**Existing Path 3 Codex / SWPC Runner, no new mechanism:**
- [Run 39276831321](https://github.com/physicslu/plasma/actions/runs/39276831321): Codex exit 0; 9 mock-based positive/negative tests PASS, eight independent evidence assertions PASS. Artifact `12197498283` includes the generated Python source, real command and output, test log, full Codex session log, SHA256 receipt and source patch. Root cause explicitly unconfirmed by offline mocks.
- [Run 39277523452](https://github.com/physicslu/plasma/actions/runs/39277523452): Codex exit 0; 17 error-mapping tests PASS and nine independent evidence assertions PASS. Artifact `12198690561` preserves the same evidence types. ChatGPT independently downloaded both Artifacts and recomputed all **8/8** component SHA256 digests; all match their respective receipts.

**Real read-only SWPC observation from Run 39277523452:** `SWPC-plasma-codex` runs with effective UID 998/GID 997. The historical fixed output root (operator-local persistent build directory; path withheld from public documentation) exists but belongs to UID/GID 65534/65534 with mode 0755; effective **write access is false**. The Vivado 2026.1 `settings64.sh` exists and is readable. The fresh candidate checkout did not contain a prepared board cache. These facts establish an actual output-path blocker **if code reaches the mkdtemp stage**; the exact first exception in Run 39274388453 is not proven because board preparation occurs earlier and the failure receipt was generic.

**Minimal reused-code repair in PR #1064:** The existing `scripts/plasma_vivado_host_build.py` continues to call the SHA-pinned `prepare-board-repository.sh`, F1-B Tcl and `verify_hwh.py`, but places its unique disposable build directory beneath the already-authorized candidate Worktree's ignored `pl/build`, instead of the unwritable persistent SWPC root. It refuses symlinks/path escapes and maps preparation timeout/launch failures and output creation permission/read-only/full-disk errors to constant `BUILD_*` codes. Existing hosted tests exercise successful path selection and fail-closed cases; **this is not evidence that the patched build has run on SWPC**.

**Boundary and reusable lesson:** Make the dispatcher dispatch a proven fixed build rather than reinventing it; take the output directory from the executable worktree, not an assumed global SWPC cache; preserve concrete stage error codes without leaking host paths; read actual runner permissions rather than inferring them from prior unrelated account builds. Existing Path 3 intentionally permits only generated-source/evidence edits, so Codex produced and tested a proposal and ChatGPT applied a reviewed minimal production patch through the PR. GitHub Actions artifacts have finite retention; do not count link existence as perpetual archival.

**State:** PR #1064 Open / NOT MERGED. F1-B fixed build on the patched code is **NOT_RUN**. Current Issue #981 trusted main dispatcher still uses merged main source; a PR code change is not automatically deployed. No extra Runner/Workflow, no FPGA load, Z2/DUT, MMIO, LA, power or deployment.

## F1-B Development Mode acceleration — 2026-10-20 (Gate 1)

The owner explicitly retired the former `f1b-path3-diagnose-39274388453` task. **Do not trigger it again.** Its original Run IDs, observations and SHA evidence above remain historical facts, not a command to repeat the old diagnosis.

Its candidate registry entry is replaced by `f1b-path3-codex-vivado-build`, a real Host-only Vivado 2026.1 engineering task. After the separately controlled trusted Dispatcher/Workflow changes in PR #1065 are merged and active, the owner-approved **Path 3 Codex engineer** may edit RTL, Tcl, Python, build scripts, and documents in the pinned candidate worktree, run actual synthesis/implementation/timing/DRC, generate BIT/HWH, diagnose failures, rerun and provide a chronological root-cause/fix/retest ledger in `.plasma-path3-evidence/engineering-report.md`. Source diffs and raw artifacts must be captured with SHA256.

This eliminates the former generated-file-only change allowlist, Python subprocess 480-second deadline and 12-minute Path 3 job deadline. The job has an operational 360-minute watchdog, not a mandated target build time. **No FPGA programming, Z2/DUT/LA/USB/MMIO/power manipulation or deployment is authorized.** These are separate from Host-only compiling.

Until actual SWPC/Codex/Vivado execution proves otherwise, synthesis, implementation, BIT/HWH, timing and DRC are **NOT_RUN**. A registry update alone is not a successful build.

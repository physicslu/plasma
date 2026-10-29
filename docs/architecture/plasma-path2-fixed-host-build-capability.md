# Path 2 capability policy — reviewed fixed host builds

> **Historical F1-B build record.** Status statements and fixed Registry
> examples below describe their dated Gate 1/PR, not the current dynamic
> Path 2 build contract. Current dynamic admission accepts trusted event
> `main` or an exact open PR HEAD for `pl/projects/<name>`; successful execution requires a
> reviewed project build contract and artifact/HWH verifier. The former
> fixed F1-B Registry Build tasks have been retired; examples below are not
> live commands. F1-B now has a project-owned `host-build.json` contract.

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

The historical manifest entry `fixed-site1-vivado-host-build` was a typed
Project definition, not a second Work Order system. It is no longer in the
live registry; use the dynamic Path 2 `vivado-host-build` Work Order.

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


## F1-B real Path 3 Build / problems and resolutions — 2026-10-20

**Executed evidence, not an offline mock:** [Actions Run 39342622512](https://github.com/physicslu/plasma/actions/runs/39342622512), SWPC `SWPC-plasma-codex`, trusted Dispatcher main
`78d3ca70f43a13523da8b6d3cdd578ec91d79b39`, candidate #1064
`92306f0b988d6546ac4d45f487fc6486d8959d51`, board-files commit
`e02d6a3866b5465218f777168cdc51344ac94e07`.
Codex exit 0 and GitHub Job SUCCESS. Independent review recovered actual
Vivado reports and the chronological report from artifact `12229802904`
(SHA256 of GitHub artifact ZIP:
`4d137b626fefa1107c81dd669e62873ffc6b6940b25c2bbad1473d136652d030`).

| Attempt / issue | Root cause / corrective action | Retest |
| --- | --- | --- |
| 01, exit 42 | Vivado executable not on PATH and License file not automatically discovered; use existing installed Vivado 2026.1 and configure existing Xilinx License via `XILINXD_LICENSE_FILE`. No license file copied or committed | Attempt 02 reached Tcl |
| 02, exit 1 | `create_block_design.tcl` compared relative string `ps7_0/FCLK_CLK0` (and reset pin) against full Vivado pin object paths. Actual net endpoints were correct. Compare against resolved `get_bd_pins` objects, preserving connection assertion | Attempt 03 exited 0 |
| 03, exit 0 | Real Vivado synthesis, implementation, routing, BIT and HWH generation | 22 host tests PASS; existing HWH/artifact verifier exit 0 |

**Independent host report review:** 100MHz clock, WNS +1.829ns / TNS 0;
WHS +0.018ns / THS 0; pulse-width slack +4.020ns, total violation 0;
zero failing setup/hold endpoints; all twelve `check_timing` issue
categories zero; DRC and methodology reports each `Checks found: 0`.
Reported utilization: 1,339 LUTs, 1,672 flip-flops, zero latches.
This substantiates **Host-only implementation PASS**, not Z2 physical
qualification or deployed product readiness.

**Recovered report SHA256 independently recomputed and matched the
manifest:**

- `timing_summary.rpt`: `9806fa1a6a61f1d18fdb6b365c96c7aee83abd3b6245a4021865fb532ede73de`
- `drc.rpt`: `07836b1165e032fe8d8f1f4667252f7a9bc71184f5ac0e6cdf4a58ae3055d490`
- `methodology.rpt`: `e418e9ba7f3592c8cb74bdc0740f8c8f1c77d9c2405a8dd6dbf873fd75150104`
- `check_timing.rpt`: `7ff59f27430da0dfa03ad1a63e4140ad3a635b353a827338ed1a4e7f65f47dd3`
- `utilization.rpt`: `2b382b28f7c81220789a381f052c1aa1abc261bd2924c23cb04920430c2cde1e`
- Engineering report: `5a8c899017ada58522d440029f3350c50833a5bf2b5c81deba9a4e5476ec276d`

**Binary-delivery caveat:** The in-run verifier records BIT
SHA256 `134e4f6103f25cbb9a9e2ea1e5e947ced29a508bbe799becb2a08f680b769cfc`
(4,045,769 bytes), HWH SHA256
`885808eee923cc5f27723452d663e928cd5c0c8869ec927df6e5d6c71cf49722`.
However **the initial uploaded artifact ZIP does not contain either binary**:
both were written under hidden/ignored `.plasma-path3-evidence/artifacts/`,
which did not match the effective upload set. Their hashes in the
manifest/report are original run claims, **not independently recomputed from
the downloaded binaries**. Subsequent Path 3 must place unmodified BIT/HWH
under `pl/build` (which the existing trusted workflow uploads by
`candidate/pl/build/**/*.bit` and `**/*.hwh`), retain full
logs, and independently verify downloaded binaries. Do not silently mark
portable artifact custody complete until this is done.

**Scope:** No FPGA load, Z2/DUT/LA/MMIO/USB/power, production release or
hardware HIL. M1 remains `NO_GO`. PR #1064 remains Gate 1 until
new source HEAD CI and portable artifact evidence are verified; its
merger requires the owner's independent Gate 2 authorization.


## F1-B Gate 1 closure — second clean-HEAD Vivado rebuild and portable custody PASS (2026-10-20)

**Live SWPC evidence:** [Path 3 Run 39344221935](https://github.com/physicslu/plasma/actions/runs/39344221935), GitHub Artifact [12229639751](https://github.com/physicslu/plasma/actions/runs/39344221935/artifacts/12229639751), ZIP SHA256 `f64356602431dc991060ef303470a8f051a8dab7edc8ec249e250974445b1b00`. Exact authorized PR #1064 input HEAD `00336106ad89eaa9fa0603dbe9e65024a27a6fe6`; trusted main dispatcher `78d3ca70f43a13523da8b6d3cdd578ec91d79b39`; board files `e02d6a3866b5465218f777168cdc51344ac94e07`.

This is a **fresh** Vivado 2026.1 Host-only synthesis, implementation, routing and bitstream build of the fixed Tcl in the above candidate HEAD, **exit 0**. Source patch in this run is empty: no additional RTL/Tcl/checked-in file changes. Original and delivered HWH verifier both exited 0. Setup WNS +1.829 ns / TNS 0; Hold WHS +0.018 ns / THS 0; pulse-width slack +4.020 ns; 100MHz clock; twelve check_timing categories zero; final DRC and methodology each reported zero findings. GitHub-hosted CI for the exact input commit completed **10/10 SUCCESS**. The optional on-SWPC `python3 -m pytest` invocation **did not run tests** because its default Python lacks pytest; do not equate this with a passed on-SWPC pytest run. The GitHub-hosted source-contract tests did pass.

**Binary custody is now independently verified from the DOWNLOADED GitHub Artifact, not merely the Codex manifest:** both raw original and delivered copies were present and SHA256-matched each other and the `delivery-manifest.json`:
- `pl/build/f1b-deliverables/system_wrapper.bit`, **4,045,769 bytes** — SHA256 `fdbde5c66999a9dab37339587d304b9c16e71a06f1890b24893c8391859cf075`
- `pl/build/f1b-deliverables/system.hwh`, **138,977 bytes** — SHA256 `bf3690d69fefc8da3fc62964209776466894cd4353aec0a475b373257899ca76`
- `timing_summary.rpt`: `7805d56523022edb095a4ed59ebd93b5bae86fcffa92149bb486a569c3db7919`
- `drc.rpt`: `21c2cbf0995e386f6db0bac041d27d9285a0695fce8171903ce953148af37b78`
- `methodology.rpt`: `9a18c015a8469831541e91726995331200bf0885b2c0775f502bbc19279119b3`
- `check_timing.rpt`: `482162887546260f3e54bb0972df98abc08370f47779b1b258d074a4f1ac5898`

The second run removes the **initial Artifact's missing BIT/HWH** deficiency; its prior caveat is historical only, not the current status. Persistent provenance includes the real Vivado logs/reports, original and copied hashes, two HWH verifier receipts, and problem/solution engineering reports. GitHub Artifact retention is limited (14 days by current workflow setting), so preserve a reviewed external copy when planning release.

**Gate 1 Host-only qualification = PASS**, pending only new latest-HEAD CI after this documentation change. **Gate 2 merge of PR #1064 remains owner-reserved; do not auto-merge**. This image has **not** been loaded onto FPGA; actual Z2/DUT/LA, power, USB/MMIO, hardware HIL and deployment remain NOT_RUN, and M1 is NO_GO.

## Path 3 legacy mechanism deletion (candidate)

The two historical F1-B Path 3 registry tasks and their special workflow
prefetch/admission instructions are removed. Historical results above remain
unchanged. New Path 3 Work Orders contain the schema, execution_path
`path3-codex`, capability `codex-workspace`, objective and acceptance; an
owner-pinned PR additionally supplies pr_number and source_sha. They do not
contain scope or hardware_stages. These routing fields authenticate the existing
dispatch protocol; they do not select an engineering mode or builder.

The existing candidate workspace supports autonomous software/build iterations.
Physical calls still require the existing protected executor; automatic
post-Codex list progression has been deleted. General future-image physical
delegation remains blocked by that executor's fixed reviewed F1-B image
contract. Removing those root image pins would also change Path 2 and remove
its artifact authorization boundary; this cleanup preserves them. No physical
execution or deployed-main behavior is proved by the candidate patch.

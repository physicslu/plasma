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

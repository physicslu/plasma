# Path 2 capability policy — reviewed fixed host builds

Path 2 is a **fixed CLI execution mechanism**. It is not conceptually tied to
`cpu-only` and a Python-only `scripts/experiments/*.py` script.

The original 2026-10 Development Dispatcher hardcoded CPU-only in
`task_by_id`, `authorize`, `execute` and the common Workflow job's
`if` condition. This repository-specific policy was not imposed by GitHub or
Vivado. It is now replaced with a typed capability route:

- `cpu-only`: unchanged bubblewrap, Python -I -S, 40s and output digest.
- `z2-cpu-only`: unchanged exceptional A2 one-shot hardware Claim.
- `vivado-host-build`: fixed **host** CLI via reviewed `main` project
  scripts, registered in the existing Development Task registry. Only the
  owner-created Issue #981 **main-only** command with exact pinned main SHA
  is admissible; PR-head candidates, re-runs, unknown capabilities and
  arbitrary executable paths fail closed.

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

**Gate 1:** source and hosted negative contracts only. Actual SWPC toolchain,
filesystem ownership/isolation, board-cache access, host Vivado synthesis,
timing, DRC, BIT/HWH and signed Build ID are **NOT_RUN/NOT_QUALIFIED**.
A separate owner's explicit approval is necessary before posting a real
Issue #981 Path 2 execution request. No Gate 2 merge consent is implicit.

# OPP Common v1 — Z2 Physical Admission Gate 1 (Path 3)

Issue: #1538. Dispatcher: #981. Owner-approved read-only investigation; this file is the minimum PR candidate for SHA-pinned Path 3 admission, not a physical deployment authorization.

## Accepted baseline

- Merged PR #1530, merge commit `0fae8f4447ac3978e4810520060036ab2176e572`.
- Exact Vivado Host Build source `82350e66ab337e4f2c31db2d85996030e9b37832`, Run `45114254444`, Artifact `14790698378`.
- Common AXI `0x43C03000`, SWD Site 1 `0x43C01000`, Site 2 `0x43C02000`, each 4 KiB; FCLK 100 MHz.
- Host Build receipt `HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED`. Six TIMING-18 external I/O warnings; external timing unqualified. Physical load, MMIO, Z2 HIL and DUT all NOT_RUN.
- BIN and candidate Manifest hashes were recorded in receipt but bytes were not included in the uploaded GitHub ZIP; inspect actual delivery and canonical candidate pairing.

## Bounded acceptance

1. Read current AGENTS.md, Path 3, FPGA, Embedded and trusted dispatcher contract; reuse accepted Host Build evidence and check only changed admission surfaces.
2. Read-only inventory of current Z2 Root/Active/Golden/Recovery identity and quiescence **only if supported by the already authorized read-only route**; otherwise mark NOT_VERIFIED, never infer from old observations.
3. Check whether the canonical Path 3 route can safely perform later candidate FPGA load and Common MMIO smoke test, including source/manifest integrity, locks, safe I/O, recovery and existing Linux permissions. Do not actually load or access MMIO in Gate 1.
4. Record PASS/BLOCKED/NOT_RUN and exact evidence; propose the smallest later owner-authorized physical validation: BUILD_ID, SITE_PRESENT=3, SITE_READY=0, decode isolation, rollback and regression.
5. Do not expand into unrelated CI, 8-Site hardware, full SWD electrical qualification or re-build unless actual evidence requires it.

## Prohibitions

No deployment, FPGA loading, MMIO reads/writes, DUT, OpenOCD HIL, power operations, service restarts, destructive operations or merge. Do not claim TIMING-18 resolved or hardware qualified. Gate 2 is for PR merge only, not an invented hardware approval gate.

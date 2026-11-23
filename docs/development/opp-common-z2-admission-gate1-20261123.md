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

## Path 3 investigation (2026-11-23)

- Executor: SWPC-plasma-codex, run `45121834919`, job `development-codex`, attempt 1; execution and publisher receipts are produced after the Codex process exits and remain **NOT_VERIFIED** here. Candidate checkout `0980ea85645414911d8cddbac14d693e38928b61`; live PR head matched at investigation time.
- Reused Host Build: merged #1530 source `82350e66ab337e4f2c31db2d85996030e9b37832`; Path 2 run `45114254444`, job `137493391899` succeeded. Its logged receipt reports BIT `c2255c8211e4bf2b59a42d1f5cce49da1e5f335c1a1f23125dc42f468d0f46d6`, HWH `afc9220ca00798ab06ea683d97b47a935857b3159f21b24af3e0f3b3b43a0ad8`, BIN `9483241d753e652d9ac7854213a7831417379ff4944b599fd523be493afc3540`, Manifest `d1ee45d84d10b1ac94af48e3958addf6db3b95ef15685390b1b798456342c504` (SHA-256). These are receipt claims, not newly hashed files or proof of cross-file pairing.
- Delivery diagnosis: the Path 2 upload patterns include `*.bit` and `*.hwh` but omit `*.bin` and the manifest JSON. Artifact `14790698378` exists; its published ZIP SHA-256 is `a9286c0f1207b7c065cda6f6d7d0472e216af699414d1f96fabeaa5a2d173481`. The Codex sandbox has network disabled and no GitHub CLI token; artifact bytes and any surviving original build output were not verified. Recover the exact original outputs through the trusted artifact/host route, then independently hash and validate their manifest, source identity and conversion relationship. If unavailable, a separately authorized exact-source rebuild and delivery is needed; recorded hashes alone cannot supply the files.
- The checked-in Root Guard identifies Golden `base.bin` SHA-256 `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c` and enforces protected ownership and reload fencing. This is source inspection, **not** a current Z2 observation. Root installation, Active image, Golden bytes, recovery readiness, owners, quiescence and effective device permissions are **NOT_VERIFIED**; the network-disabled sandbox did not support the authorized read-only SSH route.
- Later physical smoke test, only within a future appropriately scoped authorization: recover and validate the exact candidate BIN/Manifest and BIT/HWH evidence; confirm target, boot, protected Root and Golden bytes, ownership/leases, electrical safe state and actual permissions; use the existing guarded load with reload fence and recovery available. After a proven load, under the same ownership, read Common BUILD_ID words at `0x43C03018..24` against `82350e66ab337e4f2c31db2d85996030`, SITE_PRESENT at `+0x30` = 3 and SITE_READY at `+0x34` = 0; exercise bounded decode isolation and relevant regression without DUT drive. Keep Loaded after a successful load while safe; use Golden recovery only for an actual recovery need or explicit selection. Validate the concrete safe MMIO and rollback procedure before execution; source inspection alone does not establish a runnable end-to-end route.
- Current result: Host receipt and omission diagnosis **PASS** as source/log observations; physical admission and candidate byte pairing **BLOCKED** on missing bytes and current device evidence. FPGA load, MMIO, DUT, deployment, restart and recovery **NOT_RUN**. Six TIMING-18 warnings remain unqualified. Hosted repository-contract run `45121639517` passed its applicable documentation and routing jobs for the initial HEAD; latest published HEAD CI and Gate 2 readiness require independent verification after publication.

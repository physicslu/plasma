# Site-level Programming Admission (#1510): SWPC deployment + Z2 HIL evidence (2026-11-20)

**Status: FIXED / HIL VERIFIED.** This is the defect where `PPU_BUSY` blocked Sites of the same Batch from running concurrently. Owner closed
it 2026-11-20. Fix: PR #1510, merge `ba1a4b713e4ac56ed58677b0d68132afc629e7d9`, deployed to the SWPC Control Station only (Z2 Runtime
`acdfd7403`, Root, FPGA and Active Set unchanged).

| Part | What it proves | Result |
|---|---|---|
| [stability-400/](stability-400/README.md) | CS deploy (verify PASS ×2 incl. restart); 2 Sites × 100 Cycles × 2 rounds, same-IC Debug | 400/400 E/P/V + SAFE_OFF PASS, 0 UNKNOWN / Root Guard denial / `NEXT_CYCLE_EXECUTION_PPU_BUSY`. Throughput 8.95 → 9.67 Jobs/min (+7.9 %) vs the #1503 baseline on the same Z2; mean terminal → next start 3.8 → 2.77 s. Next-Job dispatch ≈ 2.4 s. Scenario A/B **not** provable here: the two Sites stayed phase-locked |
| [staggered-6/](staggered-6/README.md) | Cross-Site next-Cycle independence, both directions, via `--replace-ic yes` and a staggered `plasmactl program continue` | 6/6 PASS. Site 2 Cycle 2 was accepted/started by the PPU 1.82 s / 1.49 s before Site 1 Cycle 2 ended; Site 1 Cycle 3 1.79 s / 1.47 s before Site 2 Cycle 3 ended. Each time the Manager fleet observation already showed the peer `running` |

Scope and honesty notes:
- Only existing tools were used (`plasmactl`, Manager/PPU/Bootstrap APIs, `jq`, `journalctl`; a read-only SSH helper for Z2 state). No product
  code or new tooling. The `*-jq-filter.txt` files are the exact jq filters used for the timing tables.
- No IC was replaced or re-seated. In `staggered-6`, Continue was used only to stagger the Sites, on the same ICs (owner decision); those Cycles
  are not distinct units.
- Different-owner `PPU_BUSY` and maintenance-quiesce contracts were not exercised on hardware (no injected conflicts). They are covered by
  #1510 Host-only tests T5/T6 and the unchanged PPU lease tests.
- Not included here: the CS state backup (it contains bootstrap credentials), Manager run-journal snapshots and per-Job raw rows. They stay in
  the SWPC evidence root `<evidence-root>/site-admission-gate3-20261120` and `…/site-admission-gate3b-staggered-20261120`.
  Relative paths such as `../z2-root-wo1-deploy-20261119` and `../wo1-hil-2site-2x100-20261119` in the part READMEs refer to that root.
- Redaction: in every file here the host evidence root is written `<evidence-root>`, worktree paths `<worktree>`, the home directory `~`, and
  the operator account in Continue/actor records `<operator>`. All values are otherwise as recorded.
- Not electrical, Power Control or production qualification.

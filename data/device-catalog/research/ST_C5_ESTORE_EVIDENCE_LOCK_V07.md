# ST Coverage Gap v0.7 — Evidence-Locked Public C5 Category Set

**Reference date:** 2026-09-29. **Research-only observed category; no ST Production write.**

## Confirmed live acquisition

PR [#677](https://github.com/physicslu/plasma/pull/677) executed the bounded public official STM32C5 eStore source-byte collector at its final PR head `b8457dc333b1526ea798ac609bf55be38ed18324`. Workflow run [36537612073](https://github.com/physicslu/plasma/actions/runs/36537612073) job 109305204084 returned `OBSERVED_C5_CATEGORY_CANDIDATE_REQUIRES_INDEPENDENT_REVIEW` after all 18 pages: 10 exact Active item cards on each of pages 1–17, 2 on page 18, **172 distinct same-card Active Exact MPNs**. The category itself displayed Active 172; all parsed commercial identities were distinct, and the previously observed `STM32C531CBT6` sentinel was retained.

- Captured ZIP: [Artifact ID 11018802900](https://github.com/physicslu/plasma/actions/runs/36537612073/artifacts/11018802900), GitHub retention **7 days**. It holds original 18 HTML response files, `capture-manifest.json` and `observed-active-exact-c5.csv`.
- ZIP SHA-256: `b0b7349899864cbb5378603de17526532898e249be54d48a989c2c8b6b191861`.
- CSV SHA-256: `1c09edd86c7bfe12b38f6e22fea8626adced3ab964990ac6f61c1a9880abd85c`.
- Canonical sorted exact-MPN set SHA-256: `32d81e2491f1c8973a778cf62828a0c76662f4fb1813bc611d8b8959607b36a3`.
- The report `st-c5-estore-evidence-lock-v0.7.json` pins all **18 original page SHA256** values, parsed card row counts, actual acquisition run/head/artifact IDs and independent review boundaries.
- `st-c5-estore-172-active-exact-mpn-v0.7.txt` retains the exact 172 code identities without copying whole manufacturer page text into the Production repository.

## Bounded ST gap accounting

| Evidence component | Exact MPN observations not in frozen ST Production |
| --- | ---: |
| C5 public official category, raw captured/parse validated | 172 |
| H5 (v0.5 manually transcribed official row observations) | 6 |
| N6 (v0.5 manually transcribed official row observations) | 3 |
| WB0 (v0.5 manually transcribed official row observations) | 2 |
| WL3 (v0.5 manually transcribed official row observations) | 8 |
| **Five-family bounded observed minimum** | **191** |

The combined 191 is a **research observation minimum**, *not* all-ST missing count or any coverage KPI. Four non-C5 cohorts remain manually transcribed, not raw-page replayed. Frozen ST Production remains **2,683 exact ICPNs / 23 families**, with C5 absent.

**Unresolved:** the eStore's observed 18-page category may not equal the entirety of ST's current C5 ordering portfolio; 18 pages were acquired sequentially, not atomically under a manufacturer-issued as-of date. eStore Active is distinct from stock/order availability; any item labeled Coming Soon must be reviewed independently for eventual production admission. The source artifact's raw bytes must be durably retained (subject to manufacturer terms) before GitHub expires it. Thus the actual complete-ST Active denominator, missing count and coverage percent remain **UNKNOWN**.

## Replay

```bash
# Always runs without vendor network; replays 23 Production source SHA checks:
python data/device-catalog/research/validate_st_c5_estore_evidence_lock_v07.py

# If the ORIGINAL downloaded ZIP is available, also independently replay all 18 exact raw pages:
python data/device-catalog/research/validate_st_c5_estore_evidence_lock_v07.py \
  --artifact-zip /safe/st-c5-v06-source-evidence-candidate.zip
```

Research-only CI runs offline; no ST re-fetch per commit, no Production publication, backend route, security mutation, runtime or HIL claims. The **next gate** is independent manufacturer population/lifecycle reconciliation, metadata/target route qualification per exact C5 variant, and a separately approved Production proposal.

# ST ICPN Catalog — Catalog Complete / Maintenance Mode v1

**Decision:** 2026-10-12. **Scope:** manufacturer-authoritative, exact commercial STM32 MCU / wireless MCU identities admitted in PLASMA's Production ICPN catalog. This is a *Catalog identity* milestone only, not a Programming Backend or physical-programming support milestone.

## Closed identity-acquisition baseline

| Metric | Locked result | Authority |
| --- | ---: | --- |
| Scoped official ST eStore Active exact ordering codes | **4,550** | Manufacturer eStore Active enumeration frozen 2026-10-01 |
| Active exact identities present in PLASMA Production | **4,550 / 4,550 (100%)** | Layer-1 closure, `ST_FINAL_LAYER1_PRODUCTION_PUBLICATION_V62.md` |
| Total PLASMA ST Production exact ICPNs | **4,629** | Historical publication baseline; runtime source of truth remains the verified Production manifest |
| ST ICs with admitted packaged-runtime OpenOCD mapping | **4,164 / 4,629** | `ST_H5_C5_RUNTIME_GAP_V1.md`, after v6.31 route transaction |
| ST ICs still blocked from mapping | **465** | `openocd-final-runtime-blocked-v6.31.csv` |

**Interpretation:** No outstanding *identity additions against the locked 2026-10-01 official Active population*. This is not a claim that the live ST product portfolio remains static, that 4,629 is every ST IC, or that every admitted identity has a flash algorithm, electrical profile, device security support or HIL proof.

The 4,629 Production identities include 79 entries outside that frozen Active exact set. An earlier manufacturer audit classified one as NRND and 78 as absent from the audited eStore Active/NRND surface; these are **historical audit observations**, not up-to-date retirement determinations. Do not delete, mark Obsolete, or migrate them solely based on that observation. Reconcile exact identities and conflicting lifecycle signals against dated manufacturer evidence when due.

## Active maintenance policy

1. **Monthly official-source delta audit (manual or scheduled workflow after separate implementation approval):** reacquire complete ST eStore scoped Active exact ordering codes with source timestamp, pagination, counts, card/identity integrity, raw source evidence, and digest. Diff exact sets: `Active_new - Production`, `Production - Active_new`, `Active_new - Active_locked` and `Active_locked - Active_new`. Preserve unknown states rather than guessing Obsolete.
2. **New identities:** stage research evidence and bounded family-wise admission proposals. Publication is a separate explicit owner-approved transaction following existing manufacturer provenance, exact-MPN, metadata, manifest/SHA binding, historical regression, CI and release policies. No automatic Production writes.
3. **Lifecycle:** retain Active, NRND, unknown and manufacturer-Q&R discrepancies as distinct states; a missing eStore card is not evidence of obsolescence. Audit the historical 79 outside-Active entries using their exact vendor ordering codes.
4. **KPI:** always publish the observation date, official exact Active denominator, Production Active intersection, newly missing Active MPN count, and distinct backend/physical readiness metrics. Never silently substitute backend coverage for identity coverage.
5. **Runtime qualification remains separate:** 465 previously identified backend blocks consist of STM32H5 **190**, STM32C5 **172**, STM32N6 **32**, STM32WB0 **24** and STM32WL3 **47**. H5 and C5 candidate work is research/host-only until a pinned, isolated provider, tested target transport, electrical profile and physical approval exist. An identity with `no_mapping` remains fail-closed.

## Evidence and execution boundaries

- Canonical Product identity authority: `data/device-catalog/production/icpn-v1-manifest.json` and integrity-checked Production sources, **not this document or research CSVs**.
- Historic identity closure: `ST_FINAL_LAYER1_PRODUCTION_PUBLICATION_V62.md`.
- Backend gap authority: `OPENOCD_FINAL_COVERAGE_V631.md` and `ST_H5_C5_RUNTIME_GAP_V1.md`.
- This status update changes **documentation only**. It creates no CI scheduler, does not change catalog source files, backend mappings, programming profiles, Production manifest or OpenOCD binaries, and grants no hardware-runtime authority.
- Reopen identity-acquisition implementation when a verified ST official-source delta demonstrates new Active ordering codes or an unresolved evidence discrepancy that merits further work.

**Decision boundary:** `Catalog Complete / Maintenance Mode` = frozen population identity coverage complete. **Backend qualification, PS/PL integration and real-IC flashing remain independently gated workstreams.**

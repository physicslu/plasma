# NXP Phase 1 v24 → IC Selector read-only projection v1

**ADR-0002 boundary:** only manufacturer **01 IC Information**. The user-facing IC Selector still obtains its exact searchable ICPN identities from the pre-existing **Production Catalog manifest**. Phase 1's 501 source observations (224 already admitted + 277 Research-only) are **not** a search database and never add identities or change `catalog_size`, `total_count`, `backend`, `selected_profile`, Job/Batch admission, Software SUPPORTED, or PPU/Socket evidence.

## Changes

- `plasma_web.nxp_phase1_information` reads the exact v24 ledger `data/device-catalog/research/nxp-501-phase1-kl25-k32l2a-io-v24.csv` with pinned Git blob SHA. Rejects modified source, wrong source shape/identity counts, illegal state/value pairs, and field coverage drift.
- The Web Gateway projects the four source-backed manufacturer fields **only after** the existing production search result is resolved. Full identity, original package, pin count, Flash, temperature and original manufacturer authority must match before any research annotation appears. No fallback to the 277 Research-only rows.
- `GET /api/devices/search` adds optional `nxp_phase1_information` for admitted NXP exact ICPNs (KL25 12, MCX 196, K32L2 16), null for ST; the previous `nxp_manufacturer_device_profile` stays for backward compatibility.
- IC Selector section **01 IC Information** displays source value, `VERIFIED/PARTIAL/UNKNOWN/CONFLICT` for RAM, Working VDD, I/O Supply, VDDA, and links to per-field NXP evidence where present. UNKNOWN stays explicitly UNKNOWN. Source URL is field-specific: v24 (KL25/K32L2A I/O), v23 (MCX A rails), v21/v20/v18 (RAM), or the retained earlier official source.
- No `VDDIO` inference, no promotion of 16 KL25/K32L2A I/O PARTIAL values to VERIFIED, no treating VDD_ANA ±0.1 V as a universal supply setpoint; original PDF bytes remain unarchived/unqualified.
- ST rendering and the legacy NXP evidence path remain unchanged if the new optional projection is unavailable from an older Gateway. Phase 2 Programming and Phase 3 PLASMA Compatibility remain independent sections.

## Admitted NXP field coverage (224 denominator)

| Field | VERIFIED | PARTIAL | UNKNOWN |
|---|---:|---:|---:|
| RAM | 199 | 25 | 0 |
| Working VDD | 135 | 27 | 62 |
| I/O Supply | 119 | 16 | 89 |
| VDDA | 135 | 0 | 89 |

These are **research confidence states**, not OpenOCD supported states or HIL results. Production identity count remains 4,853 (ST 4,629 + NXP 224) at the baseline source revision. ADR-0002 Issue #849's product-only Software SUPPORTED visibility migration is **not** implemented by this change. Deployment is a separate approval after PR merge.

## Reproduce

```bash
python -m pip install -e software/python
python -m unittest discover -s software/python/tests -p 'test_nxp_phase1_information_selector_v1.py' -v
python -m unittest discover -s software/python/tests -p 'test_nxp_manufacturer_device_evidence_v6.py' -v
cd software/web
npm ci --no-audit --no-fund
node --test tests/nxp-phase1-selector-contract.test.mjs tests/ic-selector-contract.test.mjs
npx tsc --noEmit --target es2022 --module esnext --moduleResolution bundler --jsx react-jsx --skipLibCheck --esModuleInterop app/device-catalog-api.ts app/devices/ic-selector.tsx
```

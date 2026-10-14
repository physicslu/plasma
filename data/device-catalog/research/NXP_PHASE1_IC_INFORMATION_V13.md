# NXP — ADR-0002 Phase 1 IC Information (v13, 501 exact observations)

**Current scope:** only the **01 IC Information** detail panel in the owner's
three-section view. Phase 2 **02 Programming** and Phase 3 **03 PLASMA
Compatibility** are explicitly deferred; there is no new `SUPPORTED` or
HIL qualification in this deliverable.

## Data and source authority

- A 501-row, source-locked **`nxp-501-phase1-ic-information-v13.csv`**
  preserves the 224 already admitted **internal identities** and 277
  additional **research-only exact ordering-code observations**.
- Columns correspond directly to the panel: `icpn`, `base_device`,
  `package`, `pin_count`, `flash`, `ram`, `working_vdd`,
  `io_supply`, `vdda`, `temperature`. Every specification field has
  a separate `*_state` column (`VERIFIED/PARTIAL/UNKNOWN/CONFLICT`).
- Every row preserves original CSV source, original Git blob, original
  manufacturer URL/document reference, and original exact HTML SHA256
  **where available**. An HTML hash without preserved bytes is *not* a
  full original-document archive.
- `VERIFIED` here means **previously admitted identity + existing
  manufacturer-sourced field from the original admission record**,
  *not* newly checked live manufacturer documents. `PARTIAL` means
  **manufacturer field observed with retained HTML SHA256 in the 277
  research-only cohort**, not approved internal identity admission.
  Unobserved values are blank and `UNKNOWN`; not inferred from another
  package/model or silently replaced by zero.
- Raw historical `flash_kb`/`html_ram_kb` strings are kept with
  `ORIGINAL_V8_LEGACY_KB_FIELD` provenance, and existing Production
  `flash_size` strings keep their source unit; **no conversion** from
  kB to KiB is implied. Optional Core metadata remains in the earlier
  family-level v10 archival ledger, not an exact Phase 1 claim.

## Exact original source lock

The Phase 1 input ledger is rebuilt byte-for-byte only from:
`nxp-277-full-dispositions-v8.csv` (277),
`nxp-kl25-commercial-icpn.csv` (12),
`nxp-mcx-196-commercial-v5.csv` (196),
`nxp-k32l2-16-commercial-v5.csv` (16). The manifest and public product
Catalog are **not** mutated. No NXP-wide market universe is inferred
from these bounded 501 order codes.

## Coverage is not programmability

The separately emitted `nxp-phase1-field-coverage-v13.json` counts
each IC Information field as Verified / Partial / Unknown / Conflict
against its explicit cohort denominator. In particular
`RAM`, `VDD`, `I/O Supply` and `VDDA` remain unknown for
many entries; the visible IC detail must show an unknown state rather
than a guess.

`software_qualified_exact_icpns` and
`physical_hil_validated_configurations` are **null**, not zero:
they are not Phase 1 acceptance indicators.

### Legacy source work retained but out of Phase 1 scope

Draft #847 also retains original v9–v12 OpenOCD research as read-only
historical Phase 2 research. Its OpenOCD code-level P0/P1 investigation
does NOT increase Phase 1 completeness and its future work items are
**frozen** until separately authorized. Public selection/visibility
policy remains accepted (Issue #849) but its implementation is deferred
to Phase 2. No new software support, site readiness, UI filter,
Job/Batch or Production admission is inferred by this Phase 1 work.

Phase 1 tests verify full original input Git blob locks, 501 identity
uniqueness, 224/277 state separation, source-bound PARTIAL fields,
original units and fail-closed unknown values.

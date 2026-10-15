# Microchip — ADR-0002 Phase 1 S1 exact manufacturer identity funnel v1

## Scope

Implement the revised [ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md)
Section "三階段 IC Detail 與 Exact ICPN 驗收漏斗（修訂草案）"
as an **independent, reviewable Research-only implementation proposal**.
This ADR section is labelled a **revision draft** in the current main
document; this PR does **not** edit the ADR or presume separate owner
approval to modify Production/Catalog behavior.

The relevant distinction:

- **S1 IDENTIFIED**: complete exact manufacturer commercial ICPN, independently
  original-source-bound Base/Family, official exact-material source URI/scope,
  original material-response hash and actual `retrieved_at_utc`. May have
  missing package, voltage, memory, pin and temperature details.
- **S1_complete INFORMATION_COMPLETE**: subset of S1 with all required IC
  Information evidence verified for the exact ICPN or explicitly applicable
  official family. A partial family chart is not enough.
- **P0/P1/P2**: existing OpenOCD-first research priority metadata, never
  the numerator or denominator for S1/S2/S3 Phase acceptance. An original
  Microchip commercial order code lacking a CFG may still be S1 IDENTIFIED
  if independent *manufacturer* evidence is sufficient.

## Sources and replay

The existing `microchip_openocd_reverse_coverage_v1.py` original source
replayer reconstructs the **23,276** distinct exact commercial
`partNumber` observations from **313 source-attested batches** plus the
original publisher DFP index. The 8 quarantined batches are **not
counted**. This historical source set is not the broader **24,051**
Research candidate denominator, nor the entire active Microchip SKU
population.

The replayer now preserves on each individual exact material record:
official MCP endpoint `https://api.microchip.com/mcp/resources`,
`search_products` exact `partNumber` source scope, manufacturer
`basePartNumber`, original raw response SHA-256, source query,
original response `retrieved_at_utc`, and original archive file locator.
The **original captured timestamp**, never the CI replay timestamp,
is eligible as evidence of observation time.

`microchip_phase1_s1_exact_identity_funnel_v1.py` uses that
original-source-replayed mapping and the P0/P1 official Chart evidence
ledgers already generated in the same CI run. For every exact ICPN:

1. Reject duplicate exact codes, ambiguous/unbound Base,
   contradictory vendor rows, altered source URI/scope/SHA, and absent
   or malformed actual observation timestamps from S1. Preserve any
   such records in Research as `RESEARCH_ONLY` or `IDENTITY_DISPUTED`.
2. Admit to **research-only S1 `IDENTIFIED`** based on independent
   manufacturer identity proof, **not** OpenOCD CFG existence or priority.
3. Preserve **13 separate IC Information field states**. Existing original
   Chart P0/P1 Base Device values stay `PARTIAL` as appropriate; missing
   attributes remain `UNKNOWN`, never synthetic numeric zero.
4. Report **S1_complete independently**. Identity evidence, even when
   sound, does not make 13 fields complete.
5. Preserve manufacturer raw lifecycle as an exact-MCP observation,
   without manufacturing additional SKU lifecycle/status claims.

This research artifact reports individual records, source observation
gaps, field coverage, S1 and S1_complete, plus legacy OpenOCD
P0/P1/P2 separately. Source-bytes replay in temporary CI artifacts
does not amount to **permanent custody**; long-term archive work remains
separate.

## Excluded by design

No update to `docs/adr/0002-...`, Production Manifest, public
`/api/devices/search`, IC Selector, internal admission, runtime,
OpenOCD software `SUPPORTED`, Flash algorithm, geometry, Programming
Profile, PPU, Socket, Site or HIL. These are independently gated Phase
2/3 work.

**Do not report `S2` or `S3` as zero actual-qualified ICPNs from this
Phase 1 projection.** The fields `openocd_software_supported_count_from_this_phase=0`
and `phase3_hil_passed_count_from_this_phase=0` mean that *this Phase 1
research script created no new qualifications*. Global S2/S3 must be
computed separately from their own authoritative registries, not
inferred from Research-only data.

## Reproducibility

In the Microchip CFG-first CI, the bounded offline test
`test_microchip_phase1_s1_exact_identity_funnel_v1.py` rejects missing
observation time, untrusted material-source URI, Base conflicts,
incorrect SHA, P0/P1 overlap and duplicate exact ICPN. The original
313-batch replay then generates `microchip-phase1-s1-exact-identity-funnel.json`
and independently verifies deterministic output.

The resulting per-field coverage, S1 identity counts and unresolved
source provenance counts are **measured by CI**, not assumed from the
historical P0/P1 numbers.

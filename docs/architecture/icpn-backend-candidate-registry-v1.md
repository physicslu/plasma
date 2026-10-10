# ICPN Backend Candidate Registry v1

**Source-locked, read-only enrichment. No Production backend mapping, Programming Profile, Z2, FPGA or physical programming.**

## Why a distinct registry?

The Production Catalog already admits 4,629 ST exact identities: 4,164 mapped and 465 no_mapping. H5 190 and C5 172 are **already admitted exact ICPNs** but remain entirely no_mapping. PRs #802 and #803 added research-only, immutable source evidence for these families, not physical programming support.

The candidate registry is a **read-only join**, not a second IC catalog:

- H5 190 → five pinned ST-fork source-inferred Device ID groups, native stm32h5x driver, official catalog Flash capacity, source-described 8 KiB sector and 16-byte write alignment.
- C5 172 → three source-inferred Device ID groups, three pinned DFP .xldr **source path and SHA256 candidates**; 139 exact DFP Dvariant matches, 33 base-device-only. All 172 have official Production exact-ICPN identity/Flash metadata; the 33 still need exact DFP algorithm applicability proof.
- N6 32, WB0 24, WL3 47 remain no_mapping with **no** invented candidate.

Source Device ID is not readback. The H5 driver Flash size may fall back to maximum when a register read fails; that is never interpreted as a measured capacity. C5's source Tcl scalar/array defects, empty loader table, 32 KiB default work area versus DFP-declared 64/128/256 KiB algorithm RAM, and license/runtime/physical gaps remain explicit blockers.

## API and UI

The existing GET /api/devices/search endpoint remains unchanged in identity filtering and sorting. An additive optional backend_candidate payload is presented **separately** from the Production backend object:

- For all 362 research-only H5/C5 rows, status=research_only, executable=false, production_binding_authorized=false, hardware_runtime_ready=false, physical_programming_qualified=false.
- For all other Production rows, backend_candidate=null.
- Candidate source commit, target CFG *source path*, Flash driver, expected ID, official catalog flash size and optional C5 loader/DFP state are visible as reference information.
- Real backend.mapping_status continues to be no_mapping; backend.target_config stays empty. A candidate source path is never passed to Job/Batch resolution.
- IC Selector shows a research-only warning that programming is not available. This is a display annotation; it cannot open a Flash operation.

## Evidence provenance and fail-closed design

The server projects candidates only from real Production-admitted exact ICPNs. It validates full Git blob SHAs for the H5 group source evidence, C5 crosswalk, pinned DFP ledger and ST fork static source gate; ST source commits and Flash-size constraints must match the locked research. It rejects unexpected source changes, duplicate/unknown exact identities, missing/modified provenance and attempts to turn a candidate into a mapped backend.

The registry is locally cached; no upstream fetch, vendor OpenOCD binary, .xldr binary, patched executable Tcl script, network loader download or additional database is introduced. A full checkout can display source-verified candidates. A slim packaged PPU kit that does not include the optional reviewed research metadata **suppresses candidate display** (null) without altering Production search or creating an executable route; this is a deployment boundary, not candidate qualification. If some metadata is present but has a different content hash, loading still fails closed. Deployment of the 362-candidate display on packaged PPUs therefore requires a separate package-content acceptance step. An alternative Production Catalog with no H5/C5 cohort receives no candidates.

## Acceptance

Dedicated GitHub CI checks all 362 exact candidates, five H5 and three C5 device groups, C5 139/33 split, immutable provenance, negative corruption cases, server search API and UI contract regression. Production Catalog status and Site/PPU/Socket physical evidence remain untouched. Separate qualification gates are required before a real STM32H5/C5 backend can ever be promoted.

**Metric effect: 362 newly visible research candidates; zero newly mapped; 465 Production no_mapping remain.**

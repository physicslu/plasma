# Plasma ICPN v1 Production Catalog

This directory defines the **runtime source of truth** for IC Part Numbers (ICPNs) used by Plasma product paths.

## Production boundary

`icpn-v1-manifest.json` is the **single authoritative source of truth** for the currently admitted Production scope. This README is descriptive documentation only; it intentionally does **not** duplicate mutable Production state such as the current family list, per-family row counts, or aggregate ICPN count.

The runtime does **not** load `research/openocd-parts-canonical.csv` as a product catalog.

To inspect the current admitted scope, validate and load the manifest through the production catalog implementation:

```bash
PYTHONPATH=software/python python -m plasma_web.device_catalog --json
```

The resulting metadata (`catalog_size`, `source_count`, and `taxonomy`) is derived from the manifest and its integrity-bound admitted CSV sources. Do not copy those mutable values back into this README as a second source of truth.

Only rows that have completed the evidence → admission → canonical lifecycle may be referenced by the production manifest. OpenOCD research candidates, CMSIS device names, ordering patterns, family aliases, inferred commercial numbers, and unadmitted rows are excluded from the runtime selection surface.

## Runtime behavior

At startup the production loader:

1. reads the manifest;
2. requires `status = production` and the exact-ICPN-only selection policy;
3. resolves each admitted source relative to the manifest;
4. verifies each source by both Git blob identity and SHA-256 content digest, then verifies the declared row count;
5. validates the admitted canonical CSV schema and required provenance fields;
6. rejects duplicate `(manufacturer, ICPN)` identities across sources;
7. computes a SHA-256 runtime catalog revision from the bound source content digests;
8. exposes only the validated aggregate view.

Failure is **fail-closed**. There is no fallback from the production catalog to the research/candidate catalog.

`PLASMA_DEVICE_CATALOG_MANIFEST` may select another manifest for a packaged/deployed product, but that manifest must pass the same integrity checks. `PLASMA_DEVICE_CATALOG_PATH` remains only as a deprecated explicit CSV helper for research/tools/tests and is not used by the default product loader.

## Product API and UI

The existing `GET /api/devices/search` route remains the stable product API. Keeping this route avoids unnecessary Manager and Secure Gateway routing changes.

The search surface supports:

- exact ICPN;
- ICPN prefix/partial match;
- Vendor;
- Family;
- combinations such as `STMicroelectronics STM32F4`.

The shared `ICPickerField` is consumed by both PMode and EMode through `ProgrammingJobPanel`, so both modes use the same admitted production catalog. The browser submits only `vendor + identifier`; the Gateway resolves that identity again against its server-owned production catalog before creating a Job or Batch. Browser display metadata is never authoritative.

## Evidence domains stay separate

Production admission proves two things for rows referenced by the current manifest:

- exact commercial ICPN identity has authoritative retained evidence;
- the row has a deterministic OpenOCD target mapping.

It does **not** prove physical programming support. PPU and Socket validation remain separate evidence domains and must continue to report `no_evidence` until a Programming Configuration has been physically verified.

## Catalog version and update policy

`catalog_version` is a product contract version, not a row counter. The semantic version and the runtime content revision serve different purposes.

The runtime catalog revision is a SHA-256 derived from the admitted source content and is intended for release/audit correlation. A product release therefore has both:

- a semantic catalog version from the manifest;
- a content revision SHA-256 derived from the admitted source bindings.

v1 uses **release-bound updates**, not hot reload. Updating the catalog requires:

1. complete the normal manufacturer/family evidence and canonical admission flow;
2. update the production manifest source list / row counts / Git blob and SHA-256 content bindings;
3. pass retained historical family regressions;
4. pass production manifest/runtime tests;
5. pass API and Web IC Selector tests;
6. merge through the normal Plasma Merge Gate;
7. deploy through the separate deployment approval process.

A running process keeps the successfully validated catalog loaded for its lifetime. It does not silently reload a modified file from disk.

## ICPN v1 Production Ready acceptance

Phase 3.2 is complete only when all of the following are true:

- runtime default contains exactly the exact ICPNs referenced by the authoritative Production manifest;
- runtime metadata is derived from the loaded manifest and its integrity-bound sources rather than from documentation constants;
- research-only candidate identifiers cannot be selected through the product API;
- production source integrity failures stop catalog loading;
- `/api/devices/search` exposes package/memory/mapping/provenance and catalog revision data;
- both PMode and EMode consume the same shared admitted-ICPN picker;
- server-side Job/Batch target resolution rejects identities outside the production catalog;
- ICPN/OpenOCD evidence remains explicitly separate from PPU/Socket physical validation;
- retained admission regressions for the sources referenced by the current Production manifest remain green.

Deployment, service restart, FPGA/Z2 work, and real-IC programming are outside Phase 3.2 and require their own approval gates.

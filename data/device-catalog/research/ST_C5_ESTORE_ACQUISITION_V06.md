# ST Coverage Gap v0.6 — Raw-Evidence STM32C5 Category Acquisition Pilot

**Research-only. No new Catalog/Production identities or programming permission.** The frozen ST Production benchmark is 2,683 exact ICPNs / 23 families.

## Why this is a different gate

On 2026-09-29, the [official ST C5 eStore category](https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-mainstream-mcus/stm32c5-series.html) displays **18 pages** and the Marketing Status facet **Active 172 items**. The facet is not the list of 172 independently evidenced exact commercial ICPNs; it is a candidate population for a scoped acquisition. It does not establish full ST portfolio coverage. ST eStore separates **Active** marketing status from availability labels like **Coming Soon**, **Out of Stock**, and **In Stock**.

The preceding v0.5 manually transcribed 20 Active exact commercial rows over five absent families, including the C5 sentinel `STM32C531CBT6`. This transaction does **not** promote those rows or change the benchmark.

## Source-byte acquisition contract

- A single one-off GitHub pull-request job requests exactly 18 public eStore category pages (one second apart), on vendor HTTPS only, with a 6 MiB/page cap. No authenticated browser, private API, pattern expansion or evasion.
- For each 200 HTML response it retains exact original bytes (`raw/page-XX.html`), final URL, UTC time, SHA256, byte count in `capture-manifest.json` *before* parsing.
- Parses independently delimited HTML `li.product-item` cards, with one exact `STM32C5...` identity and a visible same-card **Active** marketing status. No loose global regex over scripts, wildcard construction or item-count guesswork.
- Strictly checks 18-page pagination, consistent 172 Active facet, expected 10 items on pages 1–17 and 2 on page 18, no duplicates, and the previously verified C5 sentinel.
- Only if 18/18 pages reconcile to **172 unique observed exact Active MPNs** emits `observed-active-exact-c5.csv` with the page-level raw SHA256 and exact-set SHA256. Its status is `OBSERVED_C5_CATEGORY_CANDIDATE_REQUIRES_INDEPENDENT_REVIEW`, not Production readiness.
- Any request/parsing/counter mismatch yields `ACQUISITION_BLOCKED` and partial raw evidence/manifest. The live job still ends successfully as an *attempt*, not a data-success signal, so vendor availability does not break offline parser CI. Read the capture manifest, never infer success from the GitHub green check alone.
- Evidence artifact retains raw pages for only 7 days; an approved durable store subject to vendor usage/license terms is required before relying on this as a retained proof.

## Replay / next gate

```bash
python -m unittest discover -s data/device-catalog/research -p test_acquire_st_c5_estore.py -v
python data/device-catalog/research/acquire_st_c5_estore.py --output /safe/st-c5-v06 --interval-seconds 1.0
```

After a successful live capture, independently inspect raw source and captured exact part lifecycle, prove category/version/filter completeness (including distinct suffixes), compare against frozen 2,683 Production ST identities, then separately qualify target mapping and metadata before explicit owner approval to publish any ICPN. C5 is **MX2-only**; no whole-ST coverage percentage can be computed from this one series. If blocked, use the official ST user-exported commercial list via v0.3 CSV/XLSX preflight instead of guessing.

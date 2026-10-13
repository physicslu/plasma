# NXP 277-source re-acquisition v7 — manufacturer evidence only

This change executes one **bounded 277 Active Exact ICPN** refresh in eight parallel
shards against NXP official exact `https://www.nxp.com/part/<ICPN>` pages.
Its input is the **immutably Git-blob-locked** v6 negative review queue.
It does NOT assert global NXP coverage, add identities to Production or enable
a programming backend.

## Acceptance rules

1. **277 / 277 requested**: 129 original and 148 expanded; source SHA-1 Git
   blob `6480f04e57dd29d7bd45441c38552dad89107f51`.
2. The Playwright capture accepts only exact official URL, HTTP 200 and a page
   `h1` identical to the SKU. An inaccessible or renamed page remains blocked.
3. The independent aggregate verifies SHA-256 of **original decompressed HTML**,
   exact `h1` again, replays NXP RAM/VDD parametric cells and records whether
   four base fields were observed. Unknown fields remain empty, never 0.
4. Eight complete shard manifests, exact immutable SKU order and individual
   evidence/artifacts are mandatory. Missing, duplicated, modified or forged
   sources fail the entire reconciliation.
5. **All 277 decisions are research only**. Positive observations are a
   candidate for a *separate* exact-SKU metadata admission audit; none receives
   Production, programming, hardware or physical qualification.
6. Acquisition failures are recorded as **source unavailable**, not a claim
   that the marketed Active part has ceased to exist.

## Output & evidence retention

CI artifacts: 8 raw HTML/shard bundles, one 277-row reconciled source CSV
and a source-state JSON (30-day retention). Before any future Production
proposal the original HTML must be durably archived or independently
reacquired with checksum and lifecycle review. No CI artifact is immutable
just because it has a digest; original byte availability matters.

Specific unresolved policy: i.MX RT devices with external boot flash
cannot be assigned invented on-chip Flash size `0` or passed through a
positive-internal-Flash Catalog schema without an explicit architecture decision.
Cross-ordering Base Device equivalence is likewise not inferred.

**Owner gate:** this PR adds research acquisition and fail-closed replay only.
Merging it does not change the 4,853 Production Exact / 224 NXP baseline.

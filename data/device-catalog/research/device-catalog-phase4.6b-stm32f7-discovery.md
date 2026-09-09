# Device Catalog Phase 4.6B — STM32F7 Official-ST Bounded Discovery

## Decision

Phase 4.6B retains manufacturer-backed identity/lifecycle evidence for the exact 16 Base Devices selected deterministically in Phase 4.6A.

The phase is a discovery/evidence gate. It is **not** an admission or runtime-support gate.

The retained result is disposition-aware:

- 9 targets expose Active exact commercial ICPNs;
- 5 targets have official ST commercial identities but only non-Active lifecycle dispositions in the retained surface;
- 2 deterministic targets have unavailable canonical ST product pages (HTTP 404) and remain commercially unresolved;
- 16/16 targets have a deterministic disposition;
- no target requires manual interpretation.

Therefore `bounded_discovery_clean=true`, while `commercial_identity_clean=false` remains intentionally true as a negative assertion: two target identities are still unresolved from the bounded canonical source surface.

## Immutable live execution

The accepted live execution is:

- workflow run: `34326658883`;
- executed Git SHA: `776ebeafe2156a6cfdea5340dc2c8921e45725ed`;
- artifact ID: `10094200419`;
- artifact ZIP SHA-256: `998670e0d8fc6331d60a080dccd48f0dbeb2e967a0169af4e177d9e60f30bf3f`;
- Playwright: `1.62.0`;
- Chromium: `151.0.7922.34`;
- browser mode: headed Chromium under Xvfb;
- parser profile: `stm32f7_dual_surface_v1`.

Retention independently downloaded the exact artifact ZIP and recomputed its SHA-256 before transformation. No ST page was re-fetched during retention.

The earlier pre-policy-fix run `34325627558` / artifact `10093847910` is retained only as negative engineering history. It exposed the invalid assumption that every OpenOCD-selected Base Device must currently have at least one Active commercial SKU.

## First-principles policy correction

Phase 4.6A and Phase 4.6B answer different questions.

Phase 4.6A asks:

> What is the deterministic bounded discovery surface derived from the guarded OpenOCD source?

Phase 4.6B asks:

> What does the official manufacturer source currently support us in asserting about commercial identity and lifecycle for each selected target?

Those questions must not be conflated.

A Base Device can be a legitimate deterministic discovery target even when its current manufacturer disposition is NRND, Proposal-only, or its canonical product page is unavailable. Treating those outcomes as equivalent to transport/parser failure would destroy evidence semantics.

The accepted dispositions are therefore:

1. `active_candidates` — manufacturer evidence contains at least one Active exact ICPN;
2. `lifecycle_excluded` — manufacturer identity is verified, but the retained exact identities are non-Active and excluded from admission;
3. `source_unavailable_excluded` — the canonical bounded manufacturer URL returned HTTP 404; no exact commercial identity is asserted and the target is excluded.

Only unresolved technical/evidence failures such as parser ambiguity, foreign identity contamination, malformed evidence, or non-classified transport failure require manual review and fail the bounded discovery gate.

## Retained result

Aggregate retained state:

| Measure | Result |
|---|---:|
| deterministic targets | 16 |
| dispositioned targets | 16 |
| manufacturer identity verified targets | 14 |
| Active candidate targets | 9 |
| lifecycle-excluded targets | 5 |
| canonical-page-unavailable targets | 2 |
| Active exact ICPN candidates | 19 |
| non-Active exact identity exclusions | 11 |
| manual-review targets | 0 |
| OpenOCD unique-routing targets | 9 |
| OpenOCD not-applicable targets | 7 |

The two source-unavailable exclusions are:

- `STM32F768AI` — canonical product page HTTP 404;
- `STM32F769AG` — canonical product page HTTP 404.

These are **unresolved and excluded**, not evidence of commercial nonexistence.

The five lifecycle-only target groups are:

- `STM32F746BE`;
- `STM32F756BG`;
- `STM32F765BG`;
- `STM32F767BG`;
- `STM32F777BI`.

Their retained non-Active exact identities remain evidence, but cannot be promoted into the Active admission candidate set.

## Identity versus capability boundary

OpenOCD routing is an orthogonal capability observation.

For the 9 Active target groups, the 19 Active exact ICPNs resolve uniquely to `tcl/target/stm32f7x.cfg` in the retained OpenOCD surface. For lifecycle-only or source-unavailable targets, routing is recorded as `not_applicable` because there is no Active exact ICPN set to route.

This does **not** establish programming-algorithm equivalence, flash geometry, option-byte behavior, HIL qualification, socket/electrical qualification, or runtime programming support.

Commercial identity evidence must come from the manufacturer surface. OpenOCD cannot create or rescue an exact commercial identity.

## Retention model

Raw rendered-browser evidence remains in the immutable GitHub Actions artifact.

The repository retains only the compact replayable projection:

- `stm32f7-phase4.6b-discovery-baseline.json`;
- retained `pilot-summary.json`;
- retained `provenance.json`;
- retained evidence `manifest.json`;
- retained evidence `README.md`.

The permanent validator hard-locks byte digests, live execution identity, browser/tool versions, source bindings, target ordering, disposition counts, Active/excluded identity separation, and the two HTTP-404 exclusions.

Historical Production prestate is retained as 544 exact ICPNs across STM32F0/F1/F2/F3/F4, with STM32F7 count zero. Future Production growth must not invalidate historical Phase 4.6B evidence replay.

## Claims intentionally false

Phase 4.6B does not claim:

- canonical dataset admission;
- Production admission readiness;
- Production write authorization;
- programming policy definition;
- programming-algorithm equivalence;
- physical target qualification;
- runtime support.

The 19 Active exact ICPNs are evidence-backed **candidates**, not Production records.

## Next gate

Only after this retained-evidence phase passes permanent CI and merges may STM32F7 move to Phase 4.6C metadata/admission-policy design.

Phase 4.6C must derive metadata rules from manufacturer evidence and must preserve the Phase 4.6B exclusions. It must not infer missing commercial identities for `STM32F768AI` or `STM32F769AG`, and it must not promote NRND/Proposal identities merely because OpenOCD can route a matching pattern.

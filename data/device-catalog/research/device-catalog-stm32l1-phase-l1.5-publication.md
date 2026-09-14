# STM32L1 L1.5 — Canonical / Production Publication

Date: 2026-09-14
Status: Gate 1 implementation complete; Gate 2 merge approval required

## Scope

L1.5 publishes only the 144 exact STM32L1 ICPNs frozen by merged L1.4. It does not discover new commercial identities, relax metadata policy, or qualify programming behavior.

## Frozen chain of authority

- L1.2 manufacturer-authoritative Active exact ICPNs: **144**
- L1.3 metadata-ready: **144 / 144**
- L1.4 capability-admittable: **144 / 144**
- L1.4 routing replay: **144 unique / 0 ambiguous / 0 unmapped**
- admitted/published exact-set SHA-256: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- L1.4 admission-plan Git blob: `6b75db8c09809534eba530e07ff11cf91085677f`
- L1.4 admission-plan SHA-256: `ea413a7c1761eded8875737c9e8fde3ff359a4bf52dfde1f52a795179d2457e4`

## Publication transaction

Prestate:
- exact ICPNs: **1,718**
- Base Devices: **530**
- families: **12**
- STM32L1: **0**

Poststate:
- exact ICPNs: **1,862**
- Base Devices: **589**
- families: **13**
- STM32L1: **144 exact / 59 Base Devices**

Publication artifacts:
- canonical CSV SHA-256: `72fcaf7e50537749f101e80cab7a403f3b3878006fe4019b99b99dadd2f409ec`
- canonical CSV Git blob: `8c4ff4b3331f6fe21f04c117fa952802ed587f71`
- proposal SHA-256: `c6569d29dbaaa45fa79c3c9a019bb993128d91f45feb79a717fd86afacc5f371`
- audit SHA-256: `62b5102282b7fa08c4536896a77e5e7286df3791b1660e9f9aa13ffb95365558`
- baseline SHA-256: `902b1983715d48228e9bca6d7025d5d23126b28d603d7c217c9343439273b81e`
- poststate Production manifest SHA-256: `64074683cb01d3584da314f15e499f3db2c4b586d96def3ab8371dd2b50d93f5`
- poststate Production manifest Git blob: `9c1f1a2c7c1ff3bea7892c5decf408ece676d7a3`

## Authoritative calibration / provenance

Final authoritative calibration and branch-publication run:
- workflow run: **34810850178**
- attempt: **1**
- executed SHA: `d80a3c96b31d19a659498387351227134d674aee`
- publication commit: `a5b79be6d7970526b42425db5161cec92d6b9486`
- artifact ID: **10334622426**
- artifact digest: `sha256:484959cb309c5c91d1f29a1c8c7f7c6f9f5d967accacfc4b093e3d3e02703469`

The artifact logical file SHA-256 values exactly match the committed publication files.

## Calibration corrections

Two calibration failures were execution/validation-wrapper defects, not commercial-data failures:

1. Initial post-write verification re-entered L1.2 historical discovery validation against the newly changed current Production manifest. That mixed immutable historical prestate with mutable current state. The final publisher fully replays L1.2→L1.4 before publication, then validates post-publication artifacts/current state without requiring historical validators to accept a changed current Production manifest.
2. The second run's bounded-delta check used `git diff --name-only`, which omitted untracked generated artifacts. The wrapper was corrected to include `git ls-files --others --exclude-standard`.

No exact ICPN, metadata row, route, or publication count was relaxed to resolve either failure.

## Permanent validation

Permanent validation hard-locks:
- L1.4 plan and frozen Production prestate;
- immutable STM32L1 canonical/proposal/audit/baseline bytes;
- publication provenance and artifact logical hashes;
- exact published set and 144/59 cardinality;
- exactly one STM32L1 Production source bound to the canonical CSV;
- current Production may grow in later phases, but STM32L1 must remain exactly 144 rows unless a separately governed transaction changes it;
- all programming/electrical/HIL/runtime non-claims remain false.

## Explicit non-claims

Catalog publication means the exact commercial identities are available in Production Device Catalog. It does **not** prove programming algorithm equivalence, Flash geometry, erase/program behavior, option/security semantics, electrical/socket compatibility, physical HIL, PPU deployment, or runtime programming support.

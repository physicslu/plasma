# NXP 353 Exact Active — Owner-gated 12 KL25 Layer-1 Production Transaction v4

Date: 2026-10-13. **Owner-gated PR staging: NOT merged into main, NOT deployed, NO physical programming qualification.** One bulk 353-ICPN
assessment, not a vendor-wide Active denominator or a programming-ready list.

## Decision framing

Current authoritative Production `icpn-v1-manifest.json` baseline:
**4,629 exact ICPNs, 28 sources, NXP 0**, all current ST. Production Git
blob lock: `3f66a14212fbf82aa9faa16e9434892f649f736d`.

The 353 official observed Active NXP ordering identities (23
selected manufacturer product pages, 6 series/lane segments) are locked
by exact-set SHA-256
`8d25ee58d833b69d9d6b6bc68bd20d11090c33c543e606507b95ce667267eb24`.

One full-batch, fail-closed status matrix:

| Readiness bucket | Exact count | What it **does not** claim |
| --- | ---: | --- |
| KL25 canonical manufacturer documentation and deterministic OpenOCD route, prepared as **Layer-1-only** proposal | **12** | Production approval, hardware or programming algorithm verification |
| Official exact `/part/` source HTML contains four fields (201 plus 11 independently replayed BGA bumps) | **212** | Canonical datasheet semantics, normalized package suffix/temperature, Backend or HIL |
| Part source/metadata incomplete | **129** | That the commercial Active identity is invalid |

`nxp_layer1_admission_dryrun_v4.py` produces all **353** rows with
explicit source, status, next evidence, authority and admission flags.

## Proposed, not executed: single bounded 12-row KL25 Layer-1 admission

Existing `nxp-kl25-commercial-icpn.csv` is manufacturer-reviewed and
has **12 exact Active SKUs**, verified package/pin/Flash/temperature and
existing `tcl/target/kl25.cfg` route patterned for each of the
three KL25 memory groups. Independent identity, lifecycle, route and
metadata readiness exists in `nxp-kl25-admission-readiness.json`.

Those earlier evidence gates are **not a Production write approval**.
The older readiness record also references a stale 2,683-row
Production prestate; v4 intentionally uses the **live 4,629-row
manifest blob** and fails closed on any subsequent drift rather than
copying old projection counts.

The same PR now **stages one proposed 12-row KL25 Production manifest source on its branch**, while dry-run outputs only transient GitHub Actions review artifacts:

1. A byte-for-byte copy of the locked canonical 12-row KL25 CSV.
2. A **hypothetical** manifest with one appended NXP KL25 source,
   Git-blob identity and SHA-256 integrity binding.
3. A complete 353-row owner-review matrix and machine-readable
   admission/exception summary.

**If** separately authorized and published later, the current 4,629
ST + 12 KL25 catalog would have **4,641** exact ICPNs and 29 source
entries; these numbers are projections only. No additional NXP
families are implied, no Deployment authority is implied.

**Main and deployed Production remain unchanged until a single explicit owner
merge approval.** In the Draft PR branch, the proposed
`data/device-catalog/production/icpn-v1-manifest.json` contains one extra
NXP KL25 source pinned to the reviewed 12-row canonical CSV. The
existing 28 ST source entries remain byte-for-byte reproducible from
the former Production Git blob. The hypothetical manifest in CI is
a separate review artifact and cannot be mistaken for deployment.
No automatic merge or release/deployment is authorized.

## Remaining 129-source bulk triage

**85** exact `/part/` URLs returned non-200. These retain independent
official Active ordering identity from product Package/Quality
tables. Among these:

- **22** end with `R` and have another *Active Exact* identity
  formed by dropping only the last `R`; original peer source
  metadata = 16 four-field / 6 original partial observations.
- **32** end with `R` but lack such an exact Active direct peer
  in the frozen 353 snapshot.
- **31** do not end with `R` at all.

A paired exact identity is only an investigation lead. We do **not**
assert equivalent die, flash, package, lifecycle, temperature, reel
meaning, or software executor route from suffix shape alone. Each
still needs a manufacturer ordering-table provenance bridge before
its metadata can be admitted.

Remaining **44** blocked or partial:

- 8 KW45 multi-valued Flash; official KW45 datasheet Table 1
  is discoverable but both NXP domain PDF binary fetch attempts
  previously returned 404 in GitHub Actions. Treat application and
  radio Flash as separate entities; no scalar inference.
- 23 i.MX RT missing Flash and ambient source fields; **no zero-Flash
  assumption** and no external boot memory substitution.
- 5 MCX missing Flash/ambient.
- 8 KW45 missing ambient.

All 129 remain unresolved; none are automatically promoted.

## Approval and QA gates

- `RESEARCH_ONLY_UNPUBLISHED_LAYER1_DRY_RUN` state is invariant.
- Identity set 353/353, KL25 canonical set 12/12, 129 gap queue
  and 11 previous SHA-locked BGA source fixes must reconcile.
- Current Production manifest SHA/blobs and exact counts must match
  expected prestate; source drift triggers human re-review.
- A known paired R variant must never inherit a metadata field
  without new official exact-SKU/ordering evidence.
- Every row emits:
  `canonical_metadata_admission_authorized=false`,
  `production_write_authorized=false`,
  `programming_backend_qualified=false`,
  `physical_programming_verified=false`.
- Existing KL25 OpenOCD route mapping is **not** the same as
  verified SWD electrical signaling, Flash Programming Configuration,
  security-unlock behavior or PLASMA HIL validation.
- No NXP-global Active denominator or coverage percentage is claimed.

**One final owner approval may authorize merging this staged KL25 Production
source and its updated integrity regressions**; release/deployment and
physical programming approval remain independent domains. Neither permits a runtime
programming job without its separate execution/physical validations.

## Consolidated approval boundary

This change updates **only the Draft PR branch**, not main. The final
approval request will explicitly include the proposed addition of **12 NXP
KL25 exact ICPNs to the Production Catalog** (4629 → 4641, sources 28 → 29).
It will NOT authorize the other 341 research identities, software executor
or device operations, backend binary installation, PPU/SWD/HIL, or deployment.

The existing 4629 ST ICPNs and 28 original source bindings must replay
exactly as before; the 12 KL25 additions are separately manifest-pinned.
All catalog/API tests must show NXP KL25 12 and reject NXP 341.

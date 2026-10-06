# STM32C0 Layer-1 Catalog Admission Proposal v5.5

**Research proposal only. Production publication requires explicit owner approval.**

Merged v5.4 locks the **17 current-Active STM32C0 delta identities** and replays their official ST Ordering Information metadata.

## Proposal

- additions: **17**
- metadata-ready: **17/17**
- bounded metadata exceptions: **0**
- backend scope evaluated: **false**
- backend type asserted: **none**
- backend state for all proposed rows: **`no_mapping`**
- Programming Profile: **unresolved**

## Delta semantics

Two current package combinations extend the older C0.3 bounded authority:

- STM32C011 `D/Y` → **WLCSP12**
- STM32C051 `D/Y` → **WLCSP15**

The lifecycle delta `STM32C091KBT3` is admitted as a current Active catalog identity; its earlier C0.2 Preview state is not carried forward.

## Frozen proposal locks

- exact-set SHA-256: `03b7202842b52aaa6362386864d60c62f64d9cefea74d2d039691ea170b79097`
- proposal CSV SHA-256: `ae20c35416e7144613f0aa5041676e382fe8e077836794ea31a466ec78d72e80`
- base authority SHA-256: `691733479e7f89ac9f9fe1dbd7cd95a7db6be8b27e7d75a77ae38b853d3899b0`
- delta authority SHA-256: `b2a48e10b40db576b46b8ecec926d033dffccb777028d3e27b752f03dcf79ac4`
- source workflow run: `37472025031`
- source artifact: `11417885710`
- artifact ZIP SHA-256: `8e877965282eb3b46f4fe131de3591ea11616d7232884b701f131ba6d8a7968a`

## Projected state only if later explicitly approved

- STM32C0 Active identity coverage: **209/226 → 226/226 = 100%**
- STM32C0 Production source rows: **209 → 226**
- Production exact total: **4,589 → 4,606**
- Production source count: **28 → 28**
- backend partition: **3,673 mapped / 916 no_mapping → 3,673 mapped / 933 no_mapping**
- whole-ST Active intersection: **4,510 → 4,527 / 4,550**
- whole-ST Active gap: **40 → 23**
- whole-ST Active identity coverage: **99.1209% → 99.4945%**

## Boundary

No Production file is changed by this proposal.

No backend route, Programming Profile support, Engineering Verified state, field evidence, or PS/HIL qualification is claimed.

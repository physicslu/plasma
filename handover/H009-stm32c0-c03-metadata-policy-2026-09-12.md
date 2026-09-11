# H009 — STM32C0 C0.3 Metadata Policy Handover

**Date:** 2026-09-12  
**Status:** Current engineering handover / C0.3 Gate 1 approved, implementation pending  
**Primary workstream:** Device Catalog / STM32C0  
**Repository:** `physicslu/plasma`  
**Current `main` baseline:** `f45a797dce1603a0a4016fc11450541d35a57c6e`  
**Current C0.3 branch:** `agent/device-catalog-stm32c0-phase-c03-metadata-policy`

---

## 1. Executive Summary

STM32C0 commercial discovery is complete through C0.2. The next approved transaction is **C0.3 — Manufacturer-Authoritative Commercial Metadata Policy**.

Current phase ledger:

```text
C0.0  Post-U0 next-family evidence selection       DONE / MERGED
C0.1  Deterministic STM32C0 research foundation    DONE / MERGED
C0.2  Manufacturer-authoritative commercial discovery DONE / MERGED
C0.3  Commercial metadata policy                   GATE 1 APPROVED / IMPLEMENTATION PENDING
C0.4  Read-only admission plan                     NOT STARTED
C0.5  Controlled canonical + Production publication NOT STARTED
```

C0.3 must convert the **retained 220 Active exact STM32C0 ICPNs** into deterministic canonical metadata using official ST Ordering Information semantics while preserving the commercial identity/lifecycle evidence boundary established by C0.2.

C0.3 does **not** admit STM32C0 to Production and does not prove programming capability, Flash-controller behavior, option/security semantics, HIL/electrical qualification, or runtime support.

---

## 2. Governance Contract

`AGENTS.md` defines exactly two approval gates:

```text
Gate 1 = Plan Approval before implementation
Gate 2 = Merge Approval when merge-ready
```

Gate 1 for C0.3 has already been approved by the user in the originating session.

Therefore the next session should **continue implementation autonomously on the existing C0.3 branch**. Do not ask for Gate 1 again unless the required work materially exceeds the approved C0.3 metadata-policy scope.

Stop only at Gate 2 when the transaction is merge-ready.

Repository source-of-truth priority remains:

```text
Executable code/config > tests/contracts > current docs > handover/history
```

This handover records state; it does not override newer repository facts.

---

## 3. Completed C0 Transaction Ledger

### C0.0 — Post-U0 next-family evidence selection

- PR: `#489`
- Merge commit: `85115361606fee7f51c67513052c369303a469ea`
- Frozen selection SHA-256: `f2bc4d955952cc8c25362ca5568e944470f7a1b43bf41dee2fcca9516e9c8773`
- Result: `selected_next_research_family = STM32C0`
- Selection basis:
  - C0 and L0 had equivalent clean manufacturer-evidence quality;
  - L1 remained lifecycle-heavy and was deprioritized, not permanently rejected;
  - deterministic current shortlist order selected C0.

Do not rewrite the older H006 artifact to make it appear that C0 was selected historically. H006 remains the historical U0-selection record.

### C0.1 — Foundation

- PR: `#490`
- Merge commit: `ae0e16d9cf0473529fb7bc4468d08796ac2b3855`
- Frozen foundation SHA-256: `c89e8c528f80f9b199a2b153d3d40aa4af090e50c492a7c88bfa7876ce406515`
- Frozen research surface:
  - 95 OpenOCD source rows
  - 73 `ordering_pattern` rows
  - 22 CMSIS aliases
  - 6 subfamilies: C011 / C031 / C051 / C071 / C091 / C092
  - target config: `tcl/target/stm32c0x.cfg`
- Deterministic representative Base Devices:
  - `STM32C011F4`
  - `STM32C031C4`
  - `STM32C051C6`
  - `STM32C071C8`
  - `STM32C091CB`
  - `STM32C092CB`

C0.1 representative evidence contained 21 Active exact ICPNs. Those 21 were continuity controls only; they were never the complete family inventory.

### C0.2 — Manufacturer-authoritative commercial discovery

- PR: `#491`
- Merge commit / current `main`: `f45a797dce1603a0a4016fc11450541d35a57c6e`
- Live workflow run: `34573244983`
- Retained evidence root:
  - `data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/`
- C0.2 baseline:
  - `data/device-catalog/research/stm32c0-phase-c0.2-discovery-baseline.json`
- Deterministic discovery boundary:
  - **50 unique Base Devices** collapsed from the 73 frozen C0.1 ordering patterns
- Subfamily Base Device counts:
  - C011 = 4
  - C031 = 8
  - C051 = 8
  - C071 = 10
  - C091 = 10
  - C092 = 10
- Authoritative outcome:
  - 50 / 50 Base Devices dispositioned
  - 50 / 50 commercial identities verified
  - **220 unique Active exact ICPNs** retained
  - 0 source-unavailable targets
  - 0 identity manual-review targets
  - 0 lifecycle-only Base Devices
  - 1 non-Active exact part excluded fail-closed: `STM32C091KBT3` (`Preview`)
- OpenOCD routing observation:
  - 44 unique
  - 6 unmapped
  - routing explicitly does **not** gate commercial identity

Commercial identity/lifecycle authority for C0.2 is:

```text
official ST Quality & Reliability exact identity
+
official ST Sample & Buy Marketing Status
+
fail-closed exact-Part-Number-set join
```

Do not replace this with a Q&R-only assumption. C0 pages do not expose lifecycle in the same Q&R layout as some other STM32 families.

---

## 4. Production Boundary

At the C0.3 transaction start:

```text
Production exact ICPNs:      703
Production Base Devices:     243
Production STM32 families:   9
Production STM32C0 ICPNs:    0
```

The 220 C0.2 Active exact ICPNs are **research/discovery identities only**.

Do not report:

```text
703 + 220 = 923 Production ICPNs
```

until a later controlled publication transaction actually modifies Production.

C0.3 must keep Production byte-for-byte unchanged unless the user explicitly approves a new scope. Production publication belongs to a later C0.5-style transaction.

---

## 5. C0.3 Approved Scope

C0.3 is a deterministic metadata-policy transaction over **exactly the 220 retained Active exact ICPNs from C0.2**.

The approved authority split is:

```text
Commercial identity / lifecycle
    -> retained C0.2 official-ST evidence

Canonical commercial metadata semantics
    -> official ST datasheet Ordering Information

OpenOCD routing
    -> observation only; not metadata authority

CMSIS aliases
    -> research convenience only; not metadata authority
```

The C0.3 implementation should follow the proven U0.3 architectural pattern but must not mechanically copy U0 grammar.

Primary metadata dimensions should remain compatible with the existing Device Catalog canonical metadata model where semantically valid:

```text
manufacturer
icpn
family
series
base_device
package
pin_count
flash_size
temperature_grade
option_suffix
source_type
source_reference
source_authority
verification_status
```

If C0 requires a richer semantic representation to avoid information loss, do not silently overload an existing field. Preserve compatibility where possible, but semantic correctness is higher priority than superficial schema reuse. Any schema expansion that materially changes canonical Device Catalog contracts must be treated as a scope question rather than slipped into C0.3.

---

## 6. Official Ordering Information Authorities

Existing retained C0 Ordering Information review is:

`data/device-catalog/research/stm32-u0-c0-ordering-authority-review.json`

The currently frozen official ST authorities are:

| Subfamily | Representative | Datasheet | Revision | Ordering section | PDF page |
|---|---|---|---:|---:|---:|
| STM32C011 | STM32C011F4 | DS13866 | 5 | 7 | 93 |
| STM32C031 | STM32C031C4 | DS13867 | 4 | 7 | 100 |
| STM32C051 | STM32C051C6 | DS14721 | 2 | 7 | 107 |
| STM32C071 | STM32C071C8 | DS14693 | 2 | 7 | 128 |
| STM32C091 | STM32C091CB | DS14720 | 3 | 7 | 121 |
| STM32C092 | STM32C092CB | DS14720 | 3 | 7 | 121 |

C091 and C092 legitimately share DS14720; the Ordering Information explicitly resolves `09x` to 091 or 092.

Before freezing C0.3 metadata authority, verify that these official ST document revisions have not drifted. Revision drift must fail closed or trigger an explicit authority refresh; it must not be silently accepted.

---

## 7. Critical C0 Ordering Semantics

### C071 `N` product-version option

C0 evidence contains real Active commercial identities including:

```text
STM32C071C8T6N
STM32C071C8U6N
```

The retained official Ordering Information review states:

```text
N is an official product-version option and must not be normalized away.
```

This is a hard semantic control.

Do not:

- strip `N` as noise;
- collapse an `N` part into the non-`N` part;
- treat `N` as equivalent to `TR` packing;
- infer suffix semantics from CMSIS/OpenOCD patterns.

The C0.3 parser must preserve the exact commercial identity and represent the manufacturer-defined option without losing meaning.

### Packing vs product-version semantics

`TR` is packing. `N` is a product-version option. They are not equivalent semantic dimensions merely because both occur after the package/temperature portion of an ordering code.

If the existing `option_suffix` field is used, tests must prove that values remain distinguishable and deterministic. Do not normalize different manufacturer semantics into the same canonical value unless the canonical model explicitly supports that equivalence.

### C091 / C092 shared authority

The shared DS14720 authority must not collapse C091 and C092 into one series. Exact Base Device / series identity remains manufacturer-defined and must stay distinct.

---

## 8. Expected C0.3 Engineering Outputs

The next session should implement C0.3 on the existing branch and produce, at minimum:

1. A C0-specific metadata policy/adapter with fail-closed parsing.
2. A frozen C0.3 Ordering Information authority artifact derived from official ST authority, with revision bindings and bounded semantics actually used by the 220 retained identities.
3. Deterministic candidate construction from C0.2 retained evidence only.
4. Exactly one metadata decision per retained Active exact ICPN.
5. A frozen C0.3 policy baseline containing counts, digests, authority bindings, Production prestate, and false capability/admission claims.
6. Negative/boundary tests covering unknown suffixes, unretained identities, CMSIS aliases, authority drift, malformed exact identities, duplicate identities, and semantic-collapse cases.
7. Explicit tests preserving C071 `N` variants.
8. Deterministic metadata-row digest / replay check.
9. Permanent read-only C0.3 CI and centralized `stm32c0` family-CI integration.
10. A transaction document explaining authority separation, metadata semantics, counts/distributions, fail-closed behavior, and the next phase boundary.

If all 220 retained identities can be decoded from official bounded Ordering Information semantics, expected closure is:

```text
metadata_ready = 220
manual_review = 0
reject = 0
```

This is an expected target, **not a result to force**. Any unbound manufacturer code must fail closed rather than being guessed to reach 220/220.

---

## 9. Required Negative Controls

At minimum, C0.3 should reject or block the following:

- an exact ICPN not present in the frozen C0.2 Active set;
- a CMSIS alias presented as commercial identity;
- a C0.2 excluded/non-Active part being promoted to metadata-ready;
- unknown package, pin/package, Flash, temperature, packing, or product-version code;
- C071 `N` being silently removed;
- `N` being treated as `TR` or vice versa;
- C091/C092 series collapse;
- official Ordering Information document/revision drift;
- OpenOCD routing becoming a metadata gate or metadata authority;
- any Production write;
- any canonical-admission/programming/HIL/runtime claim becoming true.

The known excluded `STM32C091KBT3` Preview part is a useful negative continuity control: C0.3 must not create a metadata-ready row for it.

---

## 10. Explicit Non-Claims

C0.3 metadata completion does not mean:

```text
commercial identity verified
== canonical admitted
== Production published
== programmable
== OpenOCD route complete
== Flash algorithm qualified
== option/security semantics qualified
== electrical/socket qualified
== HIL qualified
== PPU runtime supported
```

Keep these states separate.

In particular, C0.2 has six Base Devices with unmapped OpenOCD routing. That does not invalidate manufacturer commercial identity and must not block metadata derivation when official Ordering Information is complete.

---

## 11. Relevant Repository References

Current C0 inputs:

- `data/device-catalog/research/stm32c0-phase-c0.1-foundation-baseline.json`
- `data/device-catalog/research/stm32c0-phase-c0.2-discovery-manifest.json`
- `data/device-catalog/research/stm32c0-phase-c0.2-discovery-baseline.json`
- `data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/`
- `data/device-catalog/research/validate_stm32c0_phase_c0_2_retained_evidence.py`
- `data/device-catalog/research/stm32-u0-c0-ordering-authority-review.json`

U0.3 precedent to reuse architecturally, not mechanically:

- `data/device-catalog/research/device-catalog-stm32u0-phase-u0.3-metadata-policy.md`
- `data/device-catalog/research/stm32u0_metadata_policy.py`
- `data/device-catalog/research/stm32u0_phase_u0_3_policy.py`
- `data/device-catalog/research/stm32u0-phase-u0.3-ordering-authority.json`
- `data/device-catalog/research/stm32u0-phase-u0.3-policy-baseline.json`

Historical STM32 selection context:

- `handover/H006-stm32-next-family-evidence-selection-2026-09-10.md`

Do not modify H006 to reflect later C0 progress. H009 supersedes H006 only for **current STM32 Device Catalog continuation state**.

---

## 12. Recommended Next-Session Procedure

1. Read `AGENTS.md` and H009.
2. Verify current `main` and the C0.3 branch for drift before writes.
3. Re-read C0.2 retained evidence validator and U0.3 metadata precedent.
4. Revalidate official C0 Ordering Information revisions/bindings.
5. Enumerate all suffix/code combinations actually present across the 220 retained Active ICPNs before defining grammar.
6. Define only the bounded semantics needed by those retained identities.
7. Implement fail-closed metadata parsing and negative controls.
8. Freeze deterministic metadata rows and their digest.
9. Add C0.3 permanent CI / centralized family CI integration.
10. Open/update the C0.3 PR, repair CI autonomously within Gate 1 scope, and stop only when merge-ready for Gate 2.

Do not start C0.4 or Production publication in the same Gate 1 transaction.

---

## 13. Copy/Paste Prompt for the Next Session

```text
Read repo handover H009 and AGENTS.md, then continue STM32C0 C0.3 Manufacturer-Authoritative Commercial Metadata Policy on branch agent/device-catalog-stm32c0-phase-c03-metadata-policy.

Gate 1 for C0.3 is already approved. Verify current main/branch drift first, then continue autonomously within C0.3 scope through implementation, tests, permanent CI, PR repair, and Ready-for-review. Stop only at Gate 2.

Treat C0.2 as closed manufacturer-authoritative discovery: 50 Base Devices, 220 unique Active exact ICPNs, one Preview part STM32C091KBT3 excluded, Production unchanged at 703 exact ICPNs. Commercial identity/lifecycle authority remains retained C0.2 official-ST evidence. Metadata authority is official ST Ordering Information.

Preserve C071 N product-version semantics; do not normalize N away or treat it as TR packing. Preserve C091 and C092 as distinct series despite their shared DS14720 authority. OpenOCD routing and CMSIS aliases are not metadata authority.

Do not write Production, do not begin C0.4/C0.5, and do not claim programming, Flash-controller, option/security, HIL/electrical, or runtime support. Any unbound ordering code must fail closed rather than be guessed.
```

---

**End of H009.**

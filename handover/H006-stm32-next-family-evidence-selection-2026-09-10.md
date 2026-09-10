# H006 — STM32 Next-Family Evidence Selection Handover

**Date:** 2026-09-10  
**Status:** Current engineering handover — research-family selection formed, PR/merge closure still pending  
**Repository:** `physicslu/plasma`  
**Main at handover creation:** `519a81bf563b3b024e21b8e31d2bef5288a8e786`  
**Working branch:** `agent/device-catalog-stm32-evidence-accessibility-selection`  
**Selection-content head before this handover commit:** `9ee82da2f2cabdb125d2a4985c7b0e164a2a8916`

This handover captures the STM32 Device Catalog state after STM32G4 publication, cross-family prioritization, the U0/C0/L1 manufacturer-evidence accessibility probe, and the U0-vs-C0 Ordering Information review. It is intended to let a new session continue without reconstructing the decision chain from chat history.

## 1. Executive state

The Production Device Catalog remains:

- **635 exact ICPNs**
- **217 Base Devices**
- **8 STM32 families in Production**

Production exact-ICPN counts are:

| Family | Exact ICPNs |
|---|---:|
| STM32F0 | 42 |
| STM32F1 | 75 |
| STM32F2 | 33 |
| STM32F3 | 10 |
| STM32F4 | 384 |
| STM32F7 | 19 |
| STM32G0 | 47 |
| STM32G4 | 25 |
| **Total** | **635** |

`STM32U0`, `STM32C0`, and `STM32L1` are **not** in Production at this handover boundary.

The next research family has now been deterministically selected as:

> **STM32U0**

This is a **research-selection decision only**. It does **not** authorize canonical admission, Production publication, programming-policy equivalence, Flash-geometry assumptions, option/security semantics, physical/HIL qualification, or runtime programming support.

## 2. Important closed work before this handover

### STM32G4 Phase 4.9E

STM32G4 controlled publication was closed before this workstream continued.

- Production moved from 610 to 635 exact ICPNs.
- STM32G4 contributed 25 exact ICPNs / 8 Base Devices.
- Publication did not create programming-support claims.

### Cross-family prioritization governance

The historical F-line-only prioritization path was not rewritten. A separate cross-family prioritization policy was established and closed.

Frozen prioritization baseline SHA-256:

`9a99865865f048e6a7636efd82cb17958fdc593240a329e18e3b68d8b0f862f9`

Frozen research shortlist:

1. `STM32U0`
2. `STM32C0`
3. `STM32L1`

The frozen prioritization artifact itself intentionally kept:

`selected_next_research_family = null`

Selection was deferred to a separate manufacturer-evidence gate.

The frozen Production prestate SHA-256 used by that policy is:

`93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d`

## 3. U0 / C0 / L1 official-ST identity/lifecycle probe

A single retained live official-ST accessibility probe was executed across 13 deterministic representative Base Devices.

### Deterministic representatives

STM32U0:

- `STM32U031C6`
- `STM32U073C8`
- `STM32U083CC`

STM32C0:

- `STM32C011F4`
- `STM32C031C4`
- `STM32C051C6`
- `STM32C071C8`
- `STM32C091CB`
- `STM32C092CB`

STM32L1:

- `STM32L100C6`
- `STM32L151C6`
- `STM32L152C6`
- `STM32L162QC`

Selection rule for representatives: use the lexicographically first concrete Base Device in each guarded OpenOCD `ordering_pattern` subfamily surface. CMSIS-only aliases are not allowed to define the commercial-identity probe target set.

### Retained live-probe results

| Family | Representative targets | Active targets | Active exact ICPNs observed | Lifecycle-only targets | 404/manual |
|---|---:|---:|---:|---:|---:|
| STM32U0 | 3 | 3 | 8 | 0 | 0 |
| STM32C0 | 6 | 6 | 21 | 0 | 0 |
| STM32L1 | 4 | 1 | 1 | 3 | 0 |

STM32L1 is therefore **deprioritized for next-family research due to lifecycle**, not rejected for future support. Three of four L1 representatives are lifecycle-only / NRND. This is a resource-prioritization conclusion, not a technical-support verdict.

The C0 live evidence also preserved two real commercial `N` variants:

- `STM32C071C8T6N`
- `STM32C071C8U6N`

Do not normalize the `N` suffix away. Manufacturer commercial identity remains authoritative over CMSIS/OpenOCD alias surfaces.

### Retained evidence bindings

- Live workflow run: `34436667425`
- Executed SHA: `e30c2aca6a3f4e3ede3b40e6352aa9d8dbe2d163`
- Artifact ID: `10136442964`
- Artifact ZIP SHA-256: `4423e91a1c5eec5491084e6fedd7afc5a53f1701ec583f86163d2ddf64c16d4b`
- Retained accessibility baseline SHA-256: `473e979818770fda2661e963d064f3a0cfbd7cbcad920203e7f358b5b6e140b6`
- Retained summary SHA-256: `d4339d85a7565f4be731de863ee7db0c1301a335bb5b2777e84a1089aae2769d`
- Retained provenance SHA-256: `8c5751803719449ed0be345c2a1b264f7dfa4341faf41c22cbefc2a8aca3d1d7`

Do **not** reacquire this historical live evidence during replay. Replays must use retained repository evidence.

## 4. U0 vs C0 Ordering Information evidence-quality gate

GitHub-hosted runner attempts to transport raw ST PDF bytes were not reliable. Those failures were classified as transport/method limitations, not family-quality failures. They must not be used as selection evidence.

The final evidence-quality comparison therefore uses official ST datasheet authority, structured text review, and visual review where available. Visual screenshot cache availability is audit support, not a selection gate.

Review artifact:

`data/device-catalog/research/stm32-u0-c0-ordering-authority-review.json`

Review SHA-256:

`3fe019d420cbe43c732b9d403acaa2f1b0bf0dc583b38073eb25528217f5efe9`

The required Ordering Information schema is:

- device family
- product type
- device subfamily
- pin count
- Flash memory size
- package
- temperature range
- packing/options

All nine U0/C0 representatives have complete required schema coverage.

### Official datasheet authorities

| Base Device | DS | Rev | Ordering page | Notes |
|---|---|---:|---:|---|
| STM32U031C6 | DS14581 | 2 | 124 | complete |
| STM32U073C8 | DS14548 | 2 | 135 | complete |
| STM32U083CC | DS14463 | 2 | 135 | complete |
| STM32C011F4 | DS13866 | 5 | 93 | complete |
| STM32C031C4 | DS13867 | 4 | 100 | complete |
| STM32C051C6 | DS14721 | 2 | 107 | complete |
| STM32C071C8 | DS14693 | 2 | 128 | `N` is an official product-version option |
| STM32C091CB | DS14720 | 3 | 121 | shared 09x authority |
| STM32C092CB | DS14720 | 3 | 121 | shared 09x authority |

`STM32C091` and `STM32C092` legitimately share `DS14720`; document sharing is not evidence ambiguity.

Result of this gate:

`equivalent_required_evidence_quality`

Both U0 and C0 have zero blocking evidence issues for this research-selection purpose.

## 5. Deterministic next-family selection

Selection artifact:

`data/device-catalog/research/stm32-next-family-selection.json`

Selection SHA-256:

`2c81a6c3495a75a6f4115252293af6e99b727f3d12d67f31853922279a96d017`

Selection inputs are hard-bound to:

- cross-family prioritization SHA-256: `9a99865865f048e6a7636efd82cb17958fdc593240a329e18e3b68d8b0f862f9`
- identity/lifecycle accessibility baseline SHA-256: `473e979818770fda2661e963d064f3a0cfbd7cbcad920203e7f358b5b6e140b6`
- Ordering Information review SHA-256: `3fe019d420cbe43c732b9d403acaa2f1b0bf0dc583b38073eb25528217f5efe9`
- Production prestate SHA-256: `93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d`

Decision:

`selected_next_research_family = STM32U0`

Reason: U0 and C0 have equivalent required manufacturer-evidence quality, so the already-frozen shortlist order is the deterministic tie-break. U0 is first and also has the smaller bounded research surface.

This decision must not be reinterpreted as an admission or programmer-support decision.

## 6. Permanent validation assets currently on the working branch

Permanent workflow:

`.github/workflows/device-catalog-stm32-evidence-accessibility-validation.yml`

The workflow now validates four layers:

1. accessibility-probe policy and negative controls
2. immutable retained manufacturer evidence replay
3. U0/C0 ordering-selection negative controls
4. U0/C0 ordering evidence and next-family research-selection replay

Relevant permanent files include:

- `data/device-catalog/research/stm32-evidence-accessibility-probe-manifest.json`
- `data/device-catalog/research/stm32-evidence-accessibility-probe-baseline.json`
- `data/device-catalog/research/stm32_evidence_accessibility_probe.py`
- `data/device-catalog/research/test_stm32_evidence_accessibility_probe.py`
- `data/device-catalog/research/validate_stm32_evidence_accessibility_probe_retained.py`
- `data/device-catalog/research/evidence/stm32-u0-c0-l1-evidence-accessibility-probe-live-2026-09-10/`
- `data/device-catalog/research/stm32-u0-c0-ordering-authority-review.json`
- `data/device-catalog/research/stm32-next-family-selection.json`
- `data/device-catalog/research/stm32-next-family-selection.md`
- `data/device-catalog/research/test_stm32_u0_c0_ordering_selection.py`
- `data/device-catalog/research/validate_stm32_u0_c0_ordering_selection.py`

The hard-lock validator expects the selection SHA-256 above and requires all authority-boundary booleans to remain false.

## 7. Repository / branch state at handover

Current `main` at handover creation:

`519a81bf563b3b024e21b8e31d2bef5288a8e786`

The working branch content head immediately before creating this handover was:

`9ee82da2f2cabdb125d2a4985c7b0e164a2a8916`

At that point, comparing current main to the working branch showed:

- status: `diverged`
- ahead by: 7 commits
- behind by: 3 commits
- merge base: `9451ba5c098b7aaf17263335a89ec31dd00ba033`

The three commits missing from the working branch are newer `main` work, including NXP/KL25 work. Before opening a PR, the next session must inspect overlap and rebuild/rebase the verified STM32 assets onto latest `main` if necessary. Do not open a PR from a stale/diverged branch without this audit.

No formal PR/merge closure for this STM32 evidence-selection transaction had been completed at handover creation.

## 8. Trust boundaries — do not violate

The following remain **false / unauthorized** after selecting U0:

- `canonical_admission_authorized`
- `production_write_authorized`
- `programming_algorithm_equivalence`
- `programming_policy_defined`
- `flash_geometry_qualified`
- `option_security_semantics_qualified`
- `physical_hil_qualified`
- `runtime_programming_support_claimed`

Additional rules:

- OpenOCD routing is not commercial-identity authority.
- CMSIS aliases are not commercial-identity authority.
- A source 404 is source-unavailable evidence, not proof of product nonexistence.
- NRND means lifecycle deprioritization, not technical incompatibility.
- Shared datasheet authority is valid when the official Ordering Information table explicitly resolves the variants.
- Never strip `STM32C071...N` product-version semantics.
- Historical retained evidence must be replayed, not reacquired.
- Selection of U0 does not authorize writing any U0 row into the canonical Production dataset.

## 9. Exact next-session continuation

The next session should execute this sequence rather than reopening the selection question:

1. Read `AGENTS.md`, `WORKSTREAMS.md`, this handover, and the checked-in selection/validator files.
2. Fetch current `main` and current working-branch head; do not assume the SHAs in this handover are still current.
3. Compare latest `main` against `agent/device-catalog-stm32-evidence-accessibility-selection`.
4. If main drift is non-overlapping, rebuild or rebase the verified permanent assets onto latest main. Preserve the frozen evidence bytes and all historical digests.
5. Run the permanent STM32 evidence-accessibility workflow or equivalent branch-local replay. Require:
   - accessibility negative controls PASS
   - retained evidence replay PASS
   - ordering-selection negative controls PASS
   - ordering/selection hard-lock replay PASS
6. Confirm Production remains 635 exact ICPNs / 217 Base Devices / 8 families and U0/C0/L1 remain absent from Production.
7. Remove any temporary / diagnostic / one-off workflow before PR. The failed PDF-transport experiments must not enter the formal PR.
8. Open the formal PR for the evidence-accessibility + next-family-selection transaction.
9. Require PR gates for the STM32 evidence selection, global/current Device Catalog, and repository contracts as applicable.
10. Merge only with expected-head protection after checking base drift.
11. Run exact merge-commit post-merge closure.
12. Only after this transaction is formally CLOSED should a new STM32U0 family pipeline begin.

## 10. What the next STM32U0 pipeline should and should not assume

Once the selection transaction is closed, STM32U0 becomes the next **research target family**, not a prequalified programmer family.

A new U0 family pipeline should independently establish, in order:

1. bounded OpenOCD-derived family surface
2. official ST commercial identity/lifecycle evidence
3. manufacturer-authoritative metadata / Ordering Information policy
4. guarded capability/admission semantics
5. controlled canonical publication, if qualified
6. programming-policy / Flash-controller semantics as a separate qualification layer
7. physical/HIL/runtime qualification as separate gates

Do not infer Flash-controller equivalence with STM32G0 or any other family merely because the architecture, OpenOCD route, or naming looks similar.

## 11. Suggested prompt for the new session

Use:

```text
Read repo handover H006 and continue the STM32 next-family evidence-selection transaction. Verify current main/branch drift first. The research selection is already STM32U0; do not reopen the U0-vs-C0 decision unless checked-in evidence is inconsistent. Finish permanent replay, PR/merge/post-merge closure, keep Production at 635/217/8, and do not claim programming/HIL/runtime support. After closure, start a separate STM32U0 family research pipeline.
```

## 12. Authority note

This handover records engineering state and continuation intent. It does not override `AGENTS.md`, checked-in executable validators, immutable retained evidence, or newer repository state. If this document conflicts with newer code, tests, signed/merged commits, or repository contracts, the newer authoritative repository state wins.

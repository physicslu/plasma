# NXP — ADR-0002 Phase 1 / Phase 2 Canonical Contract & Gap Audit v1

**Scope:** NXP only. **Normative authority:** [ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md), as present on the same commit. Historical NXP research priority P0/P1/P2 ledgers remain immutable, but **shall not be used as new product Phase states, criteria, counters or scheduling gate**.

## Findings: historical approach vs ADR-0002

| Concern | Existing NXP historical method | Required current behavior |
| --- | --- | --- |
| Phase 1 identity | v13 501 records, 224 admitted / 277 research; five reviewed official material cohorts | **Only** exact official manufacturer-identified ICPNs count as S1; 297 verified S1; 279 still unresolved in bounded 576 source universe |
| Phase 1 information | v13 vendor fields may have UNKNOWN rail/Base | `INFORMATION_COMPLETE` is separate; current strict evidenced snapshot **0**, not a Phase 1 selector gate |
| Phase 2 input | Historical OpenOCD v10 investigates **501** archived source rows | **Phase 2 must be a subset of the currently valid Phase 1 S1 set (297 unique exact ICPNs)**. Research-only 277 cannot inherit software qualification |
| Phase 2 research priority | `P0=27/P1=38/P2=436` separate classifications; replay scripts pin an old ADR blob | Do **not** emit or depend on those research priority classifications as present Phase states; keep archived source byte locks for forensic replay |
| OpenOCD source facts | Upstream 0.12.0 full commit and Tcl/Driver source symbols preserved | Retain pinned Provider, Target CFG/Include, Flash Driver. A source symbol or generic family driver alone **cannot** qualify exact IC silicon and operations |
| Phase 2 status | Historical ledgers show `CANDIDATE` / `UNKNOWN` but include source-only unsupported membership | Project only the **28 Phase 1-identified rows with positive but incomplete archived provider evidence as `CANDIDATE`**; the other **269 remain `UNKNOWN`** |
| `SUPPORTED` | No archived exact NXP silicon ID + revision + geometry + security + version-locked operation-complete Programming Profile in this cohort | **0 newly certified in this audited snapshot**. This is not a claim that no NXP IC could ever work on any installed/alternative programming backend |
| Phase 3 | No configuration-bound HIL evidence in this source study | `NOT_AUDITED`, **not** `PASSED`; no Phase 3 count inferred |
| IC Selector | Previously only Production admission; Phase 1 fix is separate PR #927 | S1 identity visible independent of S2 status; Phase 2 never revokes genuine S1 identity. **No runtime change in this PR** |
| Job/Batch execution | Independent Production/Runtime gate | Continue fail-closed. Phase 1 or Phase 2 research evidence does not authorize execution |

## Reproducible source bound snapshot

| NXP exact ICPN state | Audited count | Description |
| --- | ---: | --- |
| **Phase 1 `IDENTIFIED`** | **297** | 224 archived manufacturer-admitted exact + 73 official NXP material/12NC crosswalked |
| Phase 1 `INFORMATION_COMPLETE` | **0** | Confirmed strict full-field evidence in current bounded snapshot |
| Phase 2 `CANDIDATE` | **28** | 12 KL25 source-backed `kl25.cfg`/kinetis driver research; 16 K32L2 Kinetis flash-driver clues **without approved target CFG** |
| Phase 2 `UNKNOWN` | **269** | 196 previously admitted old-source UNKNOWN + 73 newly discovered S1 not yet individually reviewed in the archived Phase 2 research |
| Phase 2 `SUPPORTED` from this source audit | **0** | No exact-ICPN silicon/geometry/security/read-verify/approved Programming Profile evidence in reviewed inputs |
| Phase 2 `UNSUPPORTED` | **0** | Lack of source evidence cannot become permanent universal incompatibility |
| Phase 3 `PASSED` | **NOT AUDITED** | No physical Site/Socket/PPU combination examined in this audit |

The correct exact NXP `CANDIDATE` count is **28, not the historical P0 27 nor historical P1 38**. The older K32L2 source study contains 20 rows, but **only 16 of those belong to the Phase 1 IDENTIFIED set**. The 4 other historical candidate strings **must not** cross the S1-to-S2 boundary until manufacturer identity is independently qualified. LPC84x legacy source-only research 15 similarly does not become a qualified exact ICPN by CFG alone.

## Stage gates to earn exact Phase 2 SUPPORTED

The next NXP Phase 2 eligibility work MUST, for each exact ICPN (or evidenced exact-applicable family/variant group), record:

1. **Phase 1 exact ICPN identity authority**: manufacturer official material/order code, Base/Family crosswalk, source scope and provenance.
2. **Pin Provider runtime**: OpenOCD version + source commit + installed runtime identity, rather than OpenOCD upstream master, config filename or generic driver alone.
3. **Target compatibility**: complete Tcl CFG/include graph, debug transport (SWD/JTAG), silicon **ID/revision** and exact orderable variant's applicability; reject unsupported part ID and unsafe abort paths.
4. **Flash programming mechanics**: Flash Bank/controller, address map/geometry/sector boundaries, IAP if relevant, Security/FCF/flash-protection policy, voltage and reset/clock constraints, with separately scoped official NXP Programming Guide/Reference Manual evidence.
5. **Operations**: separately qualify requested **Erase / Program / Read / Verify** and readback/memory comparison policy, including constraints/errors. A driver exposing function names is not operational proof. Record scoped **Programming Profile ID, provider identity, evidence/provenance and review decision**.
6. **State**: only qualification-complete exact ICPN becomes `SUPPORTED`; otherwise `CANDIDATE` / `UNKNOWN` with explicitly named missing evidence, or `UNSUPPORTED` only when a specific provider/version/operation has an independently verified negative outcome. Do not delete valid Phase 1 identity for Phase 2 failure.
7. **Independent Phase 3 and Job gates**: no invented HIL PASS or production/runtime programming authorization.

## Legacy retention and source-quality controls

- Keep v9–v12 historical ledgers, their `P0/P1/P2` fields, Git hashes and original metadata **unchanged**. They are input **research artifacts**, not the active state machine. In particular, `nxp_adr0002_core_qual_v10.py` compares the ADR to an old frozen hash and should not be invoked as the source of the current policy.
- The new `nxp_adr0002_phase1_phase2_canonical_v1.py` derives the current cross-phase data from **source-locked** Phase 1 ledgers and pinned old source-only v10 CSV; it **does not execute** obsolete v10 Python logic.
- Original manufacturer source bytes custody: the **73** new NXP material ledgers have URLs and 12NC observations but do not claim original NXP PDF/HTML archiving or SHA-256. For the 224 admitted historical identities, original binary custody is separately unverified.
- Base relation gaps: **212** historical admitted NXP Base Device values still mirror full ICPN, explicitly `UNRECONCILED_ALIAS`; this does not annul a valid exact commercial identity.
- The provider research pin is upstream OpenOCD **0.12.0**, commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`. **This is not a confirmed deployed provider or physical test**. Any mismatch requires separate Phase 2 reevaluation.
- No modifications to Production manifest, public IC Selector, application API, OpenOCD runtime, PPU/Site/Socket or HIL. **PR #927**, which addresses Phase 1 visibility, is separate and must not be represented as merged/deployed by this report.

## Replay and acceptance

```bash
python data/device-catalog/research/nxp_adr0002_phase1_phase2_canonical_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_adr0002_phase1_phase2_canonical_v1.py' -v
```

CI rejects promotion of archived source research to software `SUPPORTED`, duplicate ICPNs, S1 identity loss, fabricated operations/Flash geometry/Programming Profiles/HIL, false source custody, and old-priority classification in the canonical Phase state contract.

**Definition of done for this audit PR:** NXP current Phase 1 / Phase 2 policy is consistently represented and reproducible, with a corrective gap report and reviewed negative gates. **This does not mean the 297 ICPNs have all completed Phase 2 programming qualification.**

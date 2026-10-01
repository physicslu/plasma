# STM32G0 Active Exact Gap Layered Triage v1.5

**Research only. No Production write.**

The official ST eStore whole-STM32 audit established **406 current Active STM32G0 exact MPNs**. Plasma Production currently contains **47 STM32G0 exact ICPNs**, leaving **359 Layer-1 Catalog identity gaps**.

This gate answers why that gap exists without conflating Catalog identity with Programming Backend support.

## Historical boundary

The original STM32G0 Phase 4.8B discovery intentionally selected only one deterministic initial Base Device for each of 12 G0 subfamilies. It found 49 Active exact identities. Phase 4.8D then admitted 47 with deterministic OpenOCD ordering-pattern routes; two N-version identities remained route-unresolved.

That old bounded pilot was valid for its scope. It was never a full-family coverage claim.

The current v1.5 ledger is derived from the exact `Active - Production` set retained by the exhaustive eStore audit in PR #685 / workflow run `36797087427`.

- G0 exact gap rows: **359**
- Ledger SHA-256: `a6240e4a34e3834cba7195be306d449386dcac1b3e66189f6bfac8fdc7557a5d`

## Four-layer interpretation

For every row in this ledger:

1. **Device Catalog:** manufacturer-observed current Active exact MPN; therefore a Catalog identity candidate.
2. **Programming Backend/Profile:** independently measured against the existing OpenOCD G0 ordering-pattern research surface.
3. **Engineering Verified:** not claimed.
4. **Pilot/Production Field Evidence:** not claimed.

A missing or unresolved OpenOCD mapping must **not** turn an official Active exact commercial identity into a non-device.

Final-head CI result:

| Dimension | Result |
| --- | ---: |
| Active exact G0 | 406 |
| Production exact G0 | 47 |
| Exact gap | **359** |
| Production Active coverage | **11.5764%** |
| Gap variants on an already-published Base Device | **2** |
| Gap identities on new Base Devices | **357** |
| New Base Devices represented by those gaps | **87** |
| Current OpenOCD ordering-pattern unique routes | **317** |
| Current OpenOCD ordering-pattern unmapped | **42** |

The 42 unmapped identities do **not** invalidate their Layer-1 Catalog identity. They remain backend/profile follow-up.

This establishes the root cause: the dominant G0 coverage gap is the historical bounded discovery scope (12 published Base Devices), not a broad lack of OpenOCD ordering-pattern coverage.

The next gate after this triage is manufacturer-authoritative metadata acquisition for the 87 new Base Devices, followed by a separately reviewed Catalog publication proposal. Any Production write requires explicit owner approval.

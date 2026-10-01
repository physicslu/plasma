# STM32F0 Layer-1 Active Coverage Refresh v2.2

Research only. No Production Catalog write is authorized.

The whole-STM32 official eStore audit locked **263 current Active STM32F0 exact MPNs**. Production currently contains **42**, so the current Layer-1 gap is **221 exact identities** across **60 Base Devices** and 13 existing STM32F0 series.

The earlier Phase 4.5 work was deliberately bounded: one deterministic initial Base Device per series, producing 42 Production exact ICPNs. It did not claim full-family coverage.

## Validation before admission proposal

This refresh performs all of the following before a candidate appears in the proposal:

1. exact identity must belong to the locked official ST Active gap set;
2. its series must have an explicit official ST datasheet Ordering Information authority;
3. pin-count, Flash, package, temperature and option codes must decode under that **same series** authority;
4. ambiguous pin-count codes such as STM32F071/072/078 `C = 48/49` must resolve through the documented package combination;
5. OpenOCD mapping is replayed independently against the guarded 111-row STM32F0 surface.

Result expected by CI:

- Active exact gap: **221**
- metadata-decodable: **221 / 221**
- unique Base Devices in gap: **60**
- Layer-2 OpenOCD mapping candidates: **221**
- Layer-2 no_mapping: **0**
- Production write authorized: **false**

If later explicitly approved, F0 Layer-1 identity coverage would move from **42/263** to **263/263 = 100%**. The retained whole-ST 4,550-Active baseline would move from **3,211** to **3,432** current-Active identities, or **75.4286%**, leaving **1,118** Active exact gaps.

This does not create Engineering Verified, field evidence, PS/HIL qualification or programming-algorithm validation.

# OpenOCD C0 Bounded Route-Inventory Expansion Proposal v6.25

Research-only proposal for the five STM32C0 exact ICPNs that v6.24 proved have locked ST pattern authority.

## Proposed canonical route rows

Four ordering patterns are proposed:

- `STM32C011D6Yx`
- `STM32C051D8Yx`
- `STM32C091ECYx`
- `STM32C092ECYx`

They map only to the already-existing upstream OpenOCD target:

`tcl/target/stm32c0x.cfg`

The route metadata is inherited from existing canonical siblings in the same STM32C0 subfamily. The proposal must not invent CPU architecture, family labels, target distribution, mapping state, or validation state.

## Exact commercial scope

The proposal is bounded to five already-admitted Production ICPNs:

- `STM32C011D6Y6TR`
- `STM32C051D8Y6TR`
- `STM32C091ECY6TR`
- `STM32C092ECY3TR`
- `STM32C092ECY6TR`

The current C0 resolver produces zero compatible ordering-pattern routes for these five rows. With only the four proposed rows added in-memory, each exact ICPN resolves to exactly one authoritative pattern.

## Critical boundary

Adding route-inventory rows is **not** a Production mapping write.

Therefore this v6.25 proposal by itself leaves:

- Production mapped: **4,054**
- Production no_mapping: **575**
- Active OpenOCD route: **3,975 / 4,550 = 87.3626%**

Only a later, separately approved Production mapping transaction could move the five exact rows to mapped state. If that later gate succeeds, the theoretical route count becomes **3,980 / 4,550 = 87.4725%**, leaving **570** gaps.

## Excluded scope

- STM32L4 two-row resolver/suffix problem remains blocked.
- STM32G491RCY6TR remains on the independent ambiguity track.
- No generic C0 pattern rule is authorized.

No canonical inventory write, Production write, Programming Profile binding, erase/program/verify, Engineering Verified, or HIL claim is made here.

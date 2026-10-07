# OpenOCD Active Coverage Classification v6.3

This audit separates **ST Active identity coverage** from **OpenOCD route coverage**.

## Current state

The locked ST Active denominator is **4,550 exact MPNs** and Catalog identity coverage is **4,550 / 4,550 = 100%**.

Production contains **4,629** rows because it also retains **79 historical/non-current-Active identities**. Those 79 are all already OpenOCD-routed.

Therefore:

- Production mapped: **3,673**
- minus mapped rows outside the current Active denominator: **79**
- **Active OpenOCD route count: 3,594**
- **Active OpenOCD route coverage: 3,594 / 4,550 = 78.9890%**
- Active `no_mapping`: **956 / 4,550 = 21.0110%**

A route is still not the same as successful erase/program/verify HIL.

## 956-gap classification

| Tier | Count | Meaning |
|---|---:|---|
| A | **389** | Same series already has mapped sibling rows using one consistent OpenOCD target config |
| B | **102** | No mapped sibling in that exact series, but F3/F7 have family-level upstream target configs with flash banks |
| C | **32** | STM32N6 has upstream `stm32n6x.cfg`, but it contains no `flash bank`; debug target only for this audit |
| D | **433** | C5/H5/WL3/WB0 have no direct family target config in the bound upstream target inventory |

### Tier A family counts

- F2 72
- F3 172
- F4 3
- F7 62
- G0 42
- G4 1
- C0 17
- L4 3
- L1 2
- U3 1
- H7 14

### Tier B

- F3: 10
- F7: 92

### Tier C

- N6: 32

### Tier D

- C5: 172
- H5: 190
- WL3: 47
- WB0: 24

## Coverage opportunity

If Tier A alone passes backend qualification:

**3,983 / 4,550 = 87.5385%**

If Tier A + Tier B pass backend qualification:

**4,085 / 4,550 = 89.7802%**

That leaves **465** unresolved programming-route identities:

- N6 debug-only target: 32
- no direct upstream target config: 433

## Upstream OpenOCD evidence binding

Bound against `openocd-org/openocd` master commit:

`8da0578d7bce3e134821ccf10911182788debc32`

Relevant target config blobs:

- `stm32f3x.cfg`: `e616c20f89655a654d1ed44905c3f3a492d74c8d`
- `stm32f7x.cfg`: `345995c37f7b294911f93ca7b0df86495358579a`
- `stm32n6x.cfg`: `668182fbf9a0a91e50851dbe998a85ae94a72d0b`

The N6 config has no flash bank and is deliberately not counted as programming coverage.

## Governance

This is **research only**.

No `no_mapping` row is changed. Tier A/B means **qualification candidate**, not programming support. Promotion requires separate backend evidence and, later, real-device erase/program/verify qualification.

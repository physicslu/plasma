# ST OpenOCD Final Coverage Closure v6.31

v6.31 re-evaluates every current ST Production `no_mapping` exact ICPN against the **actual packaged Plasma OpenOCD runtime**, not an older research-only upstream snapshot.

## Production prestate

- exact identities: **4,629**
- mapped: **4,061**
- no_mapping: **568**
- Active OpenOCD route: **3,982 / 4,550 = 87.5165%**

## Runtime authority

The current packaged runtime is upstream OpenOCD 0.12.0 pinned to commit:

`9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`

At that exact runtime:

- STM32F3 / STM32F7 / STM32G4 target configs exist and contain flash-bank support.
- STM32C5 / STM32H5 / STM32N6 / STM32WB0 / STM32WL3 target configs are absent.
- `stm32wlx.cfg` exists but is not treated as authority for STM32WL3.

ST's OpenOCD fork contains C5/H5 target configs, and newer upstream contains an N6 debug target, but those are not the packaged Production runtime and therefore do not authorize Production mapping.

## Final 568-outcome partition

### Safe mapping candidates — 103

- STM32F3: **10**
- STM32F7: **92**
- STM32G4: **1**

Of these:

- **101** resolve uniquely to ordering patterns already in `openocd-parts-canonical-v627.csv`.
- only **2** require bounded route-inventory expansion:
  - `STM32F378VCHx`
  - `STM32G491RCYx`

Both expansions are bounded by official ST Ordering Information and by target configs already present in the packaged upstream runtime.

### Runtime-blocked — 465

- STM32C5: **172**
- STM32H5: **190**
- STM32N6: **32**
- STM32WB0: **24**
- STM32WL3: **47**

These remain `no_mapping` because the target config required by the family is absent from the pinned Production runtime. This is a runtime/backend-admission block, not an identity-metadata gap.

## Projected state if the 103-candidate transaction is later approved

- mapped: **4,164**
- no_mapping: **465**
- Active OpenOCD route: **4,085 / 4,550 = 89.7802%**

v6.31 is research-only at this stage. It does not modify Production, bind Programming Profiles, or claim erase/program/verify, Engineering Verified, electrical readiness or HIL.

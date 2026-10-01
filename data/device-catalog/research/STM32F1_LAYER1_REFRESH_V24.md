# STM32F1 Layer-1 Active Coverage Refresh v2.4

Research only. No Production Catalog write is authorized.

The locked whole-STM32 eStore audit reports **275 current Active STM32F1 exact MPNs**. Current Production contains 75 F1 exact ICPNs, of which 70 are in the current Active set, leaving **205 current Active identities missing from Production**. Five historical Production F1 identities are outside the current Active set, so a later complete Active publication would result in **280 Production F1 rows**, not 275.

## Validation before admission

F1 intentionally uses a different Layer-2 mapping model than F0/G0/G4:

- F1 guarded OpenOCD surface: **95 `cmsis_device_name` Base Device rows**
- exact ICPN -> Base Device -> unique CMSIS/base mapping
- target config: `tcl/target/stm32f1x.cfg`

The 205 gaps resolve to **77 Base Devices**, and every Base Device has one unique guarded mapping.

Metadata is validated by official ST Ordering Information **density bands**, not one global family map:

- F100: low/medium and high density;
- F101/F103: low, medium, high and XL density;
- F102: low and medium density;
- F105/F107: connectivity-line rules.

Legacy internal product codes such as F100 `B` and low-density F101/F102/F103 `A` remain part of the exact order code and are never normalized away.

One bounded exact metadata exception is explicit:

- `STM32F101RBH6`: official current ST product/eStore evidence identifies the exact Active product as **TFBGA64**, while the medium-density F101 Ordering Information table does not enumerate package code `H`.

## Programming Profile boundary

Catalog admission does **not** expand the existing STM32F103C Programming Profile applicability. The current evidence-backed pilot bindings remain independent. Every new proposal row is marked `unresolved_no_new_applicability_binding` for Programming Profile state.

Expected result:

- current Active gap: **205**
- unique gap Base Devices: **77**
- metadata-decodable: **205 / 205**
- Layer-2 mapping candidates: **205 / 205**
- Layer-2 no_mapping: **0**
- new Programming Profile bindings: **0**
- Production write authorized: **false**

If later explicitly approved:

- F1 current-Active identity coverage becomes **275/275 = 100%**
- F1 Production rows become **280**
- global Production exact rows become **3,716**
- whole-ST current Active intersection becomes **3,637 / 4,550 = 79.9341%**
- remaining current Active gap becomes **913**

This creates no Engineering Verified, field evidence, PS/HIL qualification, or Programming Profile applicability claim.

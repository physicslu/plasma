# OpenOCD C0 Canonical Route-Inventory Write Dry-Run v6.26

This stage turns the approved v6.25 proposal into a byte-exact **dry-run transaction**. It does not modify `openocd-parts-canonical.csv`.

## Transaction boundary

Preimage lease:

- canonical path: `data/device-catalog/research/openocd-parts-canonical.csv`
- Git blob SHA: `0ef056e3363e20bb527590c4a4cc1cc0d7afb810`
- rows: **7,657**

Exact delta:

- four STM32C0 ordering-pattern rows from v6.25
- exact v6.25 delta SHA256: `5d6f2b022a0efab409f57dece8cfcb06dace9cbf93c4a533beef9b4ecbf84b24`
- projected rows: **7,661**
- preimage SHA256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- frozen postimage Git blob SHA: `81e44f6a6df902f3b206d06bfac38e37ec74630b`
- frozen postimage SHA256: `39bb6f17765b8c95fdf1cdfa9831ac1c71ef3edd08ae899fcf6f67eae4234751`
- byte count: **1,582,603 → 1,583,487**

The dry-run renderer must prove that the preimage can be reproduced byte-for-byte before it is allowed to calculate a postimage. It then proves that the postimage adds exactly four keys, removes zero rows, mutates zero existing rows, and creates zero duplicates.

## Provenance requirement

The v6.25 canonical rows use:

`catalog_origin = openocd-c0-bounded-route-inventory-v6.25.csv`

Therefore any later actual canonical write must materialize that exact 4-row source CSV in the repository in the **same transaction**, with the frozen v6.25 SHA256. A canonical write without that provenance file is not acceptable.

## Production boundary

A canonical route-inventory write alone does not change Production mapping state. Production remains:

- mapped: **4,054**
- no_mapping: **575**
- Active OpenOCD route: **3,975 / 4,550 = 87.3626%**

A later Production mapping transaction remains a separate approval gate.

No canonical write, source materialization, Production write, Programming Profile binding, erase/program/verify, Engineering Verified, or HIL claim is authorized by v6.26.

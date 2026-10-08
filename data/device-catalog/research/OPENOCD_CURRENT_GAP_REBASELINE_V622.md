# OpenOCD Current Gap Rebaseline v6.22

Research-only reclassification of the Production OpenOCD route gap after the v6.21 17-row bounded Production write.

## Current Production boundary

- Production exact identities: **4,629**
- mapped: **4,054**
- no_mapping: **575**
- Active OpenOCD route: **3,975 / 4,550 = 87.3626%**

## Expected current tier partition

- A residual: **8**
- B: **102**
- C: **32**
- D: **433**

The 17 v6.21 mappings came entirely from the prior 25-row A residual set. Therefore the remaining A set is expected to contain only:

- STM32C0: 5
- STM32G4: 1
- STM32L4: 2

B/C/D must remain unchanged from v6.17.

This is route-gap classification only. It does not infer identifiers, bind Programming Profiles, authorize another Production write, or claim erase/program/verify, Engineering Verified, or HIL status.

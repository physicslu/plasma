# ST OpenOCD Post-v6.31 Gap Disposition v6.32

## Result

The former 568-row ST OpenOCD gap is now fully dispositioned.

- v6.31 promoted **103** deterministic backend mappings.
- Production is now **4,164 mapped / 465 no_mapping** across **4,629** exact ICPNs.
- Active OpenOCD route coverage is **4,085 / 4,550 = 89.7802%**.
- The remaining **465/465** rows have explicit fail-closed dispositions.

## Remaining 465

| Family | Exact | Disposition |
|---|---:|---|
| STM32H5 | 190 | Runtime candidate: pinned ST fork has a native H5 flash driver, but the provider is not yet Production-packaged or hardware-qualified. |
| STM32C5 | 172 | Blocked: ST `stldr` path has empty loader mapping plus retained Tcl defects and unresolved loader/runtime gates. |
| STM32N6 | 32 | Blocked: no N6 target config exists in the packaged upstream runtime or the pinned ST fork used by this review. |
| STM32WB0 | 24 | Blocked: no direct WB0 target config in either reviewed runtime source. |
| STM32WL3 | 47 | Blocked: no direct WL3 target config in either reviewed runtime source; existing `stm32wlx` must not be generalized. |

This closes the **research question** for every current ST `no_mapping` identity. It does not mean the 465 devices are permanently unsupported. It means each now has a concrete technical dependency instead of an unexplained catalog gap.

## H5 next gate

H5 is the only large remaining set with a credible native OpenOCD flash-driver path today. The bounded order is:

1. ARMv7 source/build/package execution;
2. Plasma FPGA SWD adapter compatibility;
3. approved read-only physical ID / flash-bank probe;
4. Programming Profile + Electrical Programming Profile;
5. only then controlled erase/program/verify and any Production mapping proposal.

## Governance

No Production CSV or manifest is modified by v6.32. All physical, programming, electrical, HIL and Production-readiness claims remain false.

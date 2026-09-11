# STM32F103C Vendor-Neutral Admission Migration v1

Status: Gate 1 implementation candidate; software-only admission migration.

## Exact scope

Targets:

- `STM32F103C8T6`
- `STM32F103CBT6`

Manufacturer authority is limited to the already locked ST sources:

- `DS5319 Rev 20` (`st_ds5319_rev20`)
- `PM0075 Rev 2` (`st_pm0075_rev2`)

This migration reuses the existing exact ICPN identity, `stm32f1-medium-density-flash-v0` Programming Profile, target-specific Memory Geometry Profiles, STM32F103C pilot binding, Programming Execution IR, and `OpenOCDPlanCompiler`. It does not rerun ICPN discovery or any AI model and it does not rewrite the historical v0-v9 experiment lineage.

## Bounded manufacturer review

`vendor-neutral-admission-contract-v1.json` freezes nine execution-relevant manufacturer facts covering:

- STM32F103x8/xB applicability and 64/128 KiB Flash scope;
- medium-density 1 KiB page geometry;
- C8 and CB exact main-Flash geometry derivation;
- Flash unlock keys;
- 16-bit programming granularity;
- standard main-Flash program sequence;
- page erase versus controller Mass Erase distinction;
- destructive read-unprotect behavior.

The review is intentionally narrower than the historical research pipeline. Security and option-byte semantics that are not required for the admitted software operations remain outside operation admission.

## Operation boundary

Admitted for Software Executor governance only:

- `READ`
- `VERIFY`
- `PROGRAM`
- `ERASE`

The existing application-level `ERASE` compiler behavior is bound explicitly as:

```text
flash erase_address <resolved_main_flash_start> <resolved_main_flash_size>
```

Therefore `ERASE` means **full resolved main-Flash range erase** for this migration. It is not represented as one-page erase and it is not claimed to be semantically identical to the STM32 controller `MER` Mass Erase command.

Blocked:

- controller Mass Erase operation;
- option programming / erase;
- RDP enable / disable;
- write-protection changes.

`hardware_runtime_ready` remains `false` everywhere.

## Non-claims

This migration does not establish:

- new commercial ICPN evidence;
- Production catalog or routing changes;
- new compiler behavior;
- physical OpenOCD / SWD qualification;
- HIL or real-IC programming;
- PL/PPU programming-engine qualification;
- destructive security-operation admission.

Manufacturer evidence > validated canonical specification > implementation binding > AI opinion remains the authority order.

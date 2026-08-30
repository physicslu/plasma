# IC Support Runtime Resolver Foundation

Status: **Phase 3.5 pilot**

## 1. Purpose

Plasma must resolve an exact commercial IC part number into reusable technical support knowledge before a Programming Handler or backend can make execution decisions.

The intended chain is:

```text
Exact ICPN
  -> Device Catalog identity
  -> IC Support binding
  -> ResolvedICSupport
  -> Programming route
       -> OpenOCD backend
       -> Plasma Native PPU backend
```

`ResolvedICSupport` is not a support badge and is not physical validation. It is the deterministic join between one exact ICPN and the reusable Programming, Memory Geometry, Package / Hardware, Option and Security profiles already owned by `data/ic-support/`.

## 2. Phase 3.5 boundary

Phase 3.5 introduces a runtime-consumable resolver but deliberately does not make the current Handler or hardware backend consume the resolved profiles yet.

This distinction is required because the current runtime still contains target-specific implementation debt:

- `SiteManager` constructs `STM32F103Handler` for every enabled Site;
- `STM32F103Handler` is still a legacy target-specific handler;
- `OpenOCDInterface.erase()` still contains a fixed `0x08000000 / 0x10000` erase template;
- OpenOCD Program / Verify / Read remain hardware-specific placeholders;
- no Plasma Native PPU programming driver consumes IC Support profiles yet.

Therefore:

```text
Profile resolved != runtime driver implemented
```

The resolver reports this explicitly. A resolved Programming Profile may be useful to a future OpenOCD adapter or Native PPU driver, but Phase 3.5 does not promote it to runtime-ready status.

## 3. Current resolver truth

At the Phase 3.5 baseline:

- production Device Catalog: 124 exact ICPNs;
- normalized Base Devices: 32;
- deterministic OpenOCD target mappings: 124;
- direct evidence-backed IC Support bindings: 2;
- evidence-backed Programming Profiles reachable through those bindings: 1;
- Native PPU runtime-ready exact ICPNs: 0.

The two directly resolvable exact ICPNs are:

```text
STM32F103C8T6
STM32F103CBT6
```

They share:

```text
Programming Profile: stm32f1-medium-density-flash-v0
OpenOCD target:       tcl/target/stm32f1x.cfg
```

but intentionally use different Memory Geometry Profiles for 64 KiB and 128 KiB Main Flash.

An admitted catalog part such as `STM32F407VGT6` remains unresolved by the IC Support runtime resolver. Its deterministic OpenOCD target mapping is useful catalog evidence, but it is not enough to invent a complete Programming Profile.

## 4. Runtime resolver contract

`software/python/plasma_core/ic_support.py` loads the checked-in IC Support profile and binding sets and resolves exact ICPNs case-insensitively.

The resolver fails closed on at least:

- missing profile or binding directories;
- malformed JSON;
- duplicate Profile IDs;
- profile kind / directory mismatch;
- duplicate exact-ICPN bindings;
- missing catalog identity fields in a binding;
- missing required profile kinds;
- dangling profile references;
- profile kind/reference mismatch.

A successful `ResolvedICSupport` contains:

```text
exact ICPN
binding set identity/status
expected catalog identity
Programming Profile
Memory Geometry Profile
Package / Hardware Profile
Option Profile
Security Profile
Revision Overrides[]
OpenOCD target identity
```

The runtime payload intentionally reports:

```text
OpenOCD: target_mapped
Plasma Native: algorithm_profile_available_runtime_not_implemented
runtime_ready: false
```

until execution wiring is separately implemented and tested.

## 5. Why Mock is different

The Mock runtime is a workflow simulator. It may continue to exercise a selected production-catalog ICPN without claiming that the selected IC has a real hardware Programming Profile or Native PPU implementation.

Real backend routing must not use Mock success as evidence of target support.

## 6. Scientific scale-out gate remains in force

The existing STM32F103C IC Support architecture still requires a valid isolated blind extraction result before bulk creation of new family Programming Profiles. Phase 3.5 does not weaken that gate.

That means the next steps are intentionally separated:

1. establish `ResolvedICSupport` as a deterministic runtime contract;
2. wire execution to consume it in a later approved phase;
3. complete the isolated extraction gate;
4. then expand evidence-backed Programming Profiles to additional Base Devices/families.

This prevents catalog coverage, OpenOCD target mapping and actual programming-algorithm readiness from collapsing into one misleading `supported=true` flag.

## 7. Non-goals

Phase 3.5 does not:

- add or remove Device Catalog ICPNs;
- alter the 124 / 32 production coverage baseline;
- change OpenOCD command templates;
- implement Program / Verify / Read for OpenOCD;
- implement a Native PPU driver;
- change PMode / EMode selection behavior;
- create PPU or Socket validation evidence;
- deploy or restart services;
- access Z2, FPGA or real IC hardware.

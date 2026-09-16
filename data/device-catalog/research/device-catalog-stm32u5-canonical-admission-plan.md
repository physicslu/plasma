# STM32U5 canonical admission plan under security fence

## Scope

This research-only transaction plans canonical admission for the **265 Active, metadata-ready STM32U5 exact ICPNs**. It does not write Production and it does not admit the quarantined Preview identity `STM32U5G9ZJJ3Q`.

## Route result

- retained exact identities: **266**;
- Active metadata-ready admission scope: **265**;
- quarantined Preview identities: **1**;
- frozen STM32U5 route evidence rows: **162**;
- route evidence kinds: **63 ordering_pattern / 99 cmsis_device_name**;
- standard exact-to-route assignments: **264**;
- supplemental CMSIS exact-membership bridges: **1**;
- final unique route assignments: **265 / 265**;
- unresolved after bridge: **0**;
- required target config: `tcl/target/stm32u5x.cfg`.

Frozen route-evidence SHA-256:

`01b9b9b36423752199bab34b8a3a4ba7adb3445d2d884a46c0501c09701f099d`

Frozen exact-to-route binding SHA-256:

`0aa91868a0fd8dc66f0aded52748f7c95bc58b5fb01d11629ec22fcd0c3f9907`

## STM32U5A5QII3Q route bridge

The bounded probe found one Active metadata-ready exact ICPN with no match in the frozen Plasma OpenOCD/CMSIS pattern surface: `STM32U5A5QII3Q`.

The bridge does **not** invent an OpenOCD ordering pattern. It retains a separate reviewed evidence record:

1. ST's official `STMicroelectronics/cmsis-device-u5` repository explicitly lists `STM32U5A5QII3Q` under CMSIS device selector `STM32U5A5xx` in `Include/stm32u5xx.h`.
2. The same repository's V1.3.1 release notes explicitly record adding `STM32U5A5QII3Q` to the STM32U5A5xx device list.
3. The frozen Plasma route surface contains **11** STM32U5A5 rows and all resolve to `tcl/target/stm32u5x.cfg`.

The exact bridge therefore binds:

`STM32U5A5QII3Q -> STM32U5A5xx -> tcl/target/stm32u5x.cfg`

as `cmsis_exact_membership_bridge` evidence only. The source repository commit and source blob SHAs are pinned in `stm32u5-cmsis-route-bridge.json`.

This bridge is exact-part scoped. It cannot admit another QI part, synthesize an ordering pattern, or expand the retained identity set.

## Security fence

The merged STM32U5 security foundation remains authoritative. This plan leaves false:

- security semantics support;
- option-byte writes;
- OEM-key provisioning or unlock execution;
- RDP regression;
- mass erase;
- Flash-geometry validation;
- programming-algorithm equivalence;
- runtime programming support;
- debug attach;
- HIL.

Catalog planning remains independent of HIL, but catalog membership does not authorize execution.

## Production boundary

Production remains **2,017 exact ICPNs** and STM32U5 remains absent from the Production manifest. This transaction only freezes a read-only canonical plan.

The one Preview exact identity remains retained as manufacturer identity evidence but outside canonical admission scope until its metadata authority gap is explicitly resolved.

## Next gate

`stm32u5-security-state-admission-gate`
